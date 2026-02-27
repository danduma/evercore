"""Task executor registry with lemlem as agent foundation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from evergreen_core.agent_runtime import LemlemAgentRuntime
from evergreen_core.execution import ExecutionResult, TaskExecutor
from evergreen_core.models import Task, Ticket


class NoopExecutor(TaskExecutor):
    def execute(self, ticket: Ticket, task: Task) -> ExecutionResult:
        del ticket
        return ExecutionResult(success=True, message="noop task completed", output={})


class LemlemPromptExecutor(TaskExecutor):
    def __init__(self, runtime: LemlemAgentRuntime):
        self.runtime = runtime

    def execute(self, ticket: Ticket, task: Task) -> ExecutionResult:
        payload = dict(task.payload or {})
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return ExecutionResult(success=False, message="lemlem_prompt requires payload.prompt")

        result = self.runtime.run_prompt(
            prompt=prompt,
            model=payload.get("model"),
            system_prompt=payload.get("system_prompt") or f"You are working on ticket {ticket.ticket_id}.",
            temperature=payload.get("temperature"),
        )
        if not result.success:
            return ExecutionResult(success=False, message=result.error or "lemlem prompt failed")

        return ExecutionResult(
            success=True,
            message="lemlem prompt completed",
            output={
                "text": result.text,
                "model_used": result.model_used,
                "provider": result.provider,
                "usage": result.usage,
            },
        )


class LemlemAgentJsonExecutor(TaskExecutor):
    def __init__(self, runtime: LemlemAgentRuntime):
        self.runtime = runtime

    def execute(self, ticket: Ticket, task: Task) -> ExecutionResult:
        payload = dict(task.payload or {})
        system_prompt = str(payload.get("system_prompt") or "").strip()
        user_payload = payload.get("user_payload") or {}
        if not system_prompt:
            return ExecutionResult(success=False, message="lemlem_agent_json requires payload.system_prompt")
        if not isinstance(user_payload, dict):
            return ExecutionResult(success=False, message="payload.user_payload must be an object")

        runtime_result = self.runtime.run_agent_json(
            model=payload.get("model"),
            system_prompt=system_prompt,
            payload={
                "ticket_id": ticket.ticket_id,
                "ticket_stage": ticket.stage,
                "ticket_context": ticket.context_data,
                "task_payload": user_payload,
            },
            temperature=payload.get("temperature"),
            max_tool_iterations=int(payload.get("max_tool_iterations") or 6),
        )
        if not runtime_result.success:
            return ExecutionResult(success=False, message=runtime_result.error or "lemlem agent json failed")

        return ExecutionResult(
            success=True,
            message="lemlem agent json completed",
            output={
                "text": runtime_result.text,
                "model_used": runtime_result.model_used,
                "usage": runtime_result.usage,
                "raw": runtime_result.raw or {},
            },
        )


@dataclass
class ExecutorRegistry:
    executors: Dict[str, TaskExecutor]

    @classmethod
    def default(cls) -> "ExecutorRegistry":
        runtime = LemlemAgentRuntime()
        return cls(
            executors={
                "noop": NoopExecutor(),
                "lemlem_prompt": LemlemPromptExecutor(runtime),
                "lemlem_agent_json": LemlemAgentJsonExecutor(runtime),
            }
        )

    def get(self, task_key: str) -> TaskExecutor | None:
        return self.executors.get(task_key)

    def register(self, task_key: str, executor: TaskExecutor) -> None:
        self.executors[task_key] = executor
