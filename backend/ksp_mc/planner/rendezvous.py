"""Rendez-vous avec un vaisseau existant.

Rejoindre une station coute trois choses, souvent confondues :

1. **Le changement de plan.** Si les orbites ne sont pas dans le meme plan,
   il faut tourner le vecteur vitesse, et c'est de loin le plus cher. Un
   degre d'ecart coute environ 40 m/s en orbite basse de Kerbin.
2. **Le transfert d'altitude.** Un Hohmann classique entre les deux orbites.
3. **La mise en phase.** Arriver a la bonne altitude ne suffit pas : il faut
   y arriver au moment ou la cible y passe. Cela ne coute rien en delta-v,
   seulement du temps d'attente.

Le modele suppose des orbites quasi circulaires. Sur une orbite tres
elliptique, les chiffres deviennent indicatifs et on le signale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .bodies import Body, BodyCatalog

TAU = 2 * math.pi
RAD = 180.0 / math.pi


@dataclass
class Orbite:
    """Orbite d'un engin, ramenee aux grandeurs utiles."""

    nom: str
    corps: str
    demi_grand_axe: float
    apoapside: float          # altitude
    periapside: float         # altitude
    inclinaison: float        # degres
    noeud_ascendant: float    # degres
    excentricite: float
    equipage: int = 0
    situation: str = ""


@dataclass
class PlanRendezVous:
    cible: str
    corps: str
    depuis_altitude: float
    vers_altitude: float
    delta_v_plan: float = 0.0
    delta_v_transfert: float = 0.0
    delta_v_total: float = 0.0
    inclinaison_relative: float = 0.0
    duree_transfert: float = 0.0
    attente_phase: float = 0.0
    angle_actuel: float | None = None
    angle_vise: float = 0.0
    etapes: list[dict] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def lire_orbites(conn) -> list[Orbite]:
    """Toutes les orbites exploitables de la partie.

    On ecarte ce qui est pose au sol : un debris sur la piste n'est pas une
    cible de rendez-vous, et son apoapside vaut NaN.
    """
    orbites: list[Orbite] = []
    try:
        vaisseaux = conn.space_center.vessels
    except Exception:
        return orbites

    for vaisseau in vaisseaux:
        try:
            situation = str(getattr(vaisseau.situation, "name", vaisseau.situation))
            if situation not in ("orbiting", "sub_orbital", "docked"):
                continue

            orbite = vaisseau.orbit
            apo = float(orbite.apoapsis_altitude)
            per = float(orbite.periapsis_altitude)
            if not (math.isfinite(apo) and math.isfinite(per)) or per < 0:
                continue

            orbites.append(
                Orbite(
                    nom=vaisseau.name,
                    corps=orbite.body.name,
                    demi_grand_axe=float(orbite.semi_major_axis),
                    apoapside=apo,
                    periapside=per,
                    inclinaison=float(orbite.inclination) * RAD,
                    noeud_ascendant=float(orbite.longitude_of_ascending_node) * RAD,
                    excentricite=float(orbite.eccentricity),
                    equipage=int(vaisseau.crew_count),
                    situation=situation,
                )
            )
        except Exception:
            continue

    return orbites


def angle_dans_orbite(conn, vaisseau_nom: str, corps_nom: str) -> float | None:
    """Position angulaire d'un engin autour de son corps, en degres."""
    try:
        sc = conn.space_center
        corps = sc.bodies[corps_nom]
        repere = corps.non_rotating_reference_frame
        for vaisseau in sc.vessels:
            if vaisseau.name != vaisseau_nom:
                continue
            x, _, z = vaisseau.position(repere)
            return math.degrees(math.atan2(z, x)) % 360.0
    except Exception:
        return None
    return None


def inclinaison_relative(a: Orbite, b: Orbite) -> float:
    """Angle entre les deux plans orbitaux, en degres.

    Ce n'est pas la difference des inclinaisons : deux orbites inclinees de
    30° mais de noeuds opposes forment un angle de 60°, pas de 0°.
    """
    i1 = math.radians(a.inclinaison)
    i2 = math.radians(b.inclinaison)
    d_noeud = math.radians(a.noeud_ascendant - b.noeud_ascendant)

    cos_i = (
        math.cos(i1) * math.cos(i2)
        + math.sin(i1) * math.sin(i2) * math.cos(d_noeud)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_i))))


