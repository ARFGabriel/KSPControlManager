"""Serveur web : API REST minimale + flux WebSocket de telemetrie."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_DIR, settings
from .hub import hub

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


# --- Service du dashboard compile, s'il existe ---
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_dist / "index.html")
