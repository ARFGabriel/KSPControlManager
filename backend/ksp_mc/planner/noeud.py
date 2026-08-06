"""Pose automatique de noeuds de manoeuvre dans le jeu.

Le planificateur sait deja *quoi* faire et *quand*. Ce module franchit le pas
suivant : il ecrit la manoeuvre directement dans la partie, pour eviter le
reglage a la souris qui est la partie la plus ingrate du jeu.

Portee volontairement limitee a ce qui est exact : un transfert de Hohmann
depuis l'orbite actuelle vers celle d'une cible tournant autour du meme corps.
Cela couvre les lunes et les rendez-vous avec un vaisseau, c'est-a-dire
l'essentiel des manoeuvres du quotidien.

Les transferts interplanetaires ne sont PAS poses : leur poussee doit avoir
lieu a un angle d'ejection precis, faute de quoi on part dans la mauvaise
direction. Annoncer un noeud approximatif serait pire que de ne rien poser.
"""

from __future__ import annotations

import math

TAU = 2 * math.pi


def _angle(conn, objet, repere) -> float | None:
    """Longitude d'un objet dans le plan orbital, en degres."""
    try:
        x, _, z = objet.position(repere)
        return math.degrees(math.atan2(z, x)) % 360.0
    except Exception:
        return None


def planifier(conn, cible_nom: str) -> dict:
    """Calcule le noeud de transfert vers `cible_nom` sans le poser.

    La cible peut etre un corps celeste ou un vaisseau, du moment qu'elle
    tourne autour du meme corps que nous.
    """
    sc = conn.space_center
    vaisseau = sc.active_vessel
    if vaisseau is None:
        return {"possible": False, "raison": "Aucun vaisseau actif."}

    orbite = vaisseau.orbit
    corps = orbite.body

    cible = _trouver_cible(sc, cible_nom)
    if cible is None:
        return {"possible": False,
                "raison": f"Cible « {cible_nom} » introuvable."}

    try:
        corps_cible = cible.orbit.body
    except Exception:
        return {"possible": False,
                "raison": f"« {cible_nom} » n'a pas d'orbite exploitable."}

    if corps_cible.name != corps.name:
        return {
            "possible": False,
            "raison": (
                f"« {cible_nom} » tourne autour de {corps_cible.name} et non de "
                f"{corps.name}. Seuls les transferts autour du meme corps sont "
                f"poses automatiquement : un depart interplanetaire demande un "
                f"angle d'ejection precis, qu'il vaut mieux regler a la main."
            ),
        }

    mu = corps.gravitational_parameter
    r1 = orbite.semi_major_axis
    r2 = cible.orbit.semi_major_axis
    if r1 <= 0 or r2 <= 0:
        return {"possible": False, "raison": "Orbites illisibles."}

    # --- Transfert de Hohmann depuis notre orbite vers celle de la cible ---
    a_transfert = (r1 + r2) / 2.0
    v1 = math.sqrt(mu / r1)
    v_depart = math.sqrt(mu * (2.0 / r1 - 1.0 / a_transfert))
    delta_v = v_depart - v1
    duree = math.pi * math.sqrt(a_transfert ** 3 / mu)

    # --- Angle de phase vise, puis moment ou il sera atteint ---
    omega_cible = math.sqrt(mu / r2 ** 3)
    vise = math.degrees(math.pi - omega_cible * duree) % 360.0

    repere = corps.non_rotating_reference_frame
    angle_nous = _angle(conn, vaisseau, repere)
    angle_cible = _angle(conn, cible, repere)
    if angle_nous is None or angle_cible is None:
        return {"possible": False, "raison": "Positions illisibles."}

    actuel = (angle_cible - angle_nous) % 360.0

    t_nous = TAU * math.sqrt(r1 ** 3 / mu)
    t_cible = TAU * math.sqrt(r2 ** 3 / mu)
    vitesse = 360.0 / t_cible - 360.0 / t_nous   # degres par seconde
    if abs(vitesse) < 1e-12:
        return {"possible": False,
                "raison": "Orbites de meme periode : aucun rendez-vous possible."}

    if vitesse > 0:
        ecart = (vise - actuel) % 360.0
    else:
        ecart = (actuel - vise) % 360.0
    attente = ecart / abs(vitesse)

    ut = sc.ut + attente

    return {
        "possible": True,
        "cible": cible_nom,
        "corps": corps.name,
        "delta_v": delta_v,
        "ut": ut,
        "attente": attente,
        "duree_transfert": duree,
        "angle_actuel": actuel,
        "angle_vise": vise,
        "altitude_depart": r1 - corps.equatorial_radius,
        "altitude_cible": r2 - corps.equatorial_radius,
    }


def poser(conn, cible_nom: str) -> dict:
    """Calcule puis ecrit le noeud dans la partie."""
    plan = planifier(conn, cible_nom)
    if not plan.get("possible"):
        return plan

    vaisseau = conn.space_center.active_vessel

    # Un vaisseau sans controle n'accepte aucun noeud, et le jeu ne l'explique
    # pas : il ignore simplement la demande.
    etat = str(getattr(vaisseau.control.state, "name", vaisseau.control.state))
    if etat == "none":
        plan["possible"] = False
        plan["raison"] = (
            "Le vaisseau n'est pas controlable : ni equipage, ni electricite. "
            "Aucun noeud ne peut etre pose."
        )
        return plan

    try:
        noeud = vaisseau.control.add_node(plan["ut"], prograde=plan["delta_v"])
    except Exception as exc:
        plan["possible"] = False
        plan["raison"] = f"Le jeu a refuse le noeud : {exc}"
        return plan

    plan["pose"] = True
    plan["delta_v_reel"] = float(noeud.delta_v)
    return plan


def effacer(conn) -> int:
    """Retire tous les noeuds du vaisseau actif. Renvoie le nombre retire."""
    try:
        vaisseau = conn.space_center.active_vessel
        noeuds = list(vaisseau.control.nodes)
        for n in noeuds:
            n.remove()
        return len(noeuds)
    except Exception:
        return 0


def cibles_possibles(conn) -> list[dict]:
    """Corps et vaisseaux atteignables par un transfert direct depuis ici."""
    sortie: list[dict] = []
    try:
        sc = conn.space_center
        vaisseau = sc.active_vessel
        if vaisseau is None:
            return sortie
        corps = vaisseau.orbit.body

        for nom, astre in sc.bodies.items():
            try:
                if astre.orbit is not None and astre.orbit.body.name == corps.name:
                    sortie.append({"nom": nom, "genre": "corps"})
            except Exception:
                continue

        for autre in sc.vessels:
            try:
                if autre.name == vaisseau.name:
                    continue
                if autre.orbit.body.name != corps.name:
                    continue
                if not math.isfinite(autre.orbit.apoapsis_altitude):
                    continue
                sortie.append({"nom": autre.name, "genre": "vaisseau"})
            except Exception:
                continue
    except Exception:
        pass
    return sortie


def _trouver_cible(sc, nom: str):
    corps = sc.bodies.get(nom)
    if corps is not None:
        return corps
    for vaisseau in sc.vessels:
        if vaisseau.name == nom:
            return vaisseau
    return None
