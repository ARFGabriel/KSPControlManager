"""Fournisseur Gemini (API Google Generative Language).

Correspondances avec notre format neutre :
    assistant        -> role "model"
    tool (resultat)  -> role "user" + partie functionResponse
    ToolSpec         -> function_declarations
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from .base import LLMProvider, Message, Reply, ToolCall, ToolSpec

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# Genereux a dessein : les modeles a raisonnement (serie 3) prennent
# facilement plus de 30 s avec un prompt systeme charge et seize outils
# declares. Mieux vaut une reponse tardive qu'une erreur inutile.
TIMEOUT = 120.0


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Traduction vers le format Gemini
    # ------------------------------------------------------------------
    @staticmethod
    def _contents(history: list[Message]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for msg in history:
            if msg.role == "tool":
                # Gemini attend le resultat d'outil dans un tour "user".
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": msg.tool_name,
                                    "response": {"result": msg.text},
                                }
                            }
                        ],
                    }
                )
                continue

            parts: list[dict[str, Any]] = []
            if msg.text:
                parts.append({"text": msg.text})
            for call in msg.tool_calls:
                part: dict[str, Any] = {
                    "functionCall": {"name": call.name, "args": call.arguments}
                }
                # Obligatoire pour la serie Gemini 3 : sans ce jeton, l'API
                # rejette le tour suivant avec une erreur 400.
                if call.signature:
                    part["thoughtSignature"] = call.signature
                parts.append(part)
            if not parts:
                continue
            contents.append(
                {"role": "model" if msg.role == "assistant" else "user", "parts": parts}
            )
        return contents

    @staticmethod
    def _tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        if not tools:
            return []
        return [
            {
                "function_declarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ]
            }
        ]

    # ------------------------------------------------------------------
    async def chat(
        self,
        system: str,
        history: list[Message],
        tools: list[ToolSpec],
    ) -> Reply:
        payload: dict[str, Any] = {
            "contents": self._contents(history),
            "systemInstruction": {"parts": [{"text": system}]},
        }
        declared = self._tools(tools)
        if declared:
            payload["tools"] = declared

        url = f"{BASE_URL}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                )
        except httpx.TimeoutException:
            return Reply(error="Gemini n'a pas repondu dans les temps.")
        except Exception as exc:
            return Reply(error=f"Erreur reseau vers Gemini : {exc}")

        if response.status_code != 200:
            return Reply(error=_http_error(response))

        try:
            return self._parse(response.json())
        except Exception as exc:
            return Reply(error=f"Reponse Gemini illisible : {exc}")

    @staticmethod
    def _parse(data: dict[str, Any]) -> Reply:
        candidates = data.get("candidates") or []
        if not candidates:
            # Cas classique : la reponse a ete filtree par les regles de securite.
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            if reason:
                return Reply(error=f"Reponse bloquee par Gemini ({reason}).")
            return Reply(error="Gemini n'a renvoye aucune reponse.")

        texts: list[str] = []
        calls: list[ToolCall] = []
        for part in candidates[0].get("content", {}).get("parts", []) or []:
            if "text" in part:
                texts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                calls.append(
                    ToolCall(
                        id=uuid.uuid4().hex[:8],
                        name=fc.get("name", ""),
                        arguments=fc.get("args") or {},
                        # La signature est portee par la partie, a cote de
                        # functionCall, pas a l'interieur.
                        signature=part.get("thoughtSignature", ""),
                    )
                )
        return Reply(text="".join(texts).strip(), tool_calls=calls)


def _http_error(response: httpx.Response) -> str:
    """Extrait le message d'erreur de Google, bien plus parlant que le code."""
    try:
        detail = response.json().get("error", {}).get("message", "")
    except Exception:
        detail = response.text[:200]
    if response.status_code in (401, 403):
        return f"Cle Gemini refusee ({response.status_code}) : {detail}"
    if response.status_code == 404:
        return (f"Modele '{detail}' introuvable. Verifie GEMINI_MODEL dans "
                f"backend/.env — la liste est disponible sur /api/radio/models.")
    if response.status_code == 429:
        # Le palier gratuit est compte au niveau du projet Google, pas par
        # modele : changer de modele ne debloque rien. Il faut attendre la
        # remise a zero, ou activer la facturation.
        return (
            "Quota Gemini depasse. Le palier gratuit est partage par tous les "
            "modeles du meme projet : changer GEMINI_MODEL n'y changera rien. "
            "Attends la remise a zero du quota, ou active la facturation sur "
            "ta cle."
        )
    return f"Gemini a repondu {response.status_code} : {detail}"


async def list_models(api_key: str) -> list[str]:
    """Liste les modeles utilisables avec cette cle.

    Sert a diagnostiquer une erreur 404 sans avoir a deviner le nom exact du
    modele, qui change au fil des versions de l'API.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/models", params={"key": api_key})
    response.raise_for_status()
    names = []
    for model in response.json().get("models", []):
        if "generateContent" in (model.get("supportedGenerationMethods") or []):
            names.append(model.get("name", "").removeprefix("models/"))
    return sorted(names)
