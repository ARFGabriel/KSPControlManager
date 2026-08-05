"""Vue d'ensemble du programme spatial, hors vol.

Alimente les pages Centre spatial et Station de suivi. Ces donnees n'ont rien
a faire dans le flux de telemetrie a 10 Hz : lister toute la flotte demande
plusieurs appels par vaisseau, et ces chiffres ne bougent qu'a l'echelle de la
minute. On les interroge donc a la demande, avec un cache court.

Tout est lu defensivement : selon le mode de partie (bac a sable, science,
carriere), les fonds ou la reputation n'existent pas, et les proprietes
correspondantes levent au lieu de renvoyer zero.
"""

from __future__ import annotations

import logging
import time

from .telemetry.source import safe

log = logging.getLogger("ksp_mc.overview")

CACHE_S = 3.0
_cache: dict = {}
_cache_at = 0.0

RAD_TO_DEG = 57.29577951308232


def _vessel_entry(vessel) -> dict:
    """Resume d'un vaisseau pour la liste de flotte."""
    orbit = safe(lambda: vessel.orbit)
    body = safe(lambda: orbit.body.name, "") if orbit else ""

    return {
        "name": safe(lambda: vessel.name, "?"),
        "type": _enum(safe(lambda: vessel.type)),
        "situation": _enum(safe(lambda: vessel.situation)),
        "body": body,
        "crew_count": safe(lambda: vessel.crew_count, 0),
        "met": safe(lambda: vessel.met, 0.0),
        "apoapsis": safe(lambda: orbit.apoapsis_altitude, 0.0) if orbit else 0.0,
        "periapsis": safe(lambda: orbit.periapsis_altitude, 0.0) if orbit else 0.0,
        "inclination": (safe(lambda: orbit.inclination, 0.0) * RAD_TO_DEG) if orbit else 0.0,
        "period": safe(lambda: orbit.period, 0.0) if orbit else 0.0,
    }


def _crew_entry(kerbal) -> dict:
    return {
        "name": safe(lambda: kerbal.name, "?"),
        "type": _enum(safe(lambda: kerbal.type)),
        "trait": safe(lambda: kerbal.trait, ""),
        "experience": safe(lambda: kerbal.experience_level, 0),
        "courage": safe(lambda: kerbal.courage, 0.0),
        "stupidity": safe(lambda: kerbal.stupidity, 0.0),
        "on_mission": safe(lambda: kerbal.on_mission, False),
    }


def build(conn) -> dict:
    """Construit la vue d'ensemble. Ne leve pas : chaque bloc est isole."""
    sc = conn.space_center

    data: dict = {
        "ut": safe(lambda: sc.ut, 0.0),
        # Ces trois-la n'existent qu'en mode carriere ou science.
        "funds": safe(lambda: sc.funds),
        "science": safe(lambda: sc.science),
        "reputation": safe(lambda: sc.reputation),
        "vessels": [],
        "crew": [],
        "warnings": [],
    }

    vessels = safe(lambda: sc.vessels, []) or []
    for vessel in vessels:
        try:
            data["vessels"].append(_vessel_entry(vessel))
        except Exception:
            # Un vaisseau peut disparaitre entre l'enumeration et la lecture.
            continue

    # Le roster d'equipage n'est pas expose par toutes les versions de kRPC :
    # on le signale plutot que de laisser une page vide sans explication.
    crew = safe(lambda: sc.crew)
    if crew is None:
        data["warnings"].append(
            "Le roster d'equipage n'est pas accessible via cette version de kRPC."
        )
    else:
        for kerbal in crew:
            try:
                data["crew"].append(_crew_entry(kerbal))
            except Exception:
                continue

    return data


def cached(conn) -> dict:
    """Version mise en cache : plusieurs onglets ouverts n'interrogent pas le
    jeu plusieurs fois par seconde."""
    global _cache, _cache_at

    now = time.monotonic()
    if _cache and now - _cache_at < CACHE_S:
        return _cache

    try:
        _cache = build(conn)
    except Exception as exc:
        log.debug("Vue d'ensemble indisponible", exc_info=True)
        return {"error": str(exc), "vessels": [], "crew": [], "warnings": []}

    _cache_at = now
    return _cache


def _enum(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "name", value))
