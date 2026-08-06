"""Recoupement de la fusee et de la mission.

Le VAB sait ce que la fusee emporte, le planificateur sait ce que le trajet
reclame. Les deux chiffres existaient deja, chacun dans son coin, et il fallait
les comparer de tete. Ce module les confronte :

    3 900 m/s disponibles, 5 088 necessaires pour Duna -- il manque 1 188 m/s.

La comparaison va plus loin qu'une soustraction. On cumule les etapes du plan
dans l'ordre pour dire *ou* la reserve s'epuise -- « vous atteignez l'orbite de
Kerbin, mais l'injection vers Duna est hors de portee » est une information
autrement plus actionnable qu'un total manquant.

Deux sources possibles pour le delta-v disponible, dans cet ordre :

  - le vaisseau en cours de construction, tant que l'editeur emet ;
  - a defaut, le vaisseau en vol, dont on retire alors les etapes deja
    accomplies : comparer un vaisseau en orbite a un plan qui commence par
    « decoller du sol » n'aurait aucun sens.
"""

from __future__ import annotations

import math

# En dessous de cette part du besoin, la marge est jugee trop mince : la
# moindre erreur de pilotage (ascension trop verticale, capture ratee)
# consomme cet ordre de grandeur.
MARGE_CONFORTABLE = 0.10

# Situations ou l'ascension est reellement derriere soi. Un vaisseau encore en
# "flying" ou "sub_orbital" est au milieu de sa montee : il en a paye une part
# inconnue, et lui crediter l'ascension entiere le declarerait a tort capable
# de repartir. On garde alors le plan complet -- pessimiste, mais honnete.
EN_ORBITE = ("orbiting", "escaping", "docked")

# Vitesse d'ejection en dessous de laquelle le bilan d'un etage ne veut plus
# rien dire (Isp de 153 s : moins que le plus mauvais moteur du jeu).
VE_PLAUSIBLE = 1500.0


def confronter(plan, telemetrie=None, vaisseau_vab: dict | None = None) -> dict:
    """Compare le delta-v disponible a celui qu'exige le plan.

    `plan` est un `planner.route.Plan`. Les deux autres arguments sont les deux
    sources possibles de delta-v ; on ne leve jamais si elles manquent, on
    renvoie simplement une confrontation indisponible avec sa raison.
    """
    source = _choisir_source(telemetrie, vaisseau_vab)
    if source is None:
        return {
            "disponible": False,
            "raison": (
                "Aucune fusée à comparer : construis un vaisseau dans "
                "l'éditeur, ou mets-en un en vol."
            ),
        }

    etapes, ignorees = _etapes_a_couvrir(plan, source)
    requis = math.fsum(e.delta_v for e in etapes)
    disponible = source["delta_v"]
    marge = disponible - requis

    resultat = {
        "disponible": True,
        "source": source["genre"],
        "vaisseau": source["nom"],
        "delta_v_disponible": disponible,
        "delta_v_requis": requis,
        "marge": marge,
        "marge_relative": marge / requis if requis > 0 else 0.0,
        "suffisant": marge >= 0,
        "etapes_ignorees": ignorees,
        "etape_bloquante": None,
        "suggestion": "",
    }

    if marge < 0:
        resultat["etape_bloquante"] = _etape_bloquante(etapes, disponible)
        resultat["suggestion"] = _suggestion(-marge, source.get("etages") or [])

    resultat["verdict"] = _verdict(plan, resultat)
    return resultat


# ----------------------------------------------------------------------
def _choisir_source(telemetrie, vaisseau_vab: dict | None) -> dict | None:
    """Le vaisseau en construction prime : c'est celui qu'on est en train de
    corriger, et c'est justement pour ca qu'on regarde le plan."""
    vab = vaisseau_vab or {}
    if vab.get("disponible") and (vab.get("delta_v_total_vide") or 0) > 0:
        return {
            "genre": "vab",
            "nom": vab.get("nom") or "vaisseau en construction",
            # Le delta-v sous vide est le seul comparable au plan : les cartes
            # de delta-v comptent l'ascension a part, avec ses pertes.
            "delta_v": float(vab["delta_v_total_vide"]),
            "etages": vab.get("etages") or [],
            "situation": "pre_launch",
        }

    t = telemetrie
    if (
        t is not None
        and getattr(t, "connected", False)
        and getattr(t, "game_scene", "") == "flight"
        and getattr(t, "vessel_name", "")
        and getattr(t, "delta_v_available", False)
        and getattr(t, "delta_v", 0.0) > 0
    ):
        # Le delta-v SOUS VIDE, comme pour le VAB : c'est le seul comparable a
        # un plan de mission, dont les cartes comptent l'ascension a part avec
        # ses pertes. La valeur "situation courante" vaut 30 % de moins au pas
        # de tir -- mesure faite sur le lanceur de reference : 3 357 m/s a
        # l'air libre contre 4 883 m/s sous vide.
        vide = float(getattr(t, "vacuum_delta_v", 0.0) or 0.0)
        return {
            "genre": "vol",
            "nom": t.vessel_name,
            "delta_v": vide if vide > 0 else float(t.delta_v),
            "etages": [_etage_dict(s) for s in (t.stages or [])],
            "situation": t.situation,
        }

    return None


def _etage_dict(etage) -> dict:
    """Les etages arrivent en dataclass depuis le vol, en dict depuis le VAB."""
    if isinstance(etage, dict):
        return etage
    return {
        "number": etage.number,
        "delta_v": etage.delta_v,
        "vacuum_delta_v": etage.vacuum_delta_v,
        "start_mass": etage.start_mass,
        "end_mass": etage.end_mass,
    }


