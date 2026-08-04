"""Choix du fournisseur de modele, pilote par la configuration."""

from __future__ import annotations

import logging

from ...config import settings
from .base import LLMProvider, Message, NullProvider, Reply, ToolCall, ToolSpec
from .claude import ClaudeProvider
from .gemini import GeminiProvider

log = logging.getLogger("ksp_mc.radio.llm")

__all__ = [
    "LLMProvider", "Message", "Reply", "ToolCall", "ToolSpec",
    "build_provider",
]


def build_provider() -> LLMProvider:
    choice = (settings.llm_provider or "").lower()

    if choice == "claude":
        provider: LLMProvider = ClaudeProvider(
            settings.anthropic_api_key, settings.anthropic_model
        )
    else:
        provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)

    if not provider.available():
        log.warning(
            "Fournisseur '%s' sans cle API : la radio repondra en mode degrade. "
            "Renseigne la cle dans backend/.env.",
            provider.name,
        )
        return NullProvider()

    log.info("Radio : fournisseur %s, modele %s", provider.name, provider.model)
    return provider
