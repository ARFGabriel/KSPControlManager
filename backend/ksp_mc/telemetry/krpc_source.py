"""Source de telemetrie reelle, branchee sur le serveur kRPC dans KSP.

Point d'architecture important : chaque lecture d'une propriete kRPC est un
aller-retour reseau. Lire 30 valeurs a 10 Hz ferait 300 appels par seconde et
saturerait la liaison. On utilise donc les *streams* kRPC : le serveur pousse
les valeurs qui changent, le client les garde en cache local, et les lire
devient gratuit. Seules les donnees lourdes et lentes (liste des etages,
ressources) sont interrogees a basse frequence.
"""

from __future__ import annotations

import time

import krpc

from . import deltav
from .schema import OrbitInfo, ResourceInfo, StageInfo, Telemetry
from .source import TelemetrySource, safe

# Facteurs de conversion : kRPC parle en kg et en newtons, le jeu affiche
# des tonnes et des kilonewtons.
KG_TO_T = 1e-3
N_TO_KN = 1e-3

# Periode de rafraichissement des donnees lourdes (ressources, equipage).
COLD_REFRESH_S = 1.0

# Le detail par etage est recalcule par nos soins (voir deltav.py) et coute
# environ 250 ms : 130 ms de lecture des 48 pieces, 120 ms de simulation.
# Beaucoup trop pour le cycle de telemetrie a 10 Hz, d'ou cette cadence a
# part. Un changement d'etage force un recalcul immediat, car c'est justement
# le moment ou les chiffres changent du tout au tout.
STAGE_REFRESH_S = 5.0


