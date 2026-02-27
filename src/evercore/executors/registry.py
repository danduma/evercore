"""Task executor registry with lemlem as agent foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict

from evercore.db import get_session
from evercore.agent_runtime import LemlemAgentRuntime
from evercore.execution import ExecutionResult, TaskExecutor
from evercore.models import Task, Ticket
from evercore.repositories import get_unconsumed_ticket_event
from evercore.time_utils import now_utc
from evercore.settings import settings


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


class WaitForEventExecutor(TaskExecutor):
    def execute(self, ticket: Ticket, task: Task) -> ExecutionResult:
        payload = dict(task.payload or {})
        event_type = str(payload.get("event_type") or "").strip()
        if not event_type:
            return ExecutionResult(
                success=False,
                terminal_failure=True,
                message="wait_for_event requires payload.event_type",
            )
        timeout_seconds = payload.get("timeout_seconds")
        consume = bool(payload.get("consume", True))
        defer_seconds = int(payload.get("poll_interval_seconds") or settings.event_wait_poll_interval_seconds)

        session = get_session()
        try:
            row = get_unconsumed_ticket_event(
                session,
                ticket_id=ticket.ticket_id,
                event_type=event_type,
            )
            if row is not None:
                if consume:
                    row.consumed_at = now_utc()
                    row.consumed_by_task_id = task.id
                    session.add(row)
                    session.commit()
                else:
                    session.rollback()
                return ExecutionResult(
                    success=True,
                    message=f"received event '{event_type}'",
                    output={
                        "event_id": row.id,
                        "event_type": row.event_type,
                        "payload": row.payload,
                        "created_at": row.created_at.isoformat(),
                    },
                )
            session.rollback()
        finally:
            session.close()

        if timeout_seconds is not None:
            started_at = task.created_at or now_utc()
            timeout_at = started_at + timedelta(seconds=max(int(timeout_seconds), 1))
            if now_utc() >= timeout_at:
                return ExecutionResult(
                    success=False,
                    terminal_failure=True,
                    message=f"timed out waiting for event '{event_type}'",
                    output={"event_type": event_type},
                )

        return ExecutionResult(
            success=False,
            defer=True,
            defer_seconds=max(1, defer_seconds),
            message=f"waiting for event '{event_type}'",
            output={"event_type": event_type},
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
                "wait_for_event": WaitForEventExecutor(),
            }
        )

    def get(self, task_key: str) -> TaskExecutor | None:
        return self.executors.get(task_key)

    def register(self, task_key: str, executor: TaskExecutor) -> None:
        self.executors[task_key] = executor
