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

from .schema import OrbitInfo, ResourceInfo, StageInfo, Telemetry
from .source import TelemetrySource, safe

# Facteurs de conversion : kRPC parle en kg et en newtons, le jeu affiche
# des tonnes et des kilonewtons.
KG_TO_T = 1e-3
N_TO_KN = 1e-3

# Periode de rafraichissement des donnees lourdes (etages, ressources).
COLD_REFRESH_S = 1.0


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

        # Cache des donnees lentes
        self._cold_at = 0.0
        self._cold: dict = {}

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
        # Repere de reference lie a la surface du corps survole : c'est celui
        # qui donne la vitesse "surface" affichee par le jeu au decollage.
        frame = body.reference_frame
        self._flight = vessel.flight(frame)

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
            "pitch",
            "heading",
            "roll",
            "static_pressure",
            "atmosphere_density",
        ):
            self._add(attr, self._flight, attr)

        for attr in (
            "thrust",
            "available_thrust",
            "mass",
            "dry_mass",
            "delta_v",
            "vacuum_delta_v",
        ):
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

        comms = safe(lambda: vessel.comms)
        if comms is not None:
            cold["can_communicate"] = safe(lambda: comms.can_communicate, True)
            cold["signal_strength"] = safe(lambda: comms.signal_strength, 1.0)
        else:
            # Sondes sans antenne, ou CommNet desactive : on considere la
            # liaison etablie plutot que de couper la radio a tort.
            cold["can_communicate"] = True
            cold["signal_strength"] = 1.0

        # --- Etages ---
        stages: list[StageInfo] = []
        for stage in safe(lambda: vessel.stages, []) or []:
            number = safe(lambda: stage.number, -1)
            # Le delta-v n'est defini que sur les etages d'activation ;
            # les etages de decouplage levent une exception, on les saute.
            dv = safe(lambda: stage.delta_v)
            if dv is None:
                continue
            stages.append(
                StageInfo(
                    number=number,
                    delta_v=dv,
                    vacuum_delta_v=safe(lambda: stage.vacuum_delta_v, 0.0),
                    twr=safe(lambda: stage.twr, 0.0),
                    burn_time=safe(lambda: stage.burn_time, 0.0),
                    start_mass=safe(lambda: stage.start_mass, 0.0) * KG_TO_T,
                    end_mass=safe(lambda: stage.end_mass, 0.0) * KG_TO_T,
                )
            )
        stages.sort(key=lambda s: s.number, reverse=True)
        cold["stages"] = stages

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

    # ------------------------------------------------------------------
    # Echantillonnage
    # ------------------------------------------------------------------
    def sample(self) -> Telemetry:
        if self.conn is None:
            return Telemetry(connected=False, source=self.name, error="Non connecte")

        try:
            vessel = self.conn.space_center.active_vessel
        except Exception as exc:
            # Cas normal : on est au centre spatial, dans le VAB, ou en
            # transition de scene. Pas d'erreur a afficher en rouge.
            return Telemetry(
                connected=True,
                source=self.name,
                error="Aucun vaisseau actif",
                timestamp=time.time(),
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
                error=f"Erreur de lecture : {exc}",
                timestamp=time.time(),
            )

        cold = self._cold
        mass_t = self._get("mass") * KG_TO_T
        available_thrust_kn = self._get("available_thrust") * N_TO_KN
        gravity = cold.get("surface_gravity", 9.81)
        weight_kn = mass_t * gravity  # t * m/s2 = kN
        twr = available_thrust_kn / weight_kn if weight_kn > 0 else 0.0

        return Telemetry(
            connected=True,
            source=self.name,
            timestamp=time.time(),
            ut=self._get("ut"),
            met=self._get("met"),
            vessel_name=cold.get("vessel_name", ""),
            situation=cold.get("situation", ""),
            body=cold.get("body", ""),
            crew_count=cold.get("crew_count", 0),
            altitude=self._get("mean_altitude"),
            surface_altitude=self._get("surface_altitude"),
            speed=self._get("speed"),
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
            delta_v=self._get("delta_v"),
            vacuum_delta_v=self._get("vacuum_delta_v"),
            current_stage=int(self._get("current_stage", 0)),
            stages=cold.get("stages", []),
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
            comm_can_communicate=cold.get("can_communicate", True),
            comm_signal_strength=cold.get("signal_strength", 1.0),
        )


def _enum_name(value) -> str:
    """kRPC renvoie des enums generes ; on veut juste leur nom lisible."""
    if value is None:
        return ""
    return str(getattr(value, "name", value))
