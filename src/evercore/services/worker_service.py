"""Worker task-claim and execution service."""

from __future__ import annotations

from sqlmodel import Session, select

from evercore.executors import ExecutorRegistry
from evercore.models import Task, Ticket
from evercore.repositories import add_task_log, get_task, get_ticket_by_ticket_id, list_dependencies, update_heartbeat
from evercore.schemas import WorkerRunResponse
from evercore.settings import settings
from evercore.services.state_policy import DefaultTicketStatePolicy, TicketStatePolicy
from evercore.time_utils import now_utc


class WorkerService:
    def __init__(
        self,
        executor_registry: ExecutorRegistry,
        ticket_state_policy: TicketStatePolicy | None = None,
    ):
        self.executor_registry = executor_registry
        self.ticket_state_policy = ticket_state_policy or DefaultTicketStatePolicy()

    def process_once(self, session: Session, worker_id: str | None = None) -> WorkerRunResponse:
        effective_worker_id = worker_id or settings.worker_id

        task = self._claim_next_task(session)
        if task is None:
            update_heartbeat(session, effective_worker_id, "idle", None)
            return WorkerRunResponse(processed=False, task_id=None, message="no queued task")

        ticket = get_ticket_by_ticket_id(session, task.ticket_id)
        if ticket is None:
            task.state = "failed"
            task.error_message = f"missing ticket: {task.ticket_id}"
            task.completed_at = now_utc()
            task.updated_at = now_utc()
            add_task_log(session, task_id=task.id, log_type="error", message=task.error_message, success=False)
            update_heartbeat(session, effective_worker_id, "idle", None)
            return WorkerRunResponse(processed=True, task_id=task.id, message=task.error_message)

        update_heartbeat(session, effective_worker_id, "working", task.id)
        executor = self.executor_registry.get(task.task_key)
        if executor is None:
            task.state = "failed"
            task.error_message = f"unknown task_key: {task.task_key}"
            task.completed_at = now_utc()
            task.updated_at = now_utc()
            add_task_log(session, task_id=task.id, log_type="error", message=task.error_message, success=False)
            self._sync_ticket_state(session, ticket)
            update_heartbeat(session, effective_worker_id, "idle", None)
            return WorkerRunResponse(processed=True, task_id=task.id, message=task.error_message)

        result = executor.execute(ticket, task)
        task.attempt_count += 1
        task.updated_at = now_utc()

        if result.success:
            task.state = "completed"
            task.result_data = dict(result.output or {})
            task.error_message = None
            task.completed_at = now_utc()
            add_task_log(
                session,
                task_id=task.id,
                log_type="info",
                message=result.message or "task completed",
                details=result.output or {},
                success=True,
            )
        else:
            task.state = "failed"
            task.error_message = result.message or "task failed"
            task.completed_at = now_utc()
            add_task_log(
                session,
                task_id=task.id,
                log_type="error",
                message=task.error_message,
                details=result.output or {},
                success=False,
            )

        session.add(task)
        self._sync_ticket_state(session, ticket)
        update_heartbeat(session, effective_worker_id, "idle", None)

        return WorkerRunResponse(
            processed=True,
            task_id=task.id,
            message="completed" if result.success else task.error_message,
        )

    def _claim_next_task(self, session: Session) -> Task | None:
        statement = select(Task).where(Task.state == "queued").order_by(Task.created_at.asc())
        candidates = list(session.exec(statement).all())
        for candidate in candidates:
            if self._dependencies_satisfied(session, candidate.id):
                candidate.state = "running"
                candidate.started_at = now_utc()
                candidate.updated_at = now_utc()
                session.add(candidate)
                return candidate
        return None

    def _dependencies_satisfied(self, session: Session, task_id: int) -> bool:
        deps = list_dependencies(session, task_id)
        if not deps:
            return True

        for dep in deps:
            dep_task = get_task(session, dep.depends_on_task_id)
            if dep_task is None or dep_task.state != "completed":
                return False
        return True

    def _sync_ticket_state(self, session: Session, ticket: Ticket) -> None:
        statement = select(Task).where(Task.ticket_id == ticket.ticket_id)
        tasks = list(session.exec(statement).all())

        ticket.updated_at = now_utc()
        resolved = self.ticket_state_policy.resolve(ticket, tasks)
        ticket.stage = resolved.stage
        ticket.status = resolved.status
        ticket.completed_at = resolved.completed_at

        session.add(ticket)
