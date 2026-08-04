"""Boucle de telemetrie et diffusion aux clients connectes.

Un seul echantillonnage alimente tous les navigateurs ouverts : le jeu n'est
jamais interroge plus d'une fois par cycle, quel que soit le nombre d'ecrans.

En mode "auto", le hub demarre sur le simulateur si KSP n'est pas la, puis
bascule tout seul sur le vrai jeu des que le serveur kRPC repond. Concretement,
on peut lancer le dashboard avant le jeu et le voir prendre la main sans rien
relancer.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .config import settings
from .telemetry.krpc_source import KrpcSource
from .telemetry.schema import Telemetry
from .telemetry.sim_source import SimSource
from .telemetry.source import TelemetrySource

log = logging.getLogger("ksp_mc.hub")


class TelemetryHub:
    def __init__(self) -> None:
        self.source: TelemetrySource | None = None
        self.latest: Telemetry = Telemetry(error="Demarrage en cours")
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_krpc_try = 0.0

    # ------------------------------------------------------------------
    # Abonnements
    # ------------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        # maxsize=1 : un client lent recoit le dernier etat connu, pas une
        # file d'echantillons perimes qui grandirait sans fin.
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, payload: dict) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Choix de la source
    # ------------------------------------------------------------------
    def _try_krpc(self) -> KrpcSource | None:
        src = KrpcSource(
            address=settings.krpc_address,
            rpc_port=settings.krpc_rpc_port,
            stream_port=settings.krpc_stream_port,
        )
        try:
            src.connect()
            log.info("Connecte au serveur kRPC de KSP")
            return src
        except Exception as exc:
            log.debug("kRPC injoignable : %s", exc)
            try:
                src.close()
            except Exception:
                pass
            return None

    def _select_initial_source(self) -> TelemetrySource:
        mode = settings.source.lower()
        if mode == "sim":
            src: TelemetrySource = SimSource()
            src.connect()
            log.info("Source : simulateur (forcee par configuration)")
            return src

        krpc_src = self._try_krpc()
        if krpc_src is not None:
            return krpc_src

        if mode == "krpc":
            # Mode strict : on ne triche pas avec un simulateur, on signale.
            log.warning("kRPC demande mais injoignable ; nouvelle tentative en boucle")
            return _DisconnectedSource()

        src = SimSource()
        src.connect()
        log.info("Source : simulateur (KSP non detecte, bascule automatique)")
        return src

    def _maybe_upgrade_to_krpc(self) -> None:
        """En mode auto, retente periodiquement le vrai jeu."""
        if settings.source.lower() == "sim":
            return
        if isinstance(self.source, KrpcSource):
            return
        now = time.monotonic()
        if now - self._last_krpc_try < settings.krpc_retry_s:
            return
        self._last_krpc_try = now

        krpc_src = self._try_krpc()
        if krpc_src is not None:
            old = self.source
            self.source = krpc_src
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            log.info("Bascule sur KSP : le jeu est detecte")

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self._stop.clear()
        self.source = await asyncio.to_thread(self._select_initial_source)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.source is not None:
            await asyncio.to_thread(self.source.close)
            self.source = None

    async def _run(self) -> None:
        period = settings.telemetry_period
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                # Les appels kRPC sont bloquants : on les sort de la boucle
                # asyncio pour ne pas figer le serveur web.
                await asyncio.to_thread(self._maybe_upgrade_to_krpc)
                if self.source is not None:
                    self.latest = await asyncio.to_thread(self.source.sample)
                    self._broadcast(self.latest.to_dict())
            except Exception as exc:
                log.exception("Erreur dans la boucle de telemetrie")
                self.latest = Telemetry(connected=False, error=str(exc))
                self._broadcast(self.latest.to_dict())
                # Une source cassee (jeu ferme en plein vol) doit repartir
                # proprement au tour suivant.
                if isinstance(self.source, KrpcSource):
                    await asyncio.to_thread(self.source.close)
                    self.source = _DisconnectedSource()

            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, period - elapsed))


class _DisconnectedSource(TelemetrySource):
    """Source de repli quand kRPC est exige mais absent."""

    name = "none"

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def sample(self) -> Telemetry:
        return Telemetry(
            connected=False,
            source=self.name,
            error="En attente du serveur kRPC (KSP lance ?)",
            timestamp=time.time(),
        )


hub = TelemetryHub()
