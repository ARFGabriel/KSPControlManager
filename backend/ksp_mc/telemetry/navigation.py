"""Aide a la navigation : quoi faire, quand, et dans quelle direction.

Ce module ne pilote rien. Il calcule ce qu'un pilote automatique executerait,
et se contente de l'afficher -- ce qui en fait aussi le banc d'essai de
l'autopilote a venir : si les consignes sont bonnes a l'oeil, elles seront
bonnes a l'execution.

Trois familles d'aide :

  - le **noeud de manoeuvre** : combien de temps de poussee, quand l'allumer
    (une combustion se centre sur le noeud, donc on part a la moitie avant),
    et de combien on s'ecarte de la direction visee ;
  - la **circularisation** : ce qu'il faudra depenser a l'apoapside pour
    fermer l'orbite, calcule a tout instant ;
  - l'**ascension** : l'assiette a tenir selon l'altitude, et l'ecart avec
    l'assiette reelle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G0 = 9.80665


@dataclass
class Guidage:
    phase: str = ""              # au sol, ascension, satellisation, orbite...
    consigne: str = ""           # une phrase, ce qu'il faut faire maintenant

    # --- Noeud de manoeuvre ---
    noeud: bool = False
    noeud_delta_v: float = 0.0       # m/s restants
    noeud_temps: float = 0.0         # s avant le noeud
    noeud_duree: float = 0.0         # s de poussee
    noeud_allumage: float = 0.0      # s avant d'allumer
    ecart_attitude: float = 0.0      # degres entre le nez et la direction visee

    # --- Circularisation ---
    circularisation_dv: float = 0.0
    circularisation_duree: float = 0.0

    # --- Ascension ---
    assiette_cible: float = 0.0
    assiette_ecart: float = 0.0

    alertes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Briques de calcul
# ----------------------------------------------------------------------
def duree_poussee(delta_v: float, masse: float, poussee: float, isp: float) -> float:
    """Duree d'une poussee, par l'equation de Tsiolkovski inversee.

    Une simple division delta_v / acceleration serait fausse : le vaisseau
    s'allege en brulant, donc accelere de plus en plus.
    """
    if delta_v <= 0 or masse <= 0 or poussee <= 0 or isp <= 0:
        return 0.0
    ve = isp * G0
    debit = poussee / ve
    masse_finale = masse * math.exp(-delta_v / ve)
    return (masse - masse_finale) / debit


def circularisation(mu: float, rayon_corps: float, apoapside: float,
                    demi_grand_axe: float) -> float:
    """Delta-v pour rendre l'orbite circulaire a l'apoapside."""
    r = rayon_corps + apoapside
    if r <= 0 or demi_grand_axe <= 0 or mu <= 0:
        return 0.0
    # Vitesse actuelle a l'apoapside, puis vitesse circulaire visee.
    sous_racine = mu * (2.0 / r - 1.0 / demi_grand_axe)
    if sous_racine <= 0:
        return 0.0
    return math.sqrt(mu / r) - math.sqrt(sous_racine)


def assiette_ascension(altitude: float, fin_virage: float = 45_000.0) -> float:
    """Assiette a tenir pendant un virage gravitationnel.

    Vertical au decollage, puis bascule progressive vers l'horizontale. La
    racine carree donne une bascule rapide au debut et douce ensuite, ce qui
    correspond a un profil d'ascension economique.
    """
    if altitude < 500:
        return 90.0
    if altitude >= fin_virage:
        return 0.0
    fraction = (altitude - 500.0) / (fin_virage - 500.0)
    return 90.0 * (1.0 - math.sqrt(fraction))


def angle_entre(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Angle entre deux vecteurs, en degres."""
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    cos = sum(x * y for x, y in zip(a, b)) / (na * nb)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


# ----------------------------------------------------------------------
# Assemblage
# ----------------------------------------------------------------------
def phase_de_vol(situation: str, altitude: float, atmosphere: float,
                 periapside: float, vitesse_verticale: float) -> str:
    """Phase de vol, deduite de la situation et de la trajectoire.

    L'ordre des tests compte : une vitesse verticale faible n'est pas une
    rentree. Au decollage elle est quasi nulle pendant une seconde, ce qui
    suffisait a annoncer une rentree atmospherique sur le pas de tir.
    """
    if situation in ("landed", "splashed", "pre_launch"):
        return "au sol"
    if situation == "docked":
        return "amarre"
    if periapside > atmosphere:
        return "en orbite"
    if altitude >= atmosphere:
        # Hors de l'air mais sans orbite fermee : trajectoire balistique.
        return "satellisation"
    if vitesse_verticale < -20:
        return "rentree"
    return "ascension"


