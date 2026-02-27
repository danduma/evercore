"""Lemlem-first agent runtime for standalone evercore."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from lemlem import LLMClient
import lemlem.adapter as lemlem_adapter
from lemlem.adapter import LLMAdapter

from .settings import settings


@dataclass
class AgentRuntimeResult:
    success: bool
    text: str = ""
    usage: dict[str, Any] | None = None
    provider: Optional[str] = None
    model_used: Optional[str] = None
    raw: dict[str, Any] | None = None
    error: Optional[str] = None


class LemlemAgentRuntime:
    """Central foundation for all agent execution via lemlem."""

    def __init__(self) -> None:
        lemlem_adapter._refresh_model_data()
        self._client_model_timestamp = lemlem_adapter._MODEL_DATA_TIMESTAMP
        self.client = LLMClient(lemlem_adapter.MODEL_DATA)
        # Let LLMAdapter own refresh behavior so DB/YAML config changes propagate.
        self.adapter = LLMAdapter()

    def _get_client(self) -> LLMClient:
        lemlem_adapter._refresh_model_data()
        if self._client_model_timestamp != lemlem_adapter._MODEL_DATA_TIMESTAMP:
            self.client = LLMClient(lemlem_adapter.MODEL_DATA)
            self._client_model_timestamp = lemlem_adapter._MODEL_DATA_TIMESTAMP
        return self.client

    def run_prompt(
        self,
        *,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> AgentRuntimeResult:
        try:
            selected_model = (model or settings.default_lemlem_model).strip()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            result = self._get_client().generate(
                model=selected_model,
                messages=messages,
                temperature=temperature,
            )
            usage = result.get_usage()
            usage_dict = vars(usage) if usage is not None and hasattr(usage, "__dict__") else None
            return AgentRuntimeResult(
                success=True,
                text=result.text or "",
                usage=usage_dict,
                provider=result.provider,
                model_used=result.model_used,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentRuntimeResult(success=False, error=str(exc))

    def run_agent_json(
        self,
        *,
        model: Optional[str],
        system_prompt: str,
        payload: dict[str, Any],
        temperature: Optional[float] = None,
        max_tool_iterations: int = 6,
    ) -> AgentRuntimeResult:
        try:
            selected_model = (model or settings.default_lemlem_model).strip()
            response = self.adapter.chat_json(
                system_prompt=system_prompt,
                user_payload=payload,
                model=selected_model,
                temperature=temperature,
                max_tool_iterations=max_tool_iterations,
            )
            usage = response.get("usage")
            usage_dict = vars(usage) if usage is not None and hasattr(usage, "__dict__") else None
            return AgentRuntimeResult(
                success=True,
                text=str(response.get("final_text") or response.get("text") or ""),
                usage=usage_dict,
                model_used=str(response.get("model_used") or selected_model),
                raw=response,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentRuntimeResult(success=False, error=str(exc))
