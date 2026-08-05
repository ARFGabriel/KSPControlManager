"""Simulateur de vol, utilise quand KSP n'est pas lance.

Ce n'est pas un jouet : il integre une vraie dynamique du point materiel
(gravite en 1/r2, trainee atmospherique exponentielle, perte de masse par
consommation d'ergols, largage d'etages) et calcule les elements orbitaux a
partir du vecteur d'etat. Les chiffres affiches sont donc plausibles, ce qui
permet de mettre au point le dashboard et, plus tard, les lois de pilotage
sans mobiliser le jeu.

Repere : plan 2D, x tangentiel (vers l'est), y radial (vers le haut).
Constantes de Kerbin.
"""

from __future__ import annotations

import math
import time

from ..config import settings
from .schema import OrbitInfo, ResourceInfo, StageInfo, Telemetry
from .source import TelemetrySource

# --- Constantes de Kerbin ---
R_KERBIN = 600_000.0          # m
MU_KERBIN = 3.5316000e12      # m3/s2
G0 = 9.80665                  # m/s2, pour le calcul d'Isp
ATMO_HEIGHT = 70_000.0        # m
P0 = 101_325.0                # Pa au niveau de la mer
SCALE_HEIGHT = 5_600.0        # m
RHO0 = 1.225                  # kg/m3
OMEGA_KERBIN = 2 * math.pi / 21_549.425  # rotation, rad/s

DT = 0.05                     # pas d'integration, s

# Conversion masse -> unites KSP pour l'affichage des ergols.
LF_UNITS_PER_T = 90.0
OX_UNITS_PER_T = 110.0


class _Stage:
    """Un etage : masse a vide, ergols, poussee et Isp."""

    def __init__(self, dry_t: float, fuel_t: float, thrust_kn: float,
                 isp_sl: float, isp_vac: float) -> None:
        self.dry_t = dry_t
        self.fuel_t = fuel_t
        self.fuel_left_t = fuel_t
        self.thrust_kn = thrust_kn
        self.isp_sl = isp_sl
        self.isp_vac = isp_vac

    @property
    def total_t(self) -> float:
        return self.dry_t + self.fuel_left_t

    @property
    def full_t(self) -> float:
        return self.dry_t + self.fuel_t

    def isp(self, pressure_atm: float) -> float:
        p = max(0.0, min(1.0, pressure_atm))
        return self.isp_vac + (self.isp_sl - self.isp_vac) * p


def _default_rocket() -> list[_Stage]:
    """Un lanceur a trois etages, capable d'atteindre l'orbite de Kerbin.

    Calibre sur une fusee stock raisonnable : environ 3900 m/s de delta-v au
    total (l'orbite basse de Kerbin en demande ~3400, le reste est la marge),
    pour 14 t au decollage et un TWR initial autour de 1,45.
    """
    return [
        # etage 0 = superieur (allume en dernier)
        _Stage(dry_t=0.6, fuel_t=0.65, thrust_kn=20.0, isp_sl=250, isp_vac=320),
        _Stage(dry_t=1.5, fuel_t=2.0, thrust_kn=60.0, isp_sl=265, isp_vac=300),
        _Stage(dry_t=3.0, fuel_t=5.6, thrust_kn=200.0, isp_sl=285, isp_vac=305),
    ]