class KrpcSource(TelemetrySource):
    name = "krpc"

    def __init__(
        self,
        address: str = "127.0.0.1",
        rpc_port: int = 50000,
        stream_port: int = 50001,
        client_name: str = "KSP Mission Control",
    ) -> None:
        self.address = address
        self.rpc_port = rpc_port
        self.stream_port = stream_port
        self.client_name = client_name

        self.conn = None
        self._vessel = None
        self._streams: dict[str, object] = {}
        self._flight = None
        self._flight_orbital = None
        self._flight_surface = None

        # Cache des donnees lentes
        self._cold_at = 0.0
        self._cold: dict = {}

        # Cache du detail par etage, rafraichi a sa propre cadence
        self._stages: list[StageInfo] = []
        self._stages_at = 0.0
        self._stages_stage: int | None = None

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    def connect(self) -> None:
        self.conn = krpc.connect(
            name=self.client_name,
            address=self.address,
            rpc_port=self.rpc_port,
            stream_port=self.stream_port,
        )

    def close(self) -> None:
        self._drop_streams()
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    # ------------------------------------------------------------------
    # Gestion des streams
    # ------------------------------------------------------------------
    def _drop_streams(self) -> None:
        for stream in self._streams.values():
            try:
                stream.remove()
            except Exception:
                pass
        self._streams.clear()
        self._flight = None
        self._flight_orbital = None
        self._flight_surface = None
        self._vessel = None

    def _add(self, key: str, obj, attr: str) -> None:
        """Cree un stream, en ignorant silencieusement ceux que le contexte
        rend invalides (ex : delta_v sur un vaisseau sans moteur)."""
        try:
            self._streams[key] = self.conn.add_stream(getattr, obj, attr)
        except Exception:
            pass

    def _build_streams(self, vessel) -> None:
        self._drop_streams()
        self._vessel = vessel

        sc = self.conn.space_center
        body = vessel.orbit.body

        # Trois reperes, parce qu'aucun ne mesure tout correctement :
        #
        #  - body.reference_frame TOURNE avec l'astre. Il donne la vitesse
        #    "surface" du jeu, ainsi que l'altitude et les grandeurs
        #    atmospheriques. Mais son attitude est fausse (voir plus bas).
        #  - body.non_rotating_reference_frame donne la vitesse orbitale, la
        #    seule valable des qu'on s'eloigne : en orbite solaire, la
        #    rotation du repere ajoute des dizaines de km/s d'artefact.
        #  - vessel.surface_reference_frame est centre sur le vaisseau et
        #    oriente zenith/nord/est. C'est LUI qui donne l'assiette, le cap
        #    et le roulis de la navball. Mesure a l'appui : le cap y vaut 90,7
        #    la ou le repere de l'astre annonce 269,6, soit 180 d'ecart.
        #    En revanche il est fixe au vaisseau, donc toute vitesse y vaut 0.
        self._flight = vessel.flight(body.reference_frame)
        self._flight_orbital = vessel.flight(body.non_rotating_reference_frame)
        self._flight_surface = vessel.flight(vessel.surface_reference_frame)

        self._add("ut", sc, "ut")
        self._add("met", vessel, "met")

        for attr in (
            "mean_altitude",
            "surface_altitude",
            "speed",
            "vertical_speed",
            "g_force",
            "dynamic_pressure",
            "mach",
            "static_pressure",
            "atmosphere_density",
        ):
            self._add(attr, self._flight, attr)

        self._add("orbital_speed", self._flight_orbital, "speed")

        # Attitude : imperativement dans le repere du vaisseau, sinon les trois
        # angles sont faux.
        for attr in ("pitch", "heading", "roll"):
            self._add(attr, self._flight_surface, attr)

        for attr in ("thrust", "available_thrust", "mass", "dry_mass"):
            self._add(attr, vessel, attr)

        self._add("throttle", vessel.control, "throttle")
        self._add("current_stage", vessel.control, "current_stage")

        orbit = vessel.orbit
        for attr in (
            "apoapsis_altitude",
            "periapsis_altitude",
            "eccentricity",
            "inclination",
            "period",
            "time_to_apoapsis",
            "time_to_periapsis",
            "semi_major_axis",
        ):
            self._add(f"orbit_{attr}", orbit, attr)

    def _get(self, key: str, default=0.0):
        stream = self._streams.get(key)
        if stream is None:
            return default
        try:
            value = stream()
            return default if value is None else value
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Donnees lentes
    # ------------------------------------------------------------------
    def _refresh_cold(self, vessel) -> None:
        """Interroge les donnees couteuses : etages, ressources, equipage.

        Ces valeurs bougent rarement (un largage d'etage, une consommation
        progressive), donc une fois par seconde suffit largement.
        """
        cold: dict = {}
        cold["vessel_name"] = safe(lambda: vessel.name, "")
        cold["situation"] = _enum_name(safe(lambda: vessel.situation))
        cold["body"] = safe(lambda: vessel.orbit.body.name, "")
        cold["crew_count"] = safe(lambda: vessel.crew_count, 0)
        cold["surface_gravity"] = safe(lambda: vessel.orbit.body.surface_gravity, 9.81)

        # --- Delta-v ---
        # Lu ici plutot qu'en stream : KSP peut ne pas l'avoir encore calcule
        # au moment ou on cree les streams, et un stream absent ne se
        # recreerait jamais. A 1 Hz on retente en permanence, et le delta-v ne
        # varie de toute facon qu'a la vitesse de consommation des ergols.
        try:
            cold["delta_v"] = vessel.delta_v
            cold["vacuum_delta_v"] = vessel.vacuum_delta_v
            cold["delta_v_available"] = True
        except Exception:
            cold["delta_v"] = 0.0
            cold["vacuum_delta_v"] = 0.0
            cold["delta_v_available"] = False

        # --- CommNet ---
        # can_communicate leve une NullReferenceException cote serveur quand
        # CommNet est desactive ou que le vaisseau n'a pas de module de
        # liaison. On le signale au lieu de faire croire a une liaison
        # parfaite : la radio devra savoir qu'il n'y a rien a contraindre.
        cold["comm_available"] = False
        cold["can_communicate"] = True
        cold["signal_strength"] = 1.0
        comms = safe(lambda: vessel.comms)
        if comms is not None:
            try:
                cold["can_communicate"] = comms.can_communicate
                cold["signal_strength"] = comms.signal_strength
                cold["comm_available"] = True
            except Exception:
                pass

        # Le detail par etage n'est PAS lu ici : sur KSP 1.12.5, toutes les
        # proprietes de Stage levent "Delta-v has not been calculated for this
        # vessel yet", meme quand le jeu affiche les chiffres a l'ecran. On le
        # recalcule dans _refresh_stages a partir des pieces.

        # --- Ressources ---
        resources: list[ResourceInfo] = []
        res = safe(lambda: vessel.resources)
        if res is not None:
            for rname in safe(lambda: res.names, []) or []:
                resources.append(
                    ResourceInfo(
                        name=rname,
                        amount=safe(lambda: res.amount(rname), 0.0),
                        maximum=safe(lambda: res.max(rname), 0.0),
                    )
                )
        cold["resources"] = resources

        self._cold = cold
        self._cold_at = time.monotonic()

    def _refresh_stages(self, vessel, current_stage: int) -> None:
        """Recalcule le detail par etage, a cadence reduite.

        Valide contre l'affichage du jeu sur un lanceur a propulseurs
        lateraux : ecart nul sur les deux etages propulsifs principaux,
        0,6 % sur le total.
        """
        now = time.monotonic()
        stale = now - self._stages_at > STAGE_REFRESH_S
        staged = self._stages_stage != current_stage
        if not (stale or staged or not self._stages):
            return

        try:
            parts, densities = deltav.snapshot(vessel)
            self._stages = deltav.compute_stages(parts, densities, current_stage)
        except Exception:
            self._stages = []
        self._stages_stage = current_stage
        self._stages_at = now

    # ------------------------------------------------------------------
    # Echantillonnage
    # ------------------------------------------------------------------
    def sample(self) -> Telemetry:
        if self.conn is None:
            return Telemetry(connected=False, source=self.name, error="Non connecte")

        # Cette lecture sert aussi de test de vie de la liaison : si elle leve,
        # c'est que le jeu a ete ferme ou le serveur arrete. On laisse alors
        # l'exception remonter au hub, qui relancera la detection.
        scene = _enum_name(self.conn.krpc.current_game_scene)

        # Attention : hors de la scene de vol, active_vessel renvoie None au
        # lieu de lever. Sans ce test explicite, on construirait la telemetrie
        # sur un objet nul et le dashboard afficherait des zeros credibles.
        vessel = self.conn.space_center.active_vessel
        if vessel is None:
            if self._vessel is not None:
                self._drop_streams()
            return Telemetry(
                connected=True,
                source=self.name,
                game_scene=scene,
                error=_no_vessel_message(scene),
                timestamp=time.time(),
                ut=safe(lambda: self.conn.space_center.ut, 0.0),
            )

        try:
            if vessel != self._vessel:
                self._build_streams(vessel)
                self._refresh_cold(vessel)
            elif time.monotonic() - self._cold_at > COLD_REFRESH_S:
                self._refresh_cold(vessel)
        except Exception as exc:
            return Telemetry(
                connected=True,
                source=self.name,
                game_scene=scene,
                error=f"Erreur de lecture : {exc}",
                timestamp=time.time(),
            )

        cold = self._cold
        current_stage = int(self._get("current_stage", 0))
        self._refresh_stages(vessel, current_stage)

        mass_t = self._get("mass") * KG_TO_T
        available_thrust_kn = self._get("available_thrust") * N_TO_KN
        gravity = cold.get("surface_gravity", 9.81)
        weight_kn = mass_t * gravity  # t * m/s2 = kN
        twr = available_thrust_kn / weight_kn if weight_kn > 0 else 0.0

        # Delta-v total : on prefere la valeur du jeu quand elle existe, sinon
        # la somme de notre propre calcul par etage. Les deux concordent a
        # 0,6 % pres, mais celle du jeu fait foi.
        if cold.get("delta_v_available"):
            dv_total = cold.get("delta_v", 0.0)
            dv_available = True
        elif self._stages:
            dv_total = deltav.total_delta_v(self._stages)
            dv_available = True
        else:
            dv_total = 0.0
            dv_available = False

        return Telemetry(
            connected=True,
            source=self.name,
            timestamp=time.time(),
            game_scene=scene,
            ut=self._get("ut"),
            met=self._get("met"),
            vessel_name=cold.get("vessel_name", ""),
            situation=cold.get("situation", ""),
            body=cold.get("body", ""),
            crew_count=cold.get("crew_count", 0),
            altitude=self._get("mean_altitude"),
            surface_altitude=self._get("surface_altitude"),
            speed=self._get("speed"),
            orbital_speed=self._get("orbital_speed"),
            vertical_speed=self._get("vertical_speed"),
            g_force=self._get("g_force"),
            dynamic_pressure=self._get("dynamic_pressure"),
            mach=self._get("mach"),
            pitch=self._get("pitch"),
            heading=self._get("heading"),
            roll=self._get("roll"),
            static_pressure=self._get("static_pressure"),
            atmosphere_density=self._get("atmosphere_density"),
            throttle=self._get("throttle"),
            thrust=self._get("thrust") * N_TO_KN,
            available_thrust=available_thrust_kn,
            mass=mass_t,
            dry_mass=self._get("dry_mass") * KG_TO_T,
            twr=twr,
            delta_v=dv_total,
            vacuum_delta_v=cold.get("vacuum_delta_v", 0.0),
            delta_v_available=dv_available,
            current_stage=current_stage,
            stages=self._stages,
            resources=cold.get("resources", []),
            orbit=OrbitInfo(
                body=cold.get("body", ""),
                apoapsis=self._get("orbit_apoapsis_altitude"),
                periapsis=self._get("orbit_periapsis_altitude"),
                eccentricity=self._get("orbit_eccentricity"),
                inclination=self._get("orbit_inclination") * 57.29577951308232,
                period=self._get("orbit_period"),
                time_to_apoapsis=self._get("orbit_time_to_apoapsis"),
                time_to_periapsis=self._get("orbit_time_to_periapsis"),
                semi_major_axis=self._get("orbit_semi_major_axis"),
            ),
            comm_available=cold.get("comm_available", False),
            comm_can_communicate=cold.get("can_communicate", True),
            comm_signal_strength=cold.get("signal_strength", 1.0),
        )


def _enum_name(value) -> str:
    """kRPC renvoie des enums generes ; on veut juste leur nom lisible."""
    if value is None:
        return ""
    return str(getattr(value, "name", value))


# Sans vaisseau actif, le message doit dire ou on se trouve : c'est une
# information, pas une panne.
_SCENE_MESSAGES = {
    "space_center": "Au centre spatial — aucun vaisseau en vol",
    "editor_vab": "Dans le VAB",
    "editor_sph": "Dans le hangar (SPH)",
    "tracking_station": "Station de suivi",
    "main_menu": "Menu principal — aucune partie chargee",
    "flight": "Vaisseau en cours de chargement",
}


def _no_vessel_message(scene: str) -> str:
    return _SCENE_MESSAGES.get(scene, "Aucun vaisseau actif")
