"""Rappels de fenetre de tir.

Le planificateur sait qu'une fenetre pour Duna s'ouvre au Jour 222. Cette
information ne vaut que si elle revient d'elle-meme au bon moment : personne ne
rouvre le planificateur tous les dix jours pour verifier.

Un rappel est donc une note posee sur le calendrier du jeu. Le backend la
compare au temps universel courant et dit ou l'on en est. Rien n'est declenche
automatiquement -- on previent, on n'agit pas.

Les rappels vivent dans un fichier a cote du catalogue des corps : ils doivent
survivre a un redemarrage du backend, sinon ils ne servent a rien pour une
fenetre situee a deux cents jours.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time

from .config import BACKEND_DIR
from .planner.window import JOUR, date_kerbale, duree_lisible

log = logging.getLogger("ksp_mc.rappels")

FICHIER = BACKEND_DIR / "donnees" / "rappels.json"

# Seuils d'approche, en secondes de jeu.
PROCHE_S = 10 * JOUR      # on commence a en parler
IMMINENT_S = 1 * JOUR     # il faut preparer le vaisseau maintenant

# Passe ce delai apres l'heure, un rappel non renouvelable est considere comme
# perime plutot que d'etre affiche indefiniment.
OUBLI_S = 30 * JOUR

_verrou = threading.Lock()
_rappels: list[dict] | None = None


# ----------------------------------------------------------------------
# Persistance
# ----------------------------------------------------------------------
def _charger() -> list[dict]:
    global _rappels
    if _rappels is not None:
        return _rappels

    _rappels = []
    if FICHIER.is_file():
        try:
            contenu = json.loads(FICHIER.read_text(encoding="utf-8"))
            if isinstance(contenu, list):
                _rappels = [r for r in contenu if isinstance(r, dict)]
        except Exception:
            log.warning("Fichier de rappels illisible, on repart a vide",
                        exc_info=True)
    return _rappels


def _ecrire() -> None:
    try:
        FICHIER.parent.mkdir(parents=True, exist_ok=True)
        FICHIER.write_text(
            json.dumps(_rappels or [], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        log.warning("Impossible d'ecrire les rappels", exc_info=True)


# ----------------------------------------------------------------------
# API du module
# ----------------------------------------------------------------------
def ajouter(
    depart: str,
    arrivee: str,
    ut_depart: float,
    periode_synodique: float = 0.0,
    note: str = "",
) -> dict:
    """Pose un rappel sur une date du calendrier du jeu."""
    if not math.isfinite(ut_depart) or ut_depart < 0:
        raise ValueError("Date de depart invalide.")

    with _verrou:
        rappels = _charger()
        rappel = {
            "id": f"{int(time.time() * 1000):x}",
            "depart": depart,
            "arrivee": arrivee,
            "ut_depart": float(ut_depart),
            "periode_synodique": float(periode_synodique or 0.0),
            "note": note,
        }
        # Un seul rappel par trajet : reposer le meme remplace l'ancien plutot
        # que d'empiler deux dates pour la meme destination.
        rappels[:] = [
            r for r in rappels
            if not (r.get("depart") == depart and r.get("arrivee") == arrivee)
        ]
        rappels.append(rappel)
        _ecrire()
    return rappel


def supprimer(identifiant: str) -> bool:
    with _verrou:
        rappels = _charger()
        avant = len(rappels)
        rappels[:] = [r for r in rappels if r.get("id") != identifiant]
        if len(rappels) != avant:
            _ecrire()
            return True
    return False


def lister(ut_courant: float) -> dict:
    """Rappels enrichis de leur situation par rapport a la date du jeu.

    `ut_courant` vient de la partie en cours. Sans lui (jeu ferme), on renvoie
    les rappels bruts : mieux vaut une liste sans echeance qu'une echeance
    calculee sur un temps universel nul, qui annoncerait toutes les fenetres
    comme depassees.
    """
    connu = math.isfinite(ut_courant) and ut_courant > 0

    with _verrou:
        rappels = list(_charger())
        # Une fenetre manquee n'est pas perdue : elle revient a chaque periode
        # synodique. On avance la date plutot que de laisser un rappel mort.
        modifie = False
        if connu:
            for r in rappels:
                if _renouveler(r, ut_courant):
                    modifie = True
        if modifie:
            _ecrire()

    resultat = [_situer(r, ut_courant, connu) for r in rappels]
    resultat.sort(key=lambda r: r["attente"] if r["attente"] >= 0 else 1e18)

    return {
        "ut": ut_courant if connu else 0.0,
        "date_actuelle": date_kerbale(ut_courant)["texte"] if connu else "—",
        "rappels": resultat,
        # Ce que le bandeau doit montrer : les fenetres qui approchent.
        "a_signaler": [r for r in resultat if r["proche"]],
    }


# ----------------------------------------------------------------------
def _renouveler(rappel: dict, ut: float) -> bool:
    """Reporte une fenetre passee a sa prochaine occurrence. Modifie en place."""
    periode = float(rappel.get("periode_synodique") or 0.0)
    depart = float(rappel.get("ut_depart") or 0.0)
    if periode <= 0 or depart >= ut:
        return False

    tours = math.ceil((ut - depart) / periode)
    rappel["ut_depart"] = depart + tours * periode
    rappel["renouvele"] = True
    return True


def _situer(rappel: dict, ut: float, connu: bool) -> dict:
    depart_ut = float(rappel.get("ut_depart") or 0.0)
    attente = depart_ut - ut if connu else -1.0

    data = dict(rappel)
    data["date_depart"] = date_kerbale(depart_ut)
    data["attente"] = attente
    data["attente_texte"] = duree_lisible(attente) if attente > 0 else "—"
    data["proche"] = connu and 0 <= attente <= PROCHE_S
    data["imminent"] = connu and 0 <= attente <= IMMINENT_S
    data["passee"] = connu and attente < 0
    data["oubliee"] = connu and attente < -OUBLI_S

    if not connu:
        data["message"] = (
            f"Fenêtre {rappel.get('depart', '?')} → {rappel.get('arrivee', '?')} : "
            f"{data['date_depart']['texte']}. Lance le jeu pour connaître le "
            f"temps restant."
        )
    elif data["imminent"] and attente >= 0:
        data["message"] = (
            f"Fenêtre pour {rappel.get('arrivee', '?')} dans "
            f"{data['attente_texte']} ({data['date_depart']['texte']}). "
            f"C'est maintenant qu'il faut être en orbite."
        )
    elif data["passee"]:
        data["message"] = (
            f"Fenêtre pour {rappel.get('arrivee', '?')} passée depuis "
            f"{duree_lisible(-attente)}."
        )
    else:
        data["message"] = (
            f"Fenêtre pour {rappel.get('arrivee', '?')} dans "
            f"{data['attente_texte']} ({data['date_depart']['texte']})."
        )

    return data
