"""Abstraction des fournisseurs de modeles de langage.

Le but est que le reste de la radio ignore totalement qui repond. On commence
sur Gemini, Claude est ecrit et pret ; basculer se fait par une variable
d'environnement, sans toucher a la logique metier.

Le format d'echange interne est volontairement neutre : chaque fournisseur le
traduit vers son propre protocole, car Gemini et Claude nomment les memes
concepts differemment (functionCall / tool_use, model / assistant...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """Description d'une commande exposee au modele."""

    name: str
    description: str
    parameters: dict[str, Any]  # schema JSON des arguments


@dataclass
class ToolCall:
    """Demande d'execution emise par le modele."""

    id: str
    name: str
    arguments: dict[str, Any]
    # Jeton opaque propre au fournisseur, a renvoyer tel quel au tour suivant.
    # Gemini 3 refuse la conversation avec une erreur 400 si la signature de
    # raisonnement n'accompagne pas l'appel de fonction rejoue. Les autres
    # fournisseurs ignorent ce champ.
    signature: str = ""


@dataclass
class Message:
    """Un tour de conversation, dans un format commun aux fournisseurs."""

    role: str  # "user" | "assistant" | "tool"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Renseignes uniquement quand role == "tool"
    tool_call_id: str = ""
    tool_name: str = ""


@dataclass
class Reply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str | None = None


class LLMProvider(ABC):
    """Contrat commun. Toute implementation doit etre asynchrone : la radio
    tourne dans la meme boucle que la telemetrie, un appel bloquant figerait
    le dashboard."""

    name: str = "none"
    model: str = ""

    @abstractmethod
    def available(self) -> bool:
        """Vrai si la configuration permet d'appeler le service (cle presente)."""

    @abstractmethod
    async def chat(
        self,
        system: str,
        history: list[Message],
        tools: list[ToolSpec],
    ) -> Reply:
        """Envoie la conversation et renvoie la reponse du modele.

        Ne doit pas lever : les erreurs reseau ou d'authentification
        reviennent dans Reply.error, pour que la radio affiche un message
        de panne plutot que de faire tomber le backend.
        """


class NullProvider(LLMProvider):
    """Utilise quand aucune cle n'est configuree, pour que la radio reste
    utilisable en mode commandes seules."""

    name = "none"

    def available(self) -> bool:
        return False

    async def chat(self, system, history, tools) -> Reply:  # noqa: ARG002
        return Reply(
            error="Aucun modele configure. Renseigne GEMINI_API_KEY "
                  "dans backend/.env puis relance le backend."
        )
