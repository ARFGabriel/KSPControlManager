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

    # --- identite ---
    vessel_name: str = ""
    situation: str = ""              # pre_launch, flying, orbiting, landed...
    body: str = ""
    crew_count: int = 0

    # --- vol ---
    altitude: float = 0.0            # m au-dessus du niveau de la mer
    surface_altitude: float = 0.0    # m au-dessus du relief
    speed: float = 0.0               # m/s
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
    current_stage: int = 0

    # --- detail ---
    stages: list[StageInfo] = field(default_factory=list)
    resources: list[ResourceInfo] = field(default_factory=list)
    orbit: OrbitInfo | None = None

    # --- liaison ---
    comm_can_communicate: bool = True
    comm_signal_strength: float = 1.0   # 0..1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
