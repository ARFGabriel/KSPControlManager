"""Serveur web : API REST minimale + flux WebSocket de telemetrie."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import overview, planner
from .config import PROJECT_DIR, settings
from .hub import hub
from .radio.service import radio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ksp_mc")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await hub.start()
    log.info("Mission Control demarre sur http://%s:%s", settings.host, settings.port)
    yield
    await hub.stop()


app = FastAPI(title="KSP Mission Control", version="0.1.0", lifespan=lifespan)

# Le dashboard tourne sur le port de Vite pendant le developpement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "source": hub.source.name if hub.source else "none",
        "connected": hub.latest.connected,
        "configured_source": settings.source,
    }


@app.get("/api/telemetry")
async def telemetry() -> dict:
    """Dernier echantillon connu, pour un simple appel ponctuel."""
    return hub.latest.to_dict()


@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = hub.subscribe()
    try:
        # On envoie immediatement l'etat courant pour que le dashboard
        # affiche quelque chose sans attendre le prochain cycle.
        await websocket.send_json(hub.latest.to_dict())
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        log.debug("Client WebSocket deconnecte", exc_info=True)
    finally:
        hub.unsubscribe(queue)


@app.get("/api/overview")
async def api_overview() -> dict:
    """Flotte, equipage et budget, pour les pages hors vol.

    Volontairement hors du flux de telemetrie : ces donnees sont couteuses a
    lire et ne changent qu'a l'echelle de la minute.
    """
    from .telemetry.krpc_source import KrpcSource

    source = hub.source
    if not isinstance(source, KrpcSource) or source.conn is None:
        return {
            "available": False,
            "reason": "Pas de liaison avec le jeu.",
            "vessels": [],
            "crew": [],
            "warnings": [],
        }

    data = await asyncio.to_thread(overview.cached, source.conn)
    data["available"] = "error" not in data
    return data


def _connexion_jeu():
    """Connexion kRPC si le jeu est la, pour lire les vrais parametres des
    corps plutot que la table interne."""
    from .telemetry.krpc_source import KrpcSource

    source = hub.source
    if isinstance(source, KrpcSource) and source.conn is not None:
        return source.conn
    return None


@app.get("/api/planner/bodies")
async def planner_bodies() -> dict:
    catalogue = await asyncio.to_thread(planner.catalogue, _connexion_jeu())
    return {
        "source": catalogue.source,
        "bodies": [
            {
                "name": b.name,
                "parent": b.parent,
                "radius": b.radius,
                "atmosphere": b.atmosphere,
                "low_orbit": b.low_orbit(),
                "inclination": b.inclination,
                "eccentricity": b.eccentricity,
                "orbit_radius": b.orbit_radius,
            }
            for b in sorted(catalogue.bodies.values(), key=lambda x: x.orbit_radius)
        ],
    }


@app.get("/api/planner/transfer")
async def planner_transfer(
    depart: str,
    arrivee: str,
    parking_depart: float | None = None,
    parking_arrivee: float | None = None,
) -> dict:
    catalogue = await asyncio.to_thread(planner.catalogue, _connexion_jeu())
    transfert = planner.calculer(
        catalogue, depart, arrivee, parking_depart, parking_arrivee
    )
    if transfert is None:
        return {
            "possible": False,
            "raison": (
                f"Aucun transfert direct entre {depart} et {arrivee}. Le "
                f"calcul ne traite que deux corps de même parent, ou un corps "
                f"vers l'une de ses lunes."
            ),
        }

    data = asdict(transfert)
    data["possible"] = True
    data["source"] = catalogue.source
    return data


@app.get("/api/radio/status")
async def radio_status() -> dict:
    return radio.status()


@app.get("/api/radio/models")
async def radio_models() -> dict:
    """Modeles utilisables avec la cle configuree.

    Sert a sortir d'une erreur 404 sans deviner : les noms de modeles changent
    au fil des versions de l'API.
    """
    from .radio.llm.gemini import list_models

    if not settings.gemini_api_key:
        return {"error": "Aucune cle Gemini dans backend/.env"}
    try:
        return {"models": await list_models(settings.gemini_api_key)}
    except Exception as exc:
        return {"error": str(exc)}


@app.websocket("/ws/radio")
async def ws_radio(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = radio.subscribe()

    async def pump() -> None:
        """Pousse les evenements de la radio vers ce navigateur."""
        while True:
            await websocket.send_json(await queue.get())

    pumping = asyncio.create_task(pump())
    try:
        await websocket.send_json(radio.status())
        while True:
            data = await websocket.receive_json()
            kind = data.get("type")

            if kind == "send":
                text = (data.get("text") or "").strip()
                if text:
                    # En tache de fond : un appel au modele prend plusieurs
                    # secondes et ne doit pas bloquer la reception.
                    asyncio.create_task(
                        radio.send(data.get("persona", "crew"), text)
                    )
            elif kind == "confirm":
                asyncio.create_task(
                    radio.confirm(data.get("id", ""), bool(data.get("approved")))
                )
            elif kind == "reset":
                radio.reset(data.get("persona"))
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        log.debug("Client radio deconnecte", exc_info=True)
    finally:
        pumping.cancel()
        radio.unsubscribe(queue)


# --- Service du dashboard compile, s'il existe ---
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_dist / "index.html")
