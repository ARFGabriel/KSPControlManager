"""Configuration centralisee, lue depuis l'environnement ou un fichier .env.

Aucune cle API n'est ecrite en dur dans le code : c'est la lecon tiree de la
premiere version du mod, ou la cle Gemini etait dans le source et se retrouvait
compilee dans la DLL distribuee.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- Source de telemetrie ---
    # "auto" : essaie kRPC, bascule sur le simulateur s'il est injoignable,
    # puis retente kRPC en tache de fond des que KSP est lance.
    source: str = os.getenv("KSP_MC_SOURCE", "auto")
    krpc_address: str = os.getenv("KRPC_ADDRESS", "127.0.0.1")
    krpc_rpc_port: int = _int("KRPC_RPC_PORT", 50000)
    krpc_stream_port: int = _int("KRPC_STREAM_PORT", 50001)
    krpc_retry_s: float = _float("KRPC_RETRY_S", 5.0)

    # --- Diffusion ---
    telemetry_hz: float = _float("TELEMETRY_HZ", 10.0)

    # --- Serveur web ---
    host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    port: int = _int("BACKEND_PORT", 8000)

    # --- Radio (LLM) : pas encore utilise, prepare pour la suite ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    @property
    def telemetry_period(self) -> float:
        return 1.0 / max(1.0, self.telemetry_hz)


settings = Settings()
