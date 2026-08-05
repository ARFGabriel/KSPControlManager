"""Donnees physiques et orbitales des corps du systeme.

Deux sources, dans cet ordre :

1. le jeu lui-meme, via kRPC. C'est la source de verite : elle reste juste
   si tu installes un jour Realism Overhaul ou tout mod qui redimensionne le
   systeme. Les valeurs sont mises en cache sur disque des la premiere
   connexion.
2. une table interne, pour pouvoir planifier sans lancer KSP. Elle contient
   les valeurs du systeme stock, et le planificateur signale toujours d'ou
   viennent les chiffres qu'il utilise.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import BACKEND_DIR

log = logging.getLogger("ksp_mc.planner")

CACHE = BACKEND_DIR / "donnees" / "corps.json"


@dataclass
class Body:
    name: str
    parent: str | None
    mu: float                 # m3/s2, parametre gravitationnel
    radius: float             # m, rayon equatorial
    soi: float                # m, sphere d'influence (0 pour l'etoile)
    orbit_radius: float       # m, demi-grand axe autour du parent
    atmosphere: float         # m, altitude de fin d'atmosphere (0 si aucune)
    rotational_period: float  # s
    # Ces deux-la ne servent pas au calcul : le modele de Hohmann suppose des
    # orbites circulaires et coplanaires. Elles servent a AVERTIR quand cette
    # hypothese est fausse, plutot que de livrer un chiffre trompeur.
    # Valeurs par defaut pour rester compatible avec un cache plus ancien.
    inclination: float = 0.0   # degres
    eccentricity: float = 0.0

    @property
    def has_atmosphere(self) -> bool:
        return self.atmosphere > 0

    def low_orbit(self) -> float:
        """Altitude d'une orbite basse raisonnable : juste au-dessus de
        l'atmosphere, ou du relief pour un corps sans air."""
        if self.has_atmosphere:
            return self.atmosphere + 10_000
        # Marge pour les reliefs : le Mun culmine a environ 7 km.
        return max(10_000, self.radius * 0.02)

    def orbital_period(self, parent_mu: float) -> float:
        if self.orbit_radius <= 0 or parent_mu <= 0:
            return 0.0
        return 2 * math.pi * math.sqrt(self.orbit_radius ** 3 / parent_mu)

    def circular_speed(self, altitude: float) -> float:
        return math.sqrt(self.mu / (self.radius + altitude))


# ----------------------------------------------------------------------
# Table de secours : systeme stock de KSP 1.12
# ----------------------------------------------------------------------
# Ces valeurs servent uniquement quand le jeu n'est pas joignable. Elles sont
# ecrasees des la premiere connexion a kRPC.
STOCK: dict[str, Body] = {
    b.name: b
    for b in [
        # Valeurs confrontees au jeu reel : seuls la couronne du Soleil et la
        # sphere d'influence d'Eeloo etaient fausses, elles sont corrigees ici.
        Body("Sun", None, 1.1723328e18, 261_600_000, 0, 0, 600_000, 432_000),
        Body("Moho", "Sun", 1.6860938e11, 250_000, 9_646_663, 5_263_138_304, 0, 1_210_000, 7.0, 0.200),
        Body("Eve", "Sun", 8.1717302e12, 700_000, 85_109_365, 9_832_684_544, 90_000, 80_500, 2.1, 0.010),
        Body("Gilly", "Eve", 8.2894498e6, 13_000, 126_123, 31_500_000, 0, 28_255, 12.0, 0.550),
        Body("Kerbin", "Sun", 3.5316000e12, 600_000, 84_159_286, 13_599_840_256, 70_000, 21_549, 0.0, 0.000),
        Body("Mun", "Kerbin", 6.5138398e10, 200_000, 2_429_559, 12_000_000, 0, 138_984, 0.0, 0.000),
        Body("Minmus", "Kerbin", 1.7658000e9, 60_000, 2_247_428, 47_000_000, 0, 40_400, 6.0, 0.000),
        Body("Duna", "Sun", 3.0136321e11, 320_000, 47_921_949, 20_726_155_264, 50_000, 65_517, 0.06, 0.051),
        Body("Ike", "Duna", 1.8568369e10, 130_000, 1_049_599, 3_200_000, 0, 65_517, 0.2, 0.030),
        Body("Dres", "Sun", 2.1484489e10, 138_000, 32_832_840, 40_839_348_203, 0, 34_800, 5.0, 0.145),
        Body("Jool", "Sun", 2.8252800e14, 6_000_000, 2_455_985_200, 68_773_560_320, 200_000, 36_000, 1.304, 0.050),
        Body("Laythe", "Jool", 1.9620000e12, 500_000, 3_723_646, 27_184_000, 50_000, 52_981, 0.0, 0.000),
        Body("Vall", "Jool", 2.0748150e11, 300_000, 2_406_401, 43_152_000, 0, 105_962, 0.0, 0.000),
        Body("Tylo", "Jool", 2.8252800e12, 600_000, 10_856_518, 68_500_000, 0, 211_926, 0.025, 0.000),
        Body("Bop", "Jool", 2.4868349e9, 65_000, 1_221_061, 128_500_000, 0, 544_507, 15.0, 0.235),
        Body("Pol", "Jool", 7.2170208e8, 44_000, 1_042_139, 179_890_000, 0, 901_903, 4.25, 0.171),
        Body("Eeloo", "Sun", 7.4410815e10, 210_000, 119_082_942, 90_118_820_000, 0, 19_460, 6.15, 0.260),
    ]
}