class SimSource(TelemetrySource):
    name = "sim"

    def __init__(self, auto_launch_after: float = 5.0) -> None:
        self.auto_launch_after = auto_launch_after
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.stages = _default_rocket()
        # L'etage actif est le dernier de la liste (le plus bas).
        self.active = len(self.stages) - 1

        self.alt = 0.0
        self.vx = OMEGA_KERBIN * R_KERBIN   # on tourne deja avec la planete
        self.vy = 0.0
        self.met = 0.0
        self.ut = 0.0
        self.throttle = 0.0
        self.launched = False
        self._t0 = time.monotonic()
        self._last = self._t0
        self._payload_t = 0.8   # capsule + equipage

    def connect(self) -> None:
        self.reset()

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Physique
    # ------------------------------------------------------------------
    @property
    def mass_t(self) -> float:
        m = self._payload_t
        for i, st in enumerate(self.stages):
            if i <= self.active:
                m += st.total_t
        return m

    @property
    def dry_mass_t(self) -> float:
        m = self._payload_t
        for i, st in enumerate(self.stages):
            if i <= self.active:
                m += st.dry_t
        return m

    def _pressure_atm(self) -> float:
        if self.alt >= ATMO_HEIGHT:
            return 0.0
        return math.exp(-self.alt / SCALE_HEIGHT)

    def _density(self) -> float:
        if self.alt >= ATMO_HEIGHT:
            return 0.0
        return RHO0 * math.exp(-self.alt / SCALE_HEIGHT)

    def _pitch_program(self) -> float:
        """Virage gravitationnel classique : vertical, puis bascule
        progressive jusqu'a l'horizontale vers 45 km."""
        if self.alt < 500:
            return 90.0
        if self.alt > 45_000:
            return 0.0
        frac = (self.alt - 500) / (45_000 - 500)
        return 90.0 * (1.0 - math.sqrt(frac))

    def _step(self, dt: float) -> None:
        self.ut += dt
        if not self.launched:
            if time.monotonic() - self._t0 >= self.auto_launch_after:
                self.launched = True
                self.throttle = 1.0
            else:
                return

        self.met += dt

        r = R_KERBIN + self.alt
        g = MU_KERBIN / (r * r)
        mass_kg = self.mass_t * 1000.0

        stage = self.stages[self.active] if self.active >= 0 else None
        pitch = math.radians(self._pitch_program())

        # --- Poussee ---
        thrust_n = 0.0
        if stage is not None and stage.fuel_left_t > 0 and self.throttle > 0:
            thrust_n = stage.thrust_kn * 1000.0 * self.throttle
            isp = stage.isp(self._pressure_atm())
            flow_kg_s = thrust_n / (isp * G0)
            burned_t = flow_kg_s * dt / 1000.0
            stage.fuel_left_t = max(0.0, stage.fuel_left_t - burned_t)
            if stage.fuel_left_t <= 0 and self.active > 0:
                # Largage automatique de l'etage vide.
                self.active -= 1

        ax = thrust_n * math.cos(pitch) / mass_kg
        ay = thrust_n * math.sin(pitch) / mass_kg

        # --- Trainee ---
        v = math.hypot(self.vx - OMEGA_KERBIN * r, self.vy)
        rho = self._density()
        if rho > 0 and v > 0:
            # Cd*A forfaitaire, decroissant avec le largage des etages.
            cd_a = 0.35 * (1.2 + 0.4 * self.active)
            drag_n = 0.5 * rho * v * v * cd_a
            vx_air = self.vx - OMEGA_KERBIN * r
            ax -= drag_n * (vx_air / v) / mass_kg
            ay -= drag_n * (self.vy / v) / mass_kg

        # --- Gravite et acceleration centrifuge ---
        ay += self.vx * self.vx / r - g
        ax -= self.vx * self.vy / r

        self.vx += ax * dt
        self.vy += ay * dt
        self.alt += self.vy * dt

        if self.alt < 0:
            self.alt = 0.0
            self.vy = 0.0

    # ------------------------------------------------------------------
    # Elements orbitaux depuis le vecteur d'etat
    # ------------------------------------------------------------------
    def _orbit(self) -> OrbitInfo:
        r = R_KERBIN + self.alt
        vt, vr = self.vx, self.vy
        v2 = vt * vt + vr * vr
        energy = v2 / 2.0 - MU_KERBIN / r
        h = r * vt

        if abs(energy) < 1e-9:
            return OrbitInfo(body="Kerbin")

        a = -MU_KERBIN / (2.0 * energy)
        e2 = 1.0 + 2.0 * energy * h * h / (MU_KERBIN ** 2)
        e = math.sqrt(max(0.0, e2))

        apo = a * (1 + e) - R_KERBIN
        per = a * (1 - e) - R_KERBIN
        period = 2 * math.pi * math.sqrt(a ** 3 / MU_KERBIN) if a > 0 else 0.0

        t_apo = t_per = 0.0
        if a > 0 and e < 1.0:
            # Anomalie vraie -> excentrique -> moyenne -> temps.
            cos_nu = ((a * (1 - e * e) / r) - 1.0) / e if e > 1e-9 else 1.0
            cos_nu = max(-1.0, min(1.0, cos_nu))
            nu = math.acos(cos_nu)
            if vr < 0:
                nu = 2 * math.pi - nu
            ecc_anom = 2 * math.atan2(
                math.sqrt(1 - e) * math.sin(nu / 2),
                math.sqrt(1 + e) * math.cos(nu / 2),
            )
            mean_anom = ecc_anom - e * math.sin(ecc_anom)
            t_since_per = mean_anom * period / (2 * math.pi)
            t_apo = (period / 2 - t_since_per) % period
            t_per = (period - t_since_per) % period

        return OrbitInfo(
            body="Kerbin",
            apoapsis=apo,
            periapsis=per,
            eccentricity=e,
            inclination=0.0,
            period=period,
            time_to_apoapsis=t_apo,
            time_to_periapsis=t_per,
            semi_major_axis=a,
        )

    # ------------------------------------------------------------------
    def sample(self) -> Telemetry:
        # On rattrape le temps ecoule depuis le dernier appel, par petits pas
        # pour que l'integration reste stable meme si le backend a hoquete.
        now = time.monotonic()
        elapsed = min(now - self._last, 1.0)
        self._last = now
        steps = max(1, int(elapsed / DT))
        for _ in range(steps):
            self._step(elapsed / steps)

        r = R_KERBIN + self.alt
        surface_speed = math.hypot(self.vx - OMEGA_KERBIN * r, self.vy)
        rho = self._density()
        q = 0.5 * rho * surface_speed ** 2
        mass_t = self.mass_t

        stage = self.stages[self.active] if self.active >= 0 else None
        thrust_kn = (stage.thrust_kn * self.throttle
                     if stage and stage.fuel_left_t > 0 else 0.0)
        available_kn = stage.thrust_kn if stage and stage.fuel_left_t > 0 else 0.0
        g_local = MU_KERBIN / (r * r)
        twr = available_kn / (mass_t * g_local) if mass_t > 0 else 0.0

        # --- Delta-v par etage (Tsiolkovski) ---
        stages_info: list[StageInfo] = []
        # On descend depuis le sommet : chaque etage porte la charge utile plus
        # tous les etages situes au-dessus de lui. C'est cette masse portee qui
        # determine son delta-v reel.
        carried = self._payload_t
        for i in range(0, self.active + 1):
            st = self.stages[i]
            start = carried + st.total_t
            end = carried + st.dry_t
            isp_v = st.isp_vac
            dv_vac = isp_v * G0 * math.log(start / end) if end > 0 else 0.0
            isp_now = st.isp(self._pressure_atm())
            dv_now = isp_now * G0 * math.log(start / end) if end > 0 else 0.0
            burn = (st.fuel_left_t * 1000.0 * isp_now * G0 /
                    (st.thrust_kn * 1000.0)) if st.thrust_kn > 0 else 0.0
            stages_info.append(
                StageInfo(
                    number=i,
                    delta_v=dv_now,
                    vacuum_delta_v=dv_vac,
                    twr=st.thrust_kn / (start * g_local) if start > 0 else 0.0,
                    burn_time=burn,
                    start_mass=start,
                    end_mass=end,
                )
            )
            carried += st.total_t

        # Affichage : l'etage en cours de combustion en premier.
        stages_info.reverse()

        total_dv = sum(s.delta_v for s in stages_info)
        total_dv_vac = sum(s.vacuum_delta_v for s in stages_info)

        fuel_left = sum(st.fuel_left_t for i, st in enumerate(self.stages)
                        if i <= self.active)
        fuel_full = sum(st.fuel_t for i, st in enumerate(self.stages)
                        if i <= self.active)

        orbit = self._orbit()
        situation = self._situation(orbit)

        return Telemetry(
            connected=True,
            source=self.name,
            timestamp=time.time(),
            game_scene=settings.sim_scene,
            ut=self.ut,
            met=self.met,
            vessel_name="Simulateur MC-1",
            situation=situation,
            body="Kerbin",
            crew_count=3,
            altitude=self.alt,
            surface_altitude=self.alt,
            speed=surface_speed,
            # vx est deja mesure dans le repere inertiel : la vitesse orbitale
            # est donc la norme brute, sans retrancher la rotation du sol.
            orbital_speed=math.hypot(self.vx, self.vy),
            vertical_speed=self.vy,
            g_force=(thrust_kn * 1000.0 / (mass_t * 1000.0)) / G0 if mass_t else 0.0,
            dynamic_pressure=q,
            mach=surface_speed / 340.0 if self.alt < ATMO_HEIGHT else 0.0,
            pitch=self._pitch_program(),
            heading=90.0,
            roll=0.0,
            static_pressure=P0 * self._pressure_atm(),
            atmosphere_density=rho,
            throttle=self.throttle,
            thrust=thrust_kn,
            available_thrust=available_kn,
            mass=mass_t,
            dry_mass=self.dry_mass_t,
            twr=twr,
            delta_v=total_dv,
            vacuum_delta_v=total_dv_vac,
            delta_v_available=True,
            current_stage=self.active,
            stages=stages_info,
            resources=[
                # Conversion en unites KSP : 1 unite de LiquidFuel ou
                # d'Oxidizer pese 5 kg, et le melange est de 9 volumes de
                # carburant pour 11 de comburant.
                ResourceInfo(name="LiquidFuel", amount=fuel_left * LF_UNITS_PER_T,
                             maximum=max(fuel_full * LF_UNITS_PER_T, 1e-6)),
                ResourceInfo(name="Oxidizer", amount=fuel_left * OX_UNITS_PER_T,
                             maximum=max(fuel_full * OX_UNITS_PER_T, 1e-6)),
                ResourceInfo(name="ElectricCharge", amount=180.0, maximum=200.0),
            ],
            orbit=orbit,
            comm_available=True,
            comm_can_communicate=True,
            comm_signal_strength=max(0.2, 1.0 - self.alt / 4_000_000.0),
        )

    def _situation(self, orbit: OrbitInfo) -> str:
        if not self.launched:
            return "pre_launch"
        if self.alt < 1.0:
            return "landed"
        if orbit.periapsis > ATMO_HEIGHT:
            return "orbiting"
        if self.alt < ATMO_HEIGHT:
            return "flying"
        return "sub_orbital"
