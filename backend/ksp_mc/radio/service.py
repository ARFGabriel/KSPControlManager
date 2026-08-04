"""Orchestration de la radio : conversation, outils, confirmations.

Trois garanties tenues ici :

1. Le sol ne recoit aucun outil. Impossible qu'une discussion avec le centre
   de controle declenche une action a bord, meme si le modele le voulait.
2. Une commande irreversible n'est jamais executee sans accord explicite du
   pilote. La boucle se met en pause et attend.
3. Aucun appel au jeu ne peut figer la radio : KSP en pause bloque les
   requetes kRPC indefiniment, donc tout passe par un delai d'expiration.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from ..hub import hub
from ..telemetry.krpc_source import KrpcSource
from . import commands, personas
from .llm import Message, ToolCall, build_provider

log = logging.getLogger("ksp_mc.radio")

MAX_TOOL_ROUNDS = 4      # garde-fou contre une boucle d'outils sans fin
HISTORY_LIMIT = 40       # tours conserves par interlocuteur
COMMAND_TIMEOUT_S = 10.0  # au-dela, on considere le jeu bloque


@dataclass
class Pending:
    """Commande irreversible en attente d'accord du pilote."""

    id: str
    persona: str
    call: ToolCall
    remaining: list[ToolCall] = field(default_factory=list)
    created: float = field(default_factory=time.time)


class RadioService:
    def __init__(self) -> None:
        self.provider = build_provider()
        self.history: dict[str, list[Message]] = {
            personas.GROUND: [],
            personas.CREW: [],
        }
        self.pending: dict[str, Pending] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Diffusion vers les navigateurs
    # ------------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _emit(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def status(self) -> dict:
        return {
            "type": "status",
            "provider": self.provider.name,
            "model": self.provider.model,
            "available": self.provider.available(),
            "commands": sorted(commands.REGISTRY),
            "irreversible": sorted(
                n for n, c in commands.REGISTRY.items() if c.irreversible
            ),
        }

    # ------------------------------------------------------------------
    # Acces au jeu
    # ------------------------------------------------------------------
    @staticmethod
    def _live_connection():
        """Connexion kRPC utilisable, ou None.

        Le simulateur ne pilote rien : c'est volontaire, on ne veut pas
        laisser croire qu'une commande a agi alors que le jeu est ferme.
        """
        source = hub.source
        if isinstance(source, KrpcSource) and source.conn is not None:
            return source.conn
        return None

    async def _execute(self, call: ToolCall) -> tuple[bool, str]:
        cmd = commands.get(call.name)
        if cmd is None:
            return False, f"Commande inconnue : {call.name}"

        conn = self._live_connection()
        if conn is None:
            return False, (
                "Pas de liaison avec le jeu : KSP n'est pas lance, ou le "
                "serveur kRPC n'est pas demarre. Aucune commande possible."
            )

        def run() -> str:
            vessel = conn.space_center.active_vessel
            if vessel is None:
                return "Aucun vaisseau actif : impossible d'agir."
            return cmd.handler(conn, vessel, **call.arguments)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(run), timeout=COMMAND_TIMEOUT_S
            )
            return True, result
        except asyncio.TimeoutError:
            # Cas observe : jeu en pause, le serveur kRPC ne traite plus rien.
            return False, (
                f"Le jeu n'a pas repondu en {COMMAND_TIMEOUT_S:.0f} s. "
                "Il est probablement en pause ou dans un menu."
            )
        except TypeError as exc:
            return False, f"Arguments invalides pour {call.name} : {exc}"
        except Exception as exc:
            return False, f"Echec de {call.name} : {exc}"

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------
    async def send(self, persona: str, text: str) -> None:
        if persona not in self.history:
            persona = personas.CREW

        async with self._lock:
            self._emit({"type": "message", "persona": "pilote", "text": text})
            self.history[persona].append(Message(role="user", text=text))
            await self._turn(persona)

    async def _turn(self, persona: str) -> None:
        """Fait tourner le modele jusqu'a une reponse sans outil, une pause
        pour confirmation, ou l'epuisement du garde-fou."""
        for _ in range(MAX_TOOL_ROUNDS):
            # Le sol n'a aucun outil : c'est la garantie qu'il ne peut pas agir.
            tools = commands.specs() if persona == personas.CREW else []
            system = personas.system_prompt(persona, hub.latest)

            reply = await self.provider.chat(
                system, self.history[persona][-HISTORY_LIMIT:], tools
            )

            if reply.error:
                self._emit({"type": "error", "text": reply.error})
                return

            if reply.text:
                self._emit(
                    {"type": "message", "persona": persona, "text": reply.text}
                )

            self.history[persona].append(
                Message(role="assistant", text=reply.text,
                        tool_calls=reply.tool_calls)
            )

            if not reply.tool_calls:
                return

            paused = await self._run_calls(persona, list(reply.tool_calls))
            if paused:
                return

        self._emit({
            "type": "error",
            "text": "Trop d'allers-retours de commandes, sequence interrompue.",
        })

    async def _run_calls(self, persona: str, calls: list[ToolCall]) -> bool:
        """Execute les commandes demandees. Renvoie True si on s'est arrete
        en attente d'une confirmation."""
        while calls:
            call = calls.pop(0)
            cmd = commands.get(call.name)

            if cmd is not None and cmd.irreversible:
                pending = Pending(
                    id=uuid.uuid4().hex[:8],
                    persona=persona,
                    call=call,
                    remaining=calls,
                )
                self.pending[pending.id] = pending
                self._emit({
                    "type": "confirmation",
                    "id": pending.id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "description": cmd.description,
                })
                return True

            ok, result = await self._execute(call)
            self._emit({
                "type": "command",
                "name": call.name,
                "arguments": call.arguments,
                "result": result,
                "ok": ok,
            })
            self.history[persona].append(
                Message(role="tool", text=result,
                        tool_call_id=call.id, tool_name=call.name)
            )
        return False

    async def confirm(self, pending_id: str, approved: bool) -> None:
        async with self._lock:
            pending = self.pending.pop(pending_id, None)
            if pending is None:
                self._emit({
                    "type": "error",
                    "text": "Cette demande de confirmation n'est plus valable.",
                })
                return

            if approved:
                ok, result = await self._execute(pending.call)
            else:
                ok, result = False, "Le pilote a refuse cette commande."

            self._emit({
                "type": "command",
                "name": pending.call.name,
                "arguments": pending.call.arguments,
                "result": result,
                "ok": ok,
            })
            self.history[pending.persona].append(
                Message(role="tool", text=result,
                        tool_call_id=pending.call.id,
                        tool_name=pending.call.name)
            )

            paused = await self._run_calls(pending.persona, pending.remaining)
            if not paused:
                await self._turn(pending.persona)

    def reset(self, persona: str | None = None) -> None:
        for key in ([persona] if persona else list(self.history)):
            if key in self.history:
                self.history[key].clear()
        self.pending.clear()
        self._emit({"type": "reset", "persona": persona})


radio = RadioService()