class BodyCatalog:
    """Ensemble des corps connus, avec l'origine des donnees."""

    def __init__(self, bodies: dict[str, Body], source: str) -> None:
        self.bodies = bodies
        self.source = source  # "jeu" | "cache" | "table interne"

    def get(self, name: str) -> Body | None:
        return self.bodies.get(name)

    def parent_of(self, body: Body) -> Body | None:
        return self.bodies.get(body.parent) if body.parent else None

    def names(self) -> list[str]:
        return sorted(self.bodies)

    def star(self) -> Body | None:
        for body in self.bodies.values():
            if body.parent is None:
                return body
        return None

    def to_json(self) -> dict:
        return {
            "source": self.source,
            "bodies": {n: asdict(b) for n, b in self.bodies.items()},
        }


# ----------------------------------------------------------------------
def from_game(conn) -> BodyCatalog:
    """Lit tout le systeme depuis kRPC et le met en cache."""
    bodies: dict[str, Body] = {}

    for name, body in conn.space_center.bodies.items():
        try:
            orbit = body.orbit
            parent = orbit.body.name if orbit is not None else None
            bodies[name] = Body(
                name=name,
                parent=parent,
                mu=body.gravitational_parameter,
                radius=body.equatorial_radius,
                soi=body.sphere_of_influence if parent else 0.0,
                orbit_radius=orbit.semi_major_axis if orbit is not None else 0.0,
                atmosphere=body.atmosphere_depth if body.has_atmosphere else 0.0,
                rotational_period=body.rotational_period,
                inclination=(
                    math.degrees(orbit.inclination) if orbit is not None else 0.0
                ),
                eccentricity=orbit.eccentricity if orbit is not None else 0.0,
            )
        except Exception:
            log.debug("Corps %s illisible", name, exc_info=True)
            continue

    catalog = BodyCatalog(bodies, "jeu")
    _sauver(catalog)
    return catalog


def _sauver(catalog: BodyCatalog) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(
            json.dumps(catalog.to_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Donnees des corps mises en cache (%d corps)", len(catalog.bodies))
    except Exception:
        log.debug("Cache des corps non ecrit", exc_info=True)


def from_cache() -> BodyCatalog | None:
    if not CACHE.is_file():
        return None
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        bodies = {n: Body(**b) for n, b in data["bodies"].items()}
        return BodyCatalog(bodies, "cache")
    except Exception:
        log.debug("Cache des corps illisible", exc_info=True)
        return None


def load(conn=None) -> BodyCatalog:
    """Meilleure source disponible, du plus fiable au plus approximatif."""
    if conn is not None:
        try:
            return from_game(conn)
        except Exception:
            log.debug("Lecture des corps depuis le jeu impossible", exc_info=True)

    cached = from_cache()
    if cached is not None:
        return cached

    return BodyCatalog(dict(STOCK), "table interne")
