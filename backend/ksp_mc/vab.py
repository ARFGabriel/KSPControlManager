"""Reception des donnees du VAB, emises par le mod dans le jeu.

kRPC n'expose pas d'API d'editeur : c'est le mod qui pousse ici le contenu du
vaisseau en construction. On ne recoit que la matiere premiere -- pieces,
masses, moteurs, ergols -- et on la fait passer dans le moteur de delta-v
deja ecrit et valide pour le vol. Un second calcul en C# aurait fini par
diverger du premier.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict

from .telemetry.deltav import EngineInfo, PartInfo, compute_stages, total_delta_v

log = logging.getLogger("ksp_mc.vab")

# Au-dela, on considere que le joueur a quitte l'editeur.
PEREMPTION_S = 15.0

_dernier: dict | None = None
_recu_a: float = 0.0
# Charge brute conservee telle qu'envoyee par le mod. Sert au diagnostic :
# sans elle, un calcul faux est indissociable d'une emission fausse.
_brut: dict | None = None


def enregistrer(charge: dict) -> None:
    """Stocke le vaisseau recu et en deduit le detail par etage."""
    global _dernier, _recu_a, _brut

    _brut = charge
    pieces, densites = _convertir(charge)
    etage_courant = int(charge.get("etage_courant", 0))

    # Conduites de carburant : sans elles, un lanceur en asparagus comme la
    # Kerbal X est incalculable. Chaque groupe de propulseurs brulerait dans
    # son coin au lieu d'alimenter le coeur.
    lignes = [
        (int(l.get("de", -1)), int(l.get("vers", -1)))
        for l in charge.get("lignes_ergol", []) or []
        if l.get("de") is not None and l.get("vers") is not None
    ]
    lignes = [(a, b) for a, b in lignes if a >= 0 and b >= 0]

    # On calcule les deux situations plutot que d'en choisir une : le premier
    # etage travaille dans l'air, les suivants sous vide, et afficher un seul
    # chiffre trompe dans un cas ou dans l'autre.
    try:
        etages = compute_stages(pieces, densites, etage_courant,
                                vacuum=False, lignes_ergol=lignes)
        sous_vide = compute_stages(pieces, densites, etage_courant,
                                   vacuum=True, lignes_ergol=lignes)
    except Exception:
        log.debug("Calcul de delta-v impossible sur le vaisseau du VAB", exc_info=True)
        etages, sous_vide = [], []

    dv_vide = {e.number: e.delta_v for e in sous_vide}
    for etage in etages:
        etage.vacuum_delta_v = dv_vide.get(etage.number, 0.0)

    masse_totale = sum(
        p.dry_mass + sum(u * densites.get(n, 0.0) for n, u in p.resources.items())
        for p in pieces
    )
    masse_seche = sum(p.dry_mass for p in pieces)

    _dernier = {
        "nom": charge.get("nom", ""),
        "description": charge.get("description", ""),
        "nombre_pieces": charge.get("nombre_pieces", 0),
        "etage_courant": etage_courant,
        "masse": masse_totale / 1000.0,
        "masse_seche": masse_seche / 1000.0,
        "etages": [asdict(e) for e in etages],
        "delta_v_total": total_delta_v(etages),
        "delta_v_total_vide": total_delta_v(sous_vide),
        "avertissements": _controler(charge, pieces, densites, etages),
        "ressources": _resume_ressources(pieces, densites),
    }
    _recu_a = time.monotonic()


def _controler(charge: dict, pieces, densites, etages) -> list[str]:
    """Defauts de conception qui condamnent une mission.

    Chacun de ces controles vient d'une panne reellement rencontree : une
    sonde devenue debris faute de production electrique, un vaisseau muet
    faute d'antenne, un lanceur trop lourd pour decoller.
    """
    eq = charge.get("equipements") or {}
    avertissements: list[str] = []

    charge_elec = sum(
        p.resources.get("ElectricCharge", 0.0) for p in pieces
    )
    production = eq.get("panneaux_solaires", 0) + eq.get("generateurs", 0)

    if charge_elec > 0 and production == 0:
        detail = ""
        if eq.get("alternateurs", 0) > 0:
            detail = (" Les alternateurs des moteurs ne comptent pas : ils ne "
                      "produisent que moteur allume.")
        avertissements.append(
            f"Aucune production electrique pour {charge_elec:.0f} unites de "
            f"batterie. Une fois vides, plus aucun controle -- le vaisseau "
            f"devient un debris irrecuperable.{detail}"
        )

    if eq.get("antennes", 0) == 0:
        avertissements.append(
            "Aucune antenne : pas de transmission scientifique, et une sonde "
            "sans equipage sera hors liaison."
        )

    if eq.get("places_equipage", 0) > 0 and eq.get("parachutes", 0) == 0:
        avertissements.append(
            f"{eq['places_equipage']} place(s) d'equipage mais aucun parachute : "
            f"pas de retour possible."
        )

    if etages:
        premier = etages[0]
        if 0 < premier.twr < 1.1:
            avertissements.append(
                f"TWR de {premier.twr:.2f} au decollage : trop juste pour "
                f"monter correctement, viser au moins 1,2."
            )
        elif premier.twr >= 1.1 and premier.twr > 2.5:
            avertissements.append(
                f"TWR de {premier.twr:.2f} au decollage : tres eleve, une "
                f"partie de la poussee sera perdue en trainee."
            )

    return avertissements


def brut() -> dict:
    """Derniere charge recue, sans transformation."""
    return _brut or {"vide": True}


def dernier() -> dict:
    """Dernier vaisseau recu, ou un etat vide s'il est perime.

    Sans peremption, la page continuerait d'afficher une fusee que le joueur
    a quittee il y a dix minutes, ce qui est pire qu'une page vide.
    """
    if _dernier is None:
        return {
            "disponible": False,
            "raison": (
                "Aucune donnee du VAB. Entre dans l'editeur avec le mod "
                "installe pour que le vaisseau soit transmis."
            ),
        }

    if time.monotonic() - _recu_a > PEREMPTION_S:
        return {
            "disponible": False,
            "raison": "Plus de donnees recentes de l'editeur.",
            "dernier_connu": _dernier.get("nom", ""),
        }

    data = dict(_dernier)
    data["disponible"] = True
    data["age"] = time.monotonic() - _recu_a
    return data


# ----------------------------------------------------------------------
def _convertir(charge: dict) -> tuple[list[PartInfo], dict[str, float]]:
    """Traduit la charge JSON du mod vers les structures du moteur de delta-v."""
    pieces: list[PartInfo] = []
    densites: dict[str, float] = {}

    for brut in charge.get("pieces", []) or []:
        ressources: dict[str, float] = {}
        for r in brut.get("ressources", []) or []:
            nom = r.get("nom", "")
            quantite = float(r.get("quantite", 0.0) or 0.0)
            if not nom or quantite <= 0:
                continue
            ressources[nom] = quantite
            densites.setdefault(nom, float(r.get("densite", 0.0) or 0.0))

        moteur = None
        brut_moteur = brut.get("moteur")
        if brut_moteur:
            ergols = {
                e.get("nom", ""): float(e.get("ratio", 1.0) or 1.0)
                for e in brut_moteur.get("ergols", []) or []
                if e.get("nom")
            }
            poussee = float(brut_moteur.get("poussee_max", 0.0) or 0.0)
            isp_vide = float(brut_moteur.get("isp_vide", 0.0) or 0.0)
            isp_sol = float(brut_moteur.get("isp_sol", 0.0) or 0.0)
            # ModuleEngines.maxThrust est la poussee SOUS VIDE. Au niveau de
            # la mer, elle chute dans le meme rapport que l'impulsion
            # specifique -- c'est la relation qu'utilise le jeu, et elle se
            # verifie exactement :
            #   RE-M3   1500 x 285/310 = 1379 kN
            #   LV-T45   215 x 250/320 =  168 kN
            #   RE-L10   250 x  90/350 = 64,3 kN
            # Sans cette conversion, le TWR d'un moteur de vide au decollage
            # est surestime d'un facteur quatre, et la duree de combustion
            # divisee d'autant.
            poussee_sol = (
                poussee * (isp_sol / isp_vide) if isp_vide > 0 and isp_sol > 0
                else poussee
            )

            moteur = EngineInfo(
                stage=int(brut.get("etage", -1)),
                max_thrust=poussee_sol,
                max_vacuum_thrust=poussee,
                isp=isp_sol or isp_vide,
                vacuum_isp=isp_vide or isp_sol,
                propellants=ergols,
                solid="SolidFuel" in ergols,
            )

        pieces.append(
            PartInfo(
                index=int(brut.get("index", len(pieces))),
                dry_mass=float(brut.get("masse_seche", 0.0) or 0.0),
                stage=int(brut.get("etage", -1)),
                decouple_stage=int(brut.get("etage_decouplage", -1)),
                resources=ressources,
                engine=moteur,
            )
        )

    return pieces, densites


def _resume_ressources(pieces, densites) -> list[dict]:
    totaux: dict[str, float] = {}
    for piece in pieces:
        for nom, quantite in piece.resources.items():
            totaux[nom] = totaux.get(nom, 0.0) + quantite
    return [
        {"nom": nom, "quantite": q, "masse": q * densites.get(nom, 0.0) / 1000.0}
        for nom, q in sorted(totaux.items())
    ]
