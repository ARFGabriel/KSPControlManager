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

from . import overview, planner, vab
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


@app.get("/api/planner/plan")
async def planner_plan(
    depart: str,
    arrivee: str,
    depuis_surface: bool = False,
    vers_surface: bool = False,
    parking_depart: float | None = None,
    parking_arrivee: float | None = None,
    escale: str | None = None,
) -> dict:
    """Plan de mission complet : itineraire, etapes, dates de depart.

    `escale` est le nom d'un engin existant ou l'on s'arrete avant de repartir.
    """
    conn = _connexion_jeu()

    def travail() -> dict:
        from .planner import rendezvous as rdv

        catalogue = planner.catalogue(conn)

        orbite_escale = None
        if escale and conn is not None:
            orbite_escale = next(
                (o for o in rdv.lire_orbites(conn) if o.nom == escale), None
            )

        plan = planner.construire(
            catalogue,
            depart,
            arrivee,
            depuis_surface=depuis_surface,
            vers_surface=vers_surface,
            parking_depart=parking_depart,
            parking_arrivee=parking_arrivee,
            escale=orbite_escale,
        )
        if plan is None:
            return {
                "possible": False,
                "raison": f"Aucun itineraire entre {depart} et {arrivee}.",
            }

        data = asdict(plan)
        data["possible"] = True
        data["source"] = catalogue.source
        data["delta_v_total"] = plan.delta_v_total
        data["duree_totale"] = plan.duree_totale
        # Les avertissements se repetent d'une etape a l'autre.
        data["avertissements"] = list(dict.fromkeys(plan.avertissements))

        # Fenetre de tir : seulement si le jeu est la, car il faut la position
        # reelle des corps. Sans lui, on ne montre aucune date plutot qu'une
        # date fausse.
        data["fenetre"] = None
        data["geometrie"] = None
        if conn is not None:
            premier = next(
                (e for e in plan.etapes
                 if e.genre == "transfert" and e.angle_de_phase is not None),
                None,
            )
            if premier is not None:
                fenetre = planner.prochaine_fenetre(
                    conn, catalogue, premier.depuis, premier.vers,
                    premier.angle_de_phase,
                )
                data["fenetre"] = fenetre
                if fenetre and not fenetre.get("recurrente"):
                    data["geometrie"] = planner.geometrie(
                        conn, catalogue, premier.depuis, premier.vers,
                        fenetre["attente"], premier.duree,
                    )
        return data

    return await asyncio.to_thread(travail)


@app.get("/api/planner/cibles")
async def planner_cibles() -> dict:
    """Vaisseaux pouvant servir de cible a un rendez-vous."""
    conn = _connexion_jeu()
    if conn is None:
        return {"disponible": False, "raison": "Pas de liaison avec le jeu.",
                "cibles": []}

    from .planner import rendezvous as rdv

    orbites = await asyncio.to_thread(rdv.lire_orbites, conn)
    return {
        "disponible": True,
        "cibles": [asdict(o) for o in orbites],
    }


@app.get("/api/planner/rendezvous")
async def planner_rendezvous(
    cible: str,
    chasseur: str | None = None,
    chasseur_altitude: float | None = None,
) -> dict:
    conn = _connexion_jeu()
    if conn is None:
        return {
            "possible": False,
            "raison": (
                "Le rendez-vous demande la position reelle des engins : "
                "il faut que KSP soit lance."
            ),
        }

    from .planner import rendezvous as rdv

    def travail() -> dict:
        catalogue = planner.catalogue(conn)
        plan = rdv.calculer(
            conn, catalogue, cible,
            chasseur_altitude=chasseur_altitude,
            chasseur_nom=chasseur,
        )
        if plan is None:
            return {"possible": False,
                    "raison": f"Cible '{cible}' introuvable ou hors orbite."}
        data = asdict(plan)
        data["possible"] = True
        return data

    return await asyncio.to_thread(travail)


@app.post("/api/vab")
async def vab_recevoir(charge: dict) -> dict:
    """Point d'entree du mod : contenu du vaisseau en construction."""
    try:
        await asyncio.to_thread(vab.enregistrer, charge)
        return {"ok": True}
    except Exception as exc:
        log.debug("Charge du VAB illisible", exc_info=True)
        return {"ok": False, "erreur": str(exc)}


@app.get("/api/vab")
async def vab_lire() -> dict:
    return vab.dernier()


@app.get("/api/vab/brut")
async def vab_brut() -> dict:
    """Charge telle que le mod l'a envoyee, pour diagnostic."""
    return vab.brut()


@app.get("/api/noeud/cibles")
async def noeud_cibles() -> dict:
    """Cibles atteignables par un transfert direct depuis l'orbite actuelle."""
    from .planner import noeud as mod_noeud

    conn = _connexion_jeu()
    if conn is None:
        return {"disponible": False, "cibles": []}
    return {
        "disponible": True,
        "cibles": await asyncio.to_thread(mod_noeud.cibles_possibles, conn),
    }


@app.post("/api/noeud/poser")
async def noeud_poser(cible: str, simuler: bool = False) -> dict:
    """Calcule le transfert, et l'ecrit dans la partie sauf si `simuler`.

    L'ecriture dans le jeu est une action volontaire du pilote : le
    planificateur ne pose jamais de noeud de lui-meme.
    """
    from .planner import noeud as mod_noeud

    conn = _connexion_jeu()
    if conn is None:
        return {"possible": False, "raison": "Pas de liaison avec le jeu."}

    action = mod_noeud.planifier if simuler else mod_noeud.poser
    return await asyncio.to_thread(action, conn, cible)


@app.post("/api/noeud/effacer")
async def noeud_effacer() -> dict:
    from .planner import noeud as mod_noeud

    conn = _connexion_jeu()
    if conn is None:
        return {"retires": 0}
    return {"retires": await asyncio.to_thread(mod_noeud.effacer, conn)}


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
