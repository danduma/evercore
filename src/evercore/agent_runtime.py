"""Lemlem-first agent runtime for standalone evercore."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from lemlem import LLMClient
from lemlem.adapter import LLMAdapter, MODEL_DATA

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
        self.client = LLMClient(MODEL_DATA)
        self.adapter = LLMAdapter(model_data=MODEL_DATA, client=self.client)

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
            result = self.client.generate(
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
