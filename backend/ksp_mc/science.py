"""Science embarquee mais non transmise.

Un thermometre releve, un goo observe, et les donnees restent dans la piece
jusqu'a ce qu'on pense a les transmettre ou a les ramener. Rien dans le jeu ne
le rappelle : on decouvre la perte au moment ou le vaisseau brule.

Ce module liste les experiences qui dorment a bord du vaisseau actif, avec ce
qu'elles valent selon qu'on les transmet ou qu'on les rapporte. La difference
est loin d'etre anecdotique -- un rapport d'atterrissage ne rend qu'un tiers de
sa valeur par radio, et c'est souvent la raison pour laquelle une mission
rapporte moins que prevu.

Limite assumee : kRPC ne donne acces aux pieces que du vaisseau charge. Les
sondes lointaines ne sont donc pas inspectees. Le dire vaut mieux que laisser
croire a une revue complete de la flotte.
"""

from __future__ import annotations

import logging
import math
import time

from .telemetry.source import safe

log = logging.getLogger("ksp_mc.science")

# Lire toutes les experiences coute plusieurs appels par piece : bien trop pour
# le flux de telemetrie, et inutile a cette cadence -- une experience ne se
# declenche pas dix fois par seconde.
CACHE_S = 3.0

_cache: dict = {}
_cache_at = 0.0


def _nombre(valeur, defaut: float = 0.0) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return defaut
    return nombre if math.isfinite(nombre) else defaut


def _experience(exp) -> dict | None:
    """Resume d'une experience qui detient des donnees.

    Tout est lu defensivement : selon la piece et la version du jeu, une
    partie de ces proprietes leve au lieu de repondre.
    """
    if not safe(lambda: exp.has_data, False):
        return None

    donnees = safe(lambda: list(exp.data), []) or []
    if not donnees:
        return None

    sujet = safe(lambda: exp.science_subject)

    return {
        "piece": safe(lambda: exp.part.title, "") or "?",
        "sujet": (safe(lambda: sujet.title, "") if sujet else "") or "expérience",
        "biome": safe(lambda: exp.biome, "") or "",
        "quantite": math.fsum(_nombre(safe(lambda: d.data_amount, 0.0))
                              for d in donnees),
        # Ce que valent les donnees si on les ramene au sol.
        "science": math.fsum(_nombre(safe(lambda: d.science_value, 0.0))
                             for d in donnees),
        # Ce qu'il en reste si on les transmet par radio.
        "transmission": math.fsum(_nombre(safe(lambda: d.transmit_value, 0.0))
                                  for d in donnees),
        "reutilisable": bool(safe(lambda: exp.rerunnable, False)),
        "inoperante": bool(safe(lambda: exp.inoperable, False)),
    }


def build(conn, telemetrie=None) -> dict:
    """Inventaire des donnees non transmises du vaisseau actif."""
    vessel = safe(lambda: conn.space_center.active_vessel)
    if vessel is None:
        return {
            "disponible": False,
            "raison": "Aucun vaisseau actif.",
            "experiences": [],
        }

    experiences_brutes = safe(lambda: vessel.parts.experiments)
    if experiences_brutes is None:
        return {
            "disponible": False,
            "raison": (
                "Les expériences ne sont pas accessibles via cette version "
                "de kRPC."
            ),
            "experiences": [],
        }

    trouvees: list[dict] = []
    for exp in experiences_brutes:
        try:
            resume = _experience(exp)
        except Exception:
            # Une piece peut disparaitre entre l'enumeration et la lecture.
            continue
        if resume is not None:
            trouvees.append(resume)

    trouvees.sort(key=lambda e: e["science"], reverse=True)

    science = math.fsum(e["science"] for e in trouvees)
    transmission = math.fsum(e["transmission"] for e in trouvees)

    return {
        "disponible": True,
        "vaisseau": safe(lambda: vessel.name, ""),
        "experiences": trouvees,
        "nombre": len(trouvees),
        "science": science,
        "transmission": transmission,
        "perte_transmission": max(0.0, science - transmission),
        "message": _message(trouvees, science, transmission, telemetrie),
    }


def _message(experiences: list[dict], science: float, transmission: float,
             telemetrie) -> str:
    if not experiences:
        return "Aucune donnée scientifique en attente à bord."

    pluriel = "s" if len(experiences) > 1 else ""
    phrase = (
        f"{len(experiences)} expérience{pluriel} non transmise{pluriel} : "
        f"{science:.1f} de science à bord."
    )

    perte = science - transmission
    if perte > 0.5:
        phrase += (
            f" La transmission n'en rendrait que {transmission:.1f} — "
            f"{perte:.1f} de perdu si le vaisseau ne rentre pas."
        )

    # Sans liaison, transmettre est impossible : le rappel change de nature.
    if telemetrie is not None and getattr(telemetrie, "comm_available", False):
        if not getattr(telemetrie, "comm_can_communicate", True):
            phrase += " Pas de liaison pour l'instant : impossible d'émettre."

    return phrase


def cached(conn, telemetrie=None) -> dict:
    """Version mise en cache, comme la vue d'ensemble."""
    global _cache, _cache_at

    now = time.monotonic()
    if _cache and now - _cache_at < CACHE_S:
        return _cache

    try:
        _cache = build(conn, telemetrie)
    except Exception as exc:
        log.debug("Inventaire scientifique indisponible", exc_info=True)
        return {"disponible": False, "raison": str(exc), "experiences": []}

    _cache_at = now
    return _cache
