"""Mecanique des transferts entre corps.

Modele : transfert de Hohmann entre orbites circulaires coplanaires, puis
coniques raccordees pour l'ejection et la capture. C'est exactement le modele
qu'utilisent les cartes de delta-v de KSP, et il donne des chiffres a quelques
pour cent de la realite du jeu.

Ce qu'il ne modelise pas, et qu'il faut garder en tete :
  - l'inclinaison relative des orbites (Moho et Eeloo en souffrent),
  - l'excentricite des orbites de depart et d'arrivee,
  - les assistances gravitationnelles,
  - l'aerofreinage, qui peut supprimer presque toute la capture sur Eve, Duna
    ou Jool.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .bodies import Body, BodyCatalog

TAU = 2 * math.pi


@dataclass
class Burn:
    """Une manoeuvre du plan de vol."""

    label: str
    delta_v: float           # m/s
    note: str = ""


@dataclass
class Transfer:
    depart: str
    arrivee: str
    parent: str
    # Orbites de stationnement utilisees pour le calcul
    parking_depart: float    # m d'altitude
    parking_arrivee: float   # m d'altitude

    delta_v_ejection: float = 0.0
    delta_v_capture: float = 0.0
    delta_v_total: float = 0.0
    duree_transfert: float = 0.0    # s
    angle_de_phase: float = 0.0     # degres
    periode_synodique: float = 0.0  # s
    burns: list[Burn] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def hohmann(mu: float, r1: float, r2: float) -> tuple[float, float, float]:
    """Transfert de Hohmann entre deux orbites circulaires de rayons r1 et r2.

    Renvoie (dv au depart, dv a l'arrivee, duree du transfert).
    Les deux delta-v sont exprimes dans le repere du corps central : ce sont
    des variations de vitesse heliocentrique, pas encore le cout reel depuis
    une orbite de stationnement.
    """
    a_transfert = (r1 + r2) / 2.0

    v1 = math.sqrt(mu / r1)
    v_depart = math.sqrt(mu * (2.0 / r1 - 1.0 / a_transfert))

    v2 = math.sqrt(mu / r2)
    v_arrivee = math.sqrt(mu * (2.0 / r2 - 1.0 / a_transfert))

    duree = math.pi * math.sqrt(a_transfert ** 3 / mu)
    return abs(v_depart - v1), abs(v2 - v_arrivee), duree


def angle_de_phase(mu: float, r1: float, r2: float) -> float:
    """Angle cible - depart, en degres, au moment ou il faut allumer.

    Pendant la moitie de periode du transfert, la cible parcourt un certain
    angle ; on part quand il lui reste exactement de quoi arriver au
    rendez-vous. Un angle negatif signifie que la cible doit etre en arriere,
    ce qui est le cas pour un voyage vers l'interieur du systeme.
    """
    _, _, duree = hohmann(mu, r1, r2)
    omega_cible = math.sqrt(mu / r2 ** 3)
    angle = math.pi - omega_cible * duree
    return math.degrees(_normaliser(angle))


def periode_synodique(mu: float, r1: float, r2: float) -> float:
    """Temps entre deux fenetres de tir successives."""
    t1 = TAU * math.sqrt(r1 ** 3 / mu)
    t2 = TAU * math.sqrt(r2 ** 3 / mu)
    if abs(t1 - t2) < 1e-9:
        return math.inf
    return abs(1.0 / (1.0 / t1 - 1.0 / t2))


def delta_v_ejection(corps: Body, altitude: float, v_infini: float) -> float:
    """Cout reel pour quitter une orbite de stationnement.

    C'est l'effet Oberth : partir du fond du puits de gravite coute bien moins
    cher que la difference de vitesse heliocentrique ne le laisse croire.
    """
    r = corps.radius + altitude
    v_circulaire = math.sqrt(corps.mu / r)
    v_necessaire = math.sqrt(v_infini ** 2 + 2.0 * corps.mu / r)
    return v_necessaire - v_circulaire


def delta_v_capture(corps: Body, altitude: float, v_infini: float) -> float:
    """Cout pour se satelliser en arrivant avec une vitesse residuelle."""
    return delta_v_ejection(corps, altitude, v_infini)


def calculer(
    catalog: BodyCatalog,
    depart: str,
    arrivee: str,
    parking_depart: float | None = None,
    parking_arrivee: float | None = None,
) -> Transfer | None:
    """Transfert complet entre deux corps.

    Deux topologies sont traitees, car elles ne coutent pas la meme chose :

    - **corps freres** (Kerbin vers Duna, Mun vers Minmus) : on quitte une
      orbite autour du corps de depart, donc l'effet Oberth s'applique et
      l'ejection coute bien moins que la difference de vitesse orbitale.
    - **corps central vers sa lune** (Kerbin vers Mun) : on est deja en orbite
      autour du corps central, la manoeuvre est un simple Hohmann sans
      ejection de puits de gravite.
    """
    corps_depart = catalog.get(depart)
    corps_arrivee = catalog.get(arrivee)
    if corps_depart is None or corps_arrivee is None:
        return None

    freres = (
        corps_depart.parent is not None
        and corps_depart.parent == corps_arrivee.parent
    )
    vers_lune = corps_arrivee.parent == corps_depart.name

    if not freres and not vers_lune:
        return None

    parent = catalog.get(corps_depart.parent) if freres else corps_depart
    if parent is None:
        return None

    alt_depart = (
        parking_depart if parking_depart is not None else corps_depart.low_orbit()
    )
    alt_arrivee = (
        parking_arrivee if parking_arrivee is not None else corps_arrivee.low_orbit()
    )

    if freres:
        r1 = corps_depart.orbit_radius
        r2 = corps_arrivee.orbit_radius
        v_inf_depart, v_inf_arrivee, duree = hohmann(parent.mu, r1, r2)
        # On part du fond du puits de gravite du corps de depart.
        dv_ejection = delta_v_ejection(corps_depart, alt_depart, v_inf_depart)
    else:
        # Le rayon de depart est celui de l'orbite de stationnement, pas celui
        # d'une orbite planetaire.
        r1 = corps_depart.radius + alt_depart
        r2 = corps_arrivee.orbit_radius
        v_inf_depart, v_inf_arrivee, duree = hohmann(parent.mu, r1, r2)
        # Deja en orbite autour du corps central : la poussee de depart est
        # directement le delta-v du transfert.
        dv_ejection = v_inf_depart

    dv_capture = delta_v_capture(corps_arrivee, alt_arrivee, v_inf_arrivee)

    transfert = Transfer(
        depart=depart,
        arrivee=arrivee,
        parent=parent.name,
        parking_depart=alt_depart,
        parking_arrivee=alt_arrivee,
        delta_v_ejection=dv_ejection,
        delta_v_capture=dv_capture,
        delta_v_total=dv_ejection + dv_capture,
        duree_transfert=duree,
        angle_de_phase=angle_de_phase(parent.mu, r1, r2),
        periode_synodique=periode_synodique(parent.mu, r1, r2),
        burns=[
            Burn(
                f"Injection depuis l'orbite de {depart}",
                dv_ejection,
                f"depuis une orbite a {alt_depart / 1000:.0f} km",
            ),
            Burn(
                f"Capture autour de {arrivee}",
                dv_capture,
                f"vers une orbite a {alt_arrivee / 1000:.0f} km",
            ),
        ],
    )

    if corps_arrivee.has_atmosphere:
        transfert.avertissements.append(
            f"{arrivee} a une atmosphere : un aerofreinage peut supprimer une "
            f"grande partie des {dv_capture:.0f} m/s de capture."
        )

    # Le modele suppose des orbites circulaires et coplanaires. Quand ce n'est
    # pas le cas, on le dit : sur Moho, l'ecart avec la realite du jeu depasse
    # 20 %, et livrer le chiffre sans reserve serait trompeur.
    for corps in (corps_depart, corps_arrivee):
        if corps.name == parent.name:
            continue
        if corps.inclination >= 1.0:
            transfert.avertissements.append(
                f"L'orbite de {corps.name} est inclinee de "
                f"{corps.inclination:.1f}° : il faudra un plan de changement "
                f"d'inclinaison, non compte ici."
            )
        if corps.eccentricity >= 0.05:
            transfert.avertissements.append(
                f"L'orbite de {corps.name} est excentrique "
                f"(e = {corps.eccentricity:.2f}) : le coût réel varie selon le "
                f"moment de l'année, l'estimation ci-dessus est une moyenne."
            )

    return transfert


def _normaliser(angle: float) -> float:
    """Ramene un angle dans [-pi, pi]."""
    while angle > math.pi:
        angle -= TAU
    while angle < -math.pi:
        angle += TAU
    return angle


def normaliser_degres(angle: float) -> float:
    """Ramene un angle dans [0, 360)."""
    return angle % 360.0