def construire(
    telemetrie,
    mu: float,
    rayon_corps: float,
    atmosphere: float,
    noeud: dict | None = None,
) -> Guidage:
    """Assemble le guidage a partir de la telemetrie et du corps survole."""
    g = Guidage()
    t = telemetrie

    orbite = t.orbit
    g.phase = phase_de_vol(
        t.situation, t.altitude, atmosphere,
        orbite.periapsis if orbite else -1e9, t.vertical_speed,
    )

    # --- Circularisation ---
    if orbite is not None and orbite.apoapsis > atmosphere:
        g.circularisation_dv = circularisation(
            mu, rayon_corps, orbite.apoapsis, orbite.semi_major_axis
        )
        g.circularisation_duree = duree_poussee(
            g.circularisation_dv, t.mass * 1000.0,
            t.available_thrust * 1000.0, _isp(t),
        )

    # --- Ascension ---
    if g.phase == "ascension":
        g.assiette_cible = assiette_ascension(t.altitude)
        g.assiette_ecart = t.pitch - g.assiette_cible

    # --- Noeud de manoeuvre ---
    if noeud:
        g.noeud = True
        g.noeud_delta_v = noeud.get("delta_v", 0.0)
        g.noeud_temps = noeud.get("temps", 0.0)
        g.ecart_attitude = noeud.get("ecart", 0.0)
        g.noeud_duree = duree_poussee(
            g.noeud_delta_v, t.mass * 1000.0,
            t.available_thrust * 1000.0, _isp(t),
        )
        # Une poussee se centre sur le noeud : on part a la moitie avant.
        g.noeud_allumage = g.noeud_temps - g.noeud_duree / 2.0

    g.consigne = _consigne(g, t, atmosphere)
    _alerter(g, t)
    return g


def _isp(t) -> float:
    """Impulsion specifique du vaisseau, deduite si elle n'est pas fournie."""
    isp = getattr(t, "specific_impulse", 0.0) or 0.0
    return isp if isp > 0 else 300.0


def _consigne(g: Guidage, t, atmosphere: float) -> str:
    if g.noeud:
        if g.noeud_allumage > 5:
            return (f"Manoeuvre dans {_duree(g.noeud_temps)} : allumage dans "
                    f"{_duree(g.noeud_allumage)}, {g.noeud_duree:.0f} s de poussee.")
        if g.noeud_allumage > -1:
            return f"Allumage maintenant, {g.noeud_duree:.0f} s de poussee."
        return f"Poussee en cours, {g.noeud_delta_v:.0f} m/s restants."

    if g.phase == "au sol":
        return "Au sol. Prevoir un cap de 90° pour une orbite equatoriale."

    if g.phase == "ascension":
        ecart = g.assiette_ecart
        if abs(ecart) < 3:
            return f"Ascension conforme, assiette {g.assiette_cible:.0f}°."
        sens = "trop haut" if ecart > 0 else "trop bas"
        return (f"Assiette {sens} de {abs(ecart):.0f}° : viser "
                f"{g.assiette_cible:.0f}°.")

    if g.phase == "satellisation":
        if g.circularisation_dv <= 0:
            return "Trajectoire balistique : pousser pour lever l'apoapside."
        if g.circularisation_duree <= 0:
            # Une duree nulle ne veut pas dire instantane : elle veut dire
            # qu'aucun moteur ne peut pousser.
            return (f"Circularisation impossible : {g.circularisation_dv:.0f} m/s "
                    f"necessaires, mais aucune poussee disponible.")
        return (f"Apoapside hors atmosphere. Circulariser a l'apoapside : "
                f"{g.circularisation_dv:.0f} m/s, "
                f"{g.circularisation_duree:.0f} s de poussee.")

    if g.phase == "en orbite":
        return "Orbite stable. Poser un noeud de manoeuvre pour la suite."

    if g.phase == "rentree":
        return "Rentree atmospherique. Retrograde, et laisser l'air freiner."

    return ""


def _alerter(g: Guidage, t) -> None:
    if t.twr < 1.0 and g.phase in ("au sol", "ascension"):
        g.alertes.append(
            f"TWR de {t.twr:.2f} : insuffisant pour monter, il en faut plus de 1."
        )
    if t.g_force > 6:
        g.alertes.append(f"{t.g_force:.1f} g : au-dela de ce qu'un kerbal encaisse bien.")
    if t.dynamic_pressure > 40_000:
        g.alertes.append(
            f"Pression dynamique de {t.dynamic_pressure / 1000:.0f} kPa : "
            f"risque de rupture, reduire les gaz."
        )
    if g.noeud and t.available_thrust <= 0:
        g.alertes.append("Manoeuvre prevue mais aucune poussee disponible.")


def _duree(secondes: float) -> str:
    if not math.isfinite(secondes):
        return "—"
    if secondes < 0:
        return "maintenant"
    if secondes < 60:
        return f"{secondes:.0f} s"
    minutes, reste = divmod(int(secondes), 60)
    if minutes < 60:
        return f"{minutes}:{reste:02d}"
    heures, minutes = divmod(minutes, 60)
    return f"{heures}:{minutes:02d}:{reste:02d}"
