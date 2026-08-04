"""Schema de telemetrie partage entre la source kRPC et le simulateur.

Toutes les valeurs sont normalisees dans des unites "humaines" ici :
kRPC renvoie des kg et des newtons, on expose des tonnes et des kilonewtons,
comme l'affichage du jeu. La conversion se fait une seule fois, a la source,
pour que le dashboard n'ait jamais a s'en preoccuper.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class OrbitInfo:
    body: str = ""
    apoapsis: float = 0.0            # m au-dessus du sol
    periapsis: float = 0.0           # m au-dessus du sol
    eccentricity: float = 0.0
    inclination: float = 0.0         # degres
    period: float = 0.0              # s
    time_to_apoapsis: float = 0.0    # s
    time_to_periapsis: float = 0.0   # s
    semi_major_axis: float = 0.0     # m


@dataclass
class StageInfo:
    number: int = 0
    delta_v: float = 0.0             # m/s, situation courante
    vacuum_delta_v: float = 0.0      # m/s
    twr: float = 0.0
    burn_time: float = 0.0           # s
    start_mass: float = 0.0          # tonnes
    end_mass: float = 0.0            # tonnes


@dataclass
class ResourceInfo:
    name: str = ""
    amount: float = 0.0
    maximum: float = 0.0

    @property
    def fraction(self) -> float:
        return self.amount / self.maximum if self.maximum > 0 else 0.0


@dataclass
class Telemetry:
    """Un echantillon complet de l'etat du vaisseau."""

    # --- meta ---
    connected: bool = False
    source: str = "none"             # "krpc" | "sim"
    error: str | None = None
    timestamp: float = 0.0           # horloge murale du backend
    ut: float = 0.0                  # temps universel du jeu
    met: float = 0.0                 # temps ecoule depuis le decollage
    game_scene: str = ""             # flight, space_center, editor_vab...

    # --- identite ---
    vessel_name: str = ""
    situation: str = ""              # pre_launch, flying, orbiting, landed...
    body: str = ""
    crew_count: int = 0

    # --- vol ---
    altitude: float = 0.0            # m au-dessus du niveau de la mer
    surface_altitude: float = 0.0    # m au-dessus du relief
    # Deux vitesses, comme la navball du jeu. La vitesse surface est mesuree
    # dans le repere tournant avec le corps : elle n'a de sens qu'a basse
    # altitude. En orbite ou en interplanetaire, seule l'orbitale est valable.
    speed: float = 0.0               # m/s, relative a la surface
    orbital_speed: float = 0.0       # m/s, repere non tournant
    vertical_speed: float = 0.0      # m/s
    g_force: float = 0.0
    dynamic_pressure: float = 0.0    # Pa
    mach: float = 0.0
    pitch: float = 0.0               # degres
    heading: float = 0.0             # degres
    roll: float = 0.0                # degres
    static_pressure: float = 0.0     # Pa
    atmosphere_density: float = 0.0  # kg/m3

    # --- propulsion ---
    throttle: float = 0.0            # 0..1
    thrust: float = 0.0              # kN
    available_thrust: float = 0.0    # kN
    mass: float = 0.0                # tonnes
    dry_mass: float = 0.0            # tonnes
    twr: float = 0.0
    delta_v: float = 0.0             # m/s, total, situation courante
    vacuum_delta_v: float = 0.0      # m/s, total
    # KSP ne calcule pas toujours le delta-v (affichage desactive, vaisseau
    # sans moteur, vaisseau tout juste charge). On distingue explicitement
    # "indisponible" de "zero" : afficher 0 m/s serait un mensonge.
    delta_v_available: bool = False
    current_stage: int = 0

    # --- detail ---
    stages: list[StageInfo] = field(default_factory=list)
    resources: list[ResourceInfo] = field(default_factory=list)
    orbit: OrbitInfo | None = None

    # --- liaison ---
    # comm_available distingue "CommNet desactive ou vaisseau sans antenne"
    # de "liaison coupee". La radio devra s'appuyer la-dessus : sans CommNet,
    # pas de contrainte de signal a simuler.
    comm_available: bool = False
    comm_can_communicate: bool = True
    comm_signal_strength: float = 1.0   # 0..1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
