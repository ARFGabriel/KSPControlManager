"""Fenetres de tir : quand partir, a partir de la date actuelle en jeu.

Un angle de phase theorique ne sert a rien tant qu'on ne sait pas quand il
sera atteint. Ce module lit la position reelle des corps dans la partie en
cours et en deduit la date du prochain depart.

Le calcul est purement geometrique : on connait l'angle vise, l'angle actuel,
et la vitesse a laquelle l'ecart se resorbe. Il n'y a pas d'optimisation fine
ici -- pas de recherche de la fenetre la moins couteuse sur plusieurs annees,
seulement le prochain alignement de Hohmann.
"""

from __future__ import annotations

import math

from .bodies import Body, BodyCatalog

# Calendrier kerbal.
JOUR = 6 * 3600
ANNEE = 426 * JOUR


def angle_orbital(conn, corps_nom: str, parent_nom: str) -> float | None:
    """Longitude du corps dans le plan orbital de son parent, en degres.

    KSP oriente ses reperes avec l'axe y vers le nord : le plan orbital est
    donc (x, z), et non (x, y) comme on l'ecrirait spontanement.
    """
    try:
        sc = conn.space_center
        parent = sc.bodies[parent_nom]
        corps = sc.bodies[corps_nom]
        x, _, z = corps.position(parent.non_rotating_reference_frame)
        return math.degrees(math.atan2(z, x)) % 360.0
    except Exception:
        return None


def periode(corps: Body, parent: Body) -> float:
    if corps.orbit_radius <= 0 or parent.mu <= 0:
        return 0.0
    return 2 * math.pi * math.sqrt(corps.orbit_radius ** 3 / parent.mu)


def prochaine_fenetre(
    conn,
    catalog: BodyCatalog,
    depart: str,
    arrivee: str,
    angle_vise: float,
) -> dict | None:
    """Temps d'attente avant le prochain alignement, en secondes.

    Renvoie None si les positions ne sont pas lisibles -- typiquement quand le
    jeu n'est pas lance. Mieux vaut ne rien afficher qu'une date inventee.
    """
    corps_d = catalog.get(depart)
    corps_a = catalog.get(arrivee)
    if corps_d is None or corps_a is None:
        return None

    # Cas d'une lune du corps de depart : l'angle de phase se mesure depuis le
    # vaisseau en orbite, pas depuis un corps. Comme il boucle en une demi-heure,
    # l'occasion revient en permanence -- annoncer une date n'aurait pas de sens,
    # on donne la recurrence.
    if corps_a.parent == depart:
        return _fenetre_recurrente(conn, corps_d, corps_a)

    if corps_d.parent != corps_a.parent or corps_d.parent is None:
        return None

    parent = catalog.get(corps_d.parent)
    if parent is None:
        return None

    angle_d = angle_orbital(conn, depart, parent.name)
    angle_a = angle_orbital(conn, arrivee, parent.name)
    if angle_d is None or angle_a is None:
        return None

    actuel = (angle_a - angle_d) % 360.0
    vise = angle_vise % 360.0

    t_d = periode(corps_d, parent)
    t_a = periode(corps_a, parent)
    if t_d <= 0 or t_a <= 0:
        return None

    # Vitesse a laquelle l'angle de phase evolue, en degres par seconde.
    vitesse = 360.0 / t_a - 360.0 / t_d
    if abs(vitesse) < 1e-12:
        return None

    if vitesse > 0:
        ecart = (vise - actuel) % 360.0
    else:
        ecart = (actuel - vise) % 360.0

    attente = ecart / abs(vitesse)
    periode_synodique = 360.0 / abs(vitesse)

    try:
        ut = conn.space_center.ut
    except Exception:
        return None

    return {
        "angle_actuel": actuel,
        "angle_vise": vise,
        "attente": attente,
        "ut_depart": ut + attente,
        "ut_actuel": ut,
        "periode_synodique": periode_synodique,
        "date_depart": date_kerbale(ut + attente),
        "date_actuelle": date_kerbale(ut),
    }


def _fenetre_recurrente(conn, corps: Body, lune: Body, altitude: float = 100_000.0) -> dict:
    """Cas d'un depart vers une lune : on donne la periodicite, pas une date.

    Depuis une orbite de stationnement, le vaisseau rattrape sans cesse la
    position angulaire de la lune. L'opportunite revient a chaque tour, ce qui
    se compte en dizaines de minutes.
    """
    r_park = corps.radius + altitude
    t_vaisseau = 2 * math.pi * math.sqrt(r_park ** 3 / corps.mu)
    t_lune = periode(lune, corps)

    vitesse = abs(360.0 / t_vaisseau - 360.0 / t_lune)
    synodique = 360.0 / vitesse if vitesse > 0 else 0.0

    try:
        ut = conn.space_center.ut
    except Exception:
        ut = 0.0

    return {
        "recurrente": True,
        "periode_synodique": synodique,
        "ut_actuel": ut,
        "date_actuelle": date_kerbale(ut),
        "note": (
            f"Depuis une orbite a {altitude / 1000:.0f} km, l'alignement avec "
            f"{lune.name} revient toutes les {duree_lisible(synodique)}. "
            f"Il n'y a pas de fenetre a attendre : il suffit de viser le bon "
            f"angle de phase au bon moment de l'orbite."
        ),
    }


def date_kerbale(ut: float) -> dict:
    """Convertit un temps universel en date du calendrier kerbal.

    Une journee fait 6 heures, une annee 426 jours. Le jeu compte a partir de
    l'annee 1, jour 1.
    """
    if not math.isfinite(ut) or ut < 0:
        return {"annee": 0, "jour": 0, "heure": 0, "minute": 0, "texte": "—"}

    annee = int(ut // ANNEE) + 1
    reste = ut % ANNEE
    jour = int(reste // JOUR) + 1
    dans_le_jour = reste % JOUR
    heure = int(dans_le_jour // 3600)
    minute = int((dans_le_jour % 3600) // 60)

    return {
        "annee": annee,
        "jour": jour,
        "heure": heure,
        "minute": minute,
        "texte": f"Année {annee}, Jour {jour} — {heure}h{minute:02d}",
    }


def duree_lisible(secondes: float) -> str:
    if not math.isfinite(secondes) or secondes < 0:
        return "—"
    jours = secondes / JOUR
    if jours < 1:
        return f"{secondes / 3600:.1f} h"
    if jours < 426:
        return f"{jours:.0f} jours"
    return f"{jours / 426:.1f} années ({jours:.0f} j)"