def calculer(
    conn,
    catalog: BodyCatalog,
    cible_nom: str,
    chasseur_altitude: float | None = None,
    chasseur_nom: str | None = None,
) -> PlanRendezVous | None:
    orbites = lire_orbites(conn)
    cible = next((o for o in orbites if o.nom == cible_nom), None)
    if cible is None:
        return None

    corps = catalog.get(cible.corps)
    if corps is None:
        return None

    chasseur = next((o for o in orbites if o.nom == chasseur_nom), None)
    if chasseur is not None and chasseur.corps != cible.corps:
        chasseur = None

    if chasseur is not None:
        r_depart = chasseur.demi_grand_axe
        alt_depart = r_depart - corps.radius
    else:
        alt_depart = (
            chasseur_altitude
            if chasseur_altitude is not None
            else corps.low_orbit()
        )
        r_depart = corps.radius + alt_depart

    r_cible = cible.demi_grand_axe
    alt_cible = r_cible - corps.radius

    plan = PlanRendezVous(
        cible=cible_nom,
        corps=cible.corps,
        depuis_altitude=alt_depart,
        vers_altitude=alt_cible,
    )

    # --- Changement de plan ---
    if chasseur is not None:
        i_rel = inclinaison_relative(chasseur, cible)
    else:
        # Depuis une orbite qu'on choisit, autant se caler d'emblee dans le
        # plan de la cible : le changement de plan devient gratuit.
        i_rel = 0.0
    plan.inclinaison_relative = i_rel

    if i_rel > 0.05:
        # On le fait a la plus haute des deux altitudes : la vitesse y est
        # plus faible, donc le virage moins cher.
        r_manoeuvre = max(r_depart, r_cible)
        v = math.sqrt(corps.mu / r_manoeuvre)
        dv_plan = 2.0 * v * math.sin(math.radians(i_rel) / 2.0)
        plan.delta_v_plan = dv_plan
        plan.etapes.append({
            "titre": "Alignement des plans orbitaux",
            "delta_v": dv_plan,
            "detail": (
                f"{i_rel:.2f}° d'ecart, corrige au noeud a "
                f"{(r_manoeuvre - corps.radius) / 1000:.0f} km"
            ),
        })

    # --- Transfert de Hohmann ---
    a_transfert = (r_depart + r_cible) / 2.0
    v1 = math.sqrt(corps.mu / r_depart)
    v_depart = math.sqrt(corps.mu * (2.0 / r_depart - 1.0 / a_transfert))
    v2 = math.sqrt(corps.mu / r_cible)
    v_arrivee = math.sqrt(corps.mu * (2.0 / r_cible - 1.0 / a_transfert))

    dv1 = abs(v_depart - v1)
    dv2 = abs(v2 - v_arrivee)
    plan.delta_v_transfert = dv1 + dv2
    plan.duree_transfert = math.pi * math.sqrt(a_transfert ** 3 / corps.mu)

    if dv1 > 0.05:
        plan.etapes.append({
            "titre": f"Poussee de transfert vers {alt_cible / 1000:.0f} km",
            "delta_v": dv1,
            "detail": f"depuis {alt_depart / 1000:.0f} km",
        })
    if dv2 > 0.05:
        plan.etapes.append({
            "titre": "Circularisation au contact",
            "delta_v": dv2,
            "detail": "annule la vitesse relative avec la cible",
        })

    plan.delta_v_total = plan.delta_v_plan + plan.delta_v_transfert

    # --- Mise en phase ---
    omega_cible = math.sqrt(corps.mu / r_cible ** 3)
    plan.angle_vise = math.degrees(math.pi - omega_cible * plan.duree_transfert) % 360

    angle_cible = angle_dans_orbite(conn, cible_nom, cible.corps)
    angle_chasseur = (
        angle_dans_orbite(conn, chasseur_nom, cible.corps) if chasseur_nom else None
    )
    if angle_cible is not None and angle_chasseur is not None:
        actuel = (angle_cible - angle_chasseur) % 360.0
        plan.angle_actuel = actuel

        t_chasseur = TAU * math.sqrt(r_depart ** 3 / corps.mu)
        t_cible = TAU * math.sqrt(r_cible ** 3 / corps.mu)
        vitesse = 360.0 / t_cible - 360.0 / t_chasseur
        if abs(vitesse) > 1e-12:
            if vitesse > 0:
                ecart = (plan.angle_vise - actuel) % 360.0
            else:
                ecart = (actuel - plan.angle_vise) % 360.0
            plan.attente_phase = ecart / abs(vitesse)

    # --- Avertissements ---
    if cible.excentricite > 0.05:
        plan.avertissements.append(
            f"L'orbite de {cible_nom} est elliptique (e = {cible.excentricite:.3f}) : "
            f"les chiffres deviennent indicatifs, le rendez-vous demandera des "
            f"corrections."
        )
    if i_rel > 1.0:
        plan.avertissements.append(
            f"{i_rel:.1f}° d'ecart de plan : c'est le poste le plus cher du "
            f"rendez-vous. Lancer directement dans le plan de la cible "
            f"l'eviterait entierement."
        )
    if chasseur is None:
        plan.avertissements.append(
            "Aucun vaisseau poursuivant selectionne : le calcul part d'une "
            "orbite de stationnement supposee deja dans le plan de la cible."
        )

    return plan
