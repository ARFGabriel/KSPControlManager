"""Fournisseur Claude (API Anthropic).

Ecrit et fonctionnel, mais inactif tant que LLM_PROVIDER vaut "gemini".
Pour basculer, il suffit de renseigner ANTHROPIC_API_KEY et de passer
LLM_PROVIDER=claude dans backend/.env.

Correspondances avec notre format neutre :
    assistant       -> role "assistant", blocs text et tool_use
    tool (resultat) -> role "user", bloc tool_result
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import LLMProvider, Message, Reply, ToolCall, ToolSpec

BASE_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT = 60.0
MAX_TOKENS = 1024


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        self.api_key = api_key
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    @staticmethod
    def _messages(history: list[Message]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for msg in history:
            if msg.role == "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.text,
                            }
                        ],
                    }
                )
                continue

            blocks: list[dict[str, Any]] = []
            if msg.text:
                blocks.append({"type": "text", "text": msg.text})
            for call in msg.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )
            if not blocks:
                continue
            messages.append({"role": msg.role, "content": blocks})
        return messages

    @staticmethod
    def _tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    # ------------------------------------------------------------------
    async def chat(
        self,
        system: str,
        history: list[Message],
        tools: list[ToolSpec],
    ) -> Reply:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": self._messages(history),
        }
        if tools:
            payload["tools"] = self._tools(tools)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(BASE_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            return Reply(error="Claude n'a pas repondu dans les temps.")
        except Exception as exc:
            return Reply(error=f"Erreur reseau vers Claude : {exc}")

        if response.status_code != 200:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                detail = response.text[:200]
            return Reply(error=f"Claude a repondu {response.status_code} : {detail}")

        try:
            data = response.json()
        except Exception as exc:
            return Reply(error=f"Reponse Claude illisible : {exc}")

        texts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []) or []:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                    )
                )
        return Reply(text="".join(texts).strip(), tool_calls=calls)