def _etapes_a_couvrir(plan, source: dict) -> tuple[list, list[str]]:
    """Etapes du plan qui restent a la charge du vaisseau.

    Un vaisseau deja en vol a paye son ascension : la lui recompter ferait
    conclure a tort qu'il ne peut pas repartir.
    """
    etapes = list(plan.etapes)
    if source["genre"] != "vol" or source["situation"] not in EN_ORBITE:
        return etapes, []

    ignorees: list[str] = []
    while etapes and etapes[0].genre == "ascension":
        ignorees.append(etapes.pop(0).titre)
    return etapes, ignorees


def _etape_bloquante(etapes, disponible: float) -> dict | None:
    """Premiere etape que la reserve ne permet plus de finir."""
    cumul = 0.0
    for etape in etapes:
        cumul += etape.delta_v
        if cumul > disponible:
            return {
                "titre": etape.titre,
                "delta_v": etape.delta_v,
                "cumul": cumul,
                # Ce qu'il reste en arrivant au debut de cette etape.
                "restant": max(0.0, disponible - (cumul - etape.delta_v)),
            }
    return None


def _suggestion(manque: float, etages: list[dict]) -> str:
    """Traduit le delta-v manquant en ergols a ajouter.

    On raisonne sur l'etage superieur, celui qui porte le moins de masse : le
    delta-v y est le moins cher. Sa vitesse d'ejection se deduit de son propre
    bilan par Tsiolkovski inverse, sans avoir besoin de connaitre son Isp.

    Le chiffre est une borne basse : il ignore la masse a vide du reservoir
    ajoute et la perte de TWR. C'est un ordre de grandeur pour savoir si on
    parle d'un demi-reservoir ou d'un etage entier.
    """
    if manque <= 0:
        return ""

    # compute_stages rend les etages du plus haut numero au plus bas :
    # le dernier de la liste est l'etage superieur.
    superieur = etages[-1] if etages else None
    if not superieur:
        return f"Il manque {_milliers(manque)} m/s."

    dv = float(superieur.get("vacuum_delta_v") or superieur.get("delta_v") or 0.0)
    m0 = float(superieur.get("start_mass") or 0.0)
    m1 = float(superieur.get("end_mass") or 0.0)
    if dv <= 0 or m0 <= 0 or m1 <= 0 or m0 <= m1:
        return f"Il manque {_milliers(manque)} m/s."

    ve = dv / math.log(m0 / m1)

    # Garde-fou tire d'un essai reel : en vol, le detail par etage n'est
    # calcule qu'a la pression courante. Au pas de tir, le bilan d'un etage
    # superieur -- concu pour le vide -- donne une vitesse d'ejection de
    # 900 m/s, soit une Isp de 92 s qu'aucun moteur chimique n'atteint. La
    # formule repondait alors « 64 t d'ergols » en toute confiance.
    #
    # 1 500 m/s (Isp 153 s) est en dessous du plus mauvais moteur du jeu :
    # sous ce seuil, le chiffre ne mesure plus rien.
    if ve < VE_PLAUSIBLE:
        return (
            f"Il manque {_milliers(manque)} m/s. Le rendement de l'étage "
            f"supérieur n'est pas mesurable dans cette situation : impossible "
            f"de chiffrer les ergols à ajouter."
        )

    # Le rapport de masse doit etre multiplie par exp(manque / ve) ; a masse
    # finale inchangee, cela revient a ajouter m0 * (exp(manque/ve) - 1).
    exposant = manque / ve
    if exposant > 6:
        # Au-dela, l'ergol supplementaire depasse cent fois la masse actuelle :
        # ce n'est plus un reservoir a rajouter, c'est une autre fusee.
        return (
            f"Il manque {_milliers(manque)} m/s, hors de portée d'un simple ajout "
            f"d'ergols sur l'étage supérieur : il faut un étage de plus, ou "
            f"une escale de ravitaillement."
        )

    ergols = _decimal(m0 * math.expm1(exposant))
    return (
        f"Il manque {_milliers(manque)} m/s, soit environ {ergols} t "
        f"d'ergols de plus sur l'étage supérieur (masse des réservoirs "
        f"non comptée) — ou un étage supplémentaire."
    )


def _milliers(valeur: float) -> str:
    """Separateur de milliers a la francaise : 5 088, et non 5,088."""
    return f"{valeur:,.0f}".replace(",", " ")


def _decimal(valeur: float, decimales: int = 1) -> str:
    """Virgule decimale, comme le reste de l'interface."""
    return f"{valeur:.{decimales}f}".replace(".", ",")


def _verdict(plan, r: dict) -> str:
    """La phrase que le joueur lit en premier."""
    tete = (
        f"{_milliers(r['delta_v_disponible'])} m/s disponibles, "
        f"{_milliers(r['delta_v_requis'])} nécessaires pour {plan.arrivee}"
    )

    if not r["suffisant"]:
        phrase = f"{tete} — il manque {_milliers(-r['marge'])} m/s."
        bloquante = r["etape_bloquante"]
        if bloquante:
            phrase += (
                f" La réserve s'épuise à l'étape « {bloquante['titre']} » : "
                f"{bloquante['restant']:.0f} m/s restants pour "
                f"{bloquante['delta_v']:.0f} m/s à dépenser."
            )
        return phrase

    marge = f"{_milliers(r['marge'])} m/s ({r['marge_relative'] * 100:.0f} %)"
    if r["marge_relative"] < MARGE_CONFORTABLE:
        return f"{tete} — il ne reste que {marge} de marge, c'est très juste."
    return f"{tete} — il reste {marge} de marge."
