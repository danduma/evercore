"""Worker task-claim and execution service."""

from __future__ import annotations

import threading
from contextlib import suppress

from sqlalchemy import or_
from sqlmodel import Session, select

from evercore.executors import ExecutorRegistry
from evercore.models import Task, Ticket
from evercore.repositories import (
    add_task_log,
    get_task,
    get_ticket_by_ticket_id,
    list_dependencies,
    update_heartbeat,
)
from evercore.schemas import WorkerRunResponse
from evercore.settings import settings
from evercore.services.state_policy import DefaultTicketStatePolicy, TicketStatePolicy
from evercore.task_control import TaskControl
from evercore.task_runtime import (
    compute_next_retry_at,
    compute_retry_delay_seconds,
    is_stale_running_task,
    lease_expires_at,
    normalize_max_attempts,
    should_dead_letter,
)
from evercore.time_utils import coerce_utc, now_utc


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
        bind = session.get_bind()
        self._reap_stale_running_tasks(bind)

        with Session(bind=bind, expire_on_commit=False) as claim_session:
            cancelled_before_claim = self._finalize_requested_cancellations(claim_session)
            task = self._claim_next_task(claim_session, effective_worker_id)
            if task is None:
                update_heartbeat(claim_session, effective_worker_id, "idle", None)
                claim_session.commit()
                if cancelled_before_claim > 0:
                    return WorkerRunResponse(
                        processed=True,
                        task_id=None,
                        message=f"cancelled {cancelled_before_claim} task(s)",
                    )
                return WorkerRunResponse(
                    processed=False, task_id=None, message="no queued task"
                )
            task_id = int(task.id)
            task_key = str(task.task_key)
            ticket_id = str(task.ticket_id)
            update_heartbeat(claim_session, effective_worker_id, "working", task_id)
            claim_session.commit()

        with Session(bind=bind, expire_on_commit=False) as load_session:
            task_for_exec = load_session.exec(
                select(Task).where(Task.id == task_id)
            ).first()
            ticket = get_ticket_by_ticket_id(load_session, ticket_id)
            if task_for_exec is None:
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=False, task_id=task_id, message="claimed task missing"
                )
            if ticket is None:
                self._mark_task_terminal_failure(
                    load_session,
                    task_for_exec,
                    f"missing ticket: {ticket_id}",
                )
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message=f"missing ticket: {ticket_id}",
                )

            if bool(ticket.paused):
                self._park_task_for_pause(load_session, task_for_exec)
                self._sync_ticket_state(load_session, ticket)
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message="ticket paused before execution",
                )

            if bool(ticket.approval_required) and ticket.approval_status == "pending":
                self._park_task_for_approval(load_session, task_for_exec)
                self._sync_ticket_state(load_session, ticket)
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message="ticket awaiting approval before execution",
                )

            if bool(task_for_exec.cancel_requested):
                self._mark_task_cancelled(load_session, task_for_exec)
                self._sync_ticket_state(load_session, ticket)
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message="cancelled before execution",
                )

            executor = self.executor_registry.get(task_key)
            if executor is None:
                self._mark_task_terminal_failure(
                    load_session,
                    task_for_exec,
                    f"unknown task_key: {task_key}",
                )
                self._sync_ticket_state(load_session, ticket)
                update_heartbeat(load_session, effective_worker_id, "idle", None)
                load_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message=f"unknown task_key: {task_key}",
                )

            # End read transaction before potentially long-running execution.
            load_session.commit()

        stop_lease_event = threading.Event()
        lease_thread = threading.Thread(
            target=self._lease_renewer_loop,
            args=(bind, task_id, effective_worker_id, stop_lease_event),
            daemon=True,
        )
        lease_thread.start()
        result = None
        raised_exc: Exception | None = None
        try:
            execute_with_control = getattr(executor, "execute_with_control", None)
            if callable(execute_with_control):
                control = TaskControl(
                    session_factory=lambda: Session(bind=bind, expire_on_commit=False),
                    task_id=task_id,
                    ticket_id=ticket_id,
                )
                result = execute_with_control(ticket, task_for_exec, control)
            else:
                result = executor.execute(ticket, task_for_exec)
        except Exception as exc:  # noqa: BLE001
            raised_exc = exc
        finally:
            stop_lease_event.set()
            with suppress(Exception):
                lease_thread.join(timeout=2.0)

        with Session(bind=bind, expire_on_commit=False) as finalize_session:
            live_task = finalize_session.exec(select(Task).where(Task.id == task_id)).first()
            if live_task is None:
                update_heartbeat(finalize_session, effective_worker_id, "idle", None)
                finalize_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message="task disappeared before finalization",
                )

            live_ticket = get_ticket_by_ticket_id(finalize_session, ticket_id)
            if live_ticket is None:
                self._mark_task_terminal_failure(
                    finalize_session, live_task, f"missing ticket: {ticket_id}"
                )
                update_heartbeat(finalize_session, effective_worker_id, "idle", None)
                finalize_session.commit()
                return WorkerRunResponse(
                    processed=True,
                    task_id=task_id,
                    message=f"missing ticket: {ticket_id}",
                )

            if raised_exc is not None:
                response = self._finalize_retry_or_dead_letter(
                    finalize_session,
                    live_task,
                    message=f"execution raised: {raised_exc}",
                )
            elif bool(live_task.cancel_requested):
                self._mark_task_cancelled(finalize_session, live_task)
                response = WorkerRunResponse(
                    processed=True, task_id=task_id, message="cancelled"
                )
            elif result is not None and bool(result.defer):
                response = self._finalize_deferred_task(
                    finalize_session,
                    live_task,
                    message=result.message or "deferred",
                    defer_seconds=result.defer_seconds,
                    details=dict(result.output or {}),
                )
            elif result is not None and bool(result.success):
                live_task.state = "completed"
                live_task.result_data = dict(result.output or {})
                live_task.error_message = None
                live_task.completed_at = now_utc()
                live_task.updated_at = now_utc()
                live_task.claimed_by = None
                live_task.claimed_at = None
                live_task.lease_expires_at = None
                live_task.next_run_at = None
                add_task_log(
                    finalize_session,
                    task_id=live_task.id,
                    log_type="info",
                    message=result.message or "task completed",
                    details=result.output or {},
                    success=True,
                )
                response = WorkerRunResponse(
                    processed=True, task_id=task_id, message="completed"
                )
            else:
                failure_message = "task failed"
                if result is not None and result.message:
                    failure_message = result.message
                if result is not None and bool(result.terminal_failure):
                    self._mark_task_terminal_failure(
                        finalize_session,
                        live_task,
                        failure_message,
                    )
                    response = WorkerRunResponse(
                        processed=True,
                        task_id=task_id,
                        message=failure_message,
                    )
                else:
                    response = self._finalize_retry_or_dead_letter(
                        finalize_session,
                        live_task,
                        message=failure_message,
                        details={} if result is None else dict(result.output or {}),
                    )

            self._sync_ticket_state(finalize_session, live_ticket)
            update_heartbeat(finalize_session, effective_worker_id, "idle", None)
            finalize_session.commit()
            return response

    def _claim_next_task(self, session: Session, worker_id: str) -> Task | None:
        now = now_utc()
        statement = (
            select(Task)
            .where(Task.state.in_(["queued", "retrying"]))
            .where(or_(Task.next_run_at.is_(None), Task.next_run_at <= now))
            .where(or_(Task.cancel_requested.is_(None), Task.cancel_requested.is_(False)))
            .order_by(Task.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        candidates = list(session.exec(statement).all())
        for candidate in candidates:
            ticket = get_ticket_by_ticket_id(session, candidate.ticket_id)
            if ticket is None:
                self._mark_task_terminal_failure(
                    session,
                    candidate,
                    f"missing ticket: {candidate.ticket_id}",
                )
                continue
            if bool(ticket.paused):
                self._park_task_for_pause(session, candidate)
                continue
            if bool(ticket.approval_required) and ticket.approval_status == "pending":
                self._park_task_for_approval(session, candidate)
                continue
            if self._dependencies_satisfied(session, candidate.id):
                candidate.max_attempts = normalize_max_attempts(
                    candidate.max_attempts,
                    settings.default_max_attempts,
                )
                candidate.state = "running"
                candidate.attempt_count = int(candidate.attempt_count or 0) + 1
                candidate.started_at = now
                candidate.updated_at = now
                candidate.next_run_at = None
                candidate.claimed_by = worker_id
                candidate.claimed_at = now
                candidate.lease_expires_at = lease_expires_at(
                    now,
                    max(settings.task_lease_seconds, 10),
                )
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

    def _mark_task_terminal_failure(self, session: Session, task: Task, message: str) -> None:
        task.state = "failed"
        task.error_message = message
        task.completed_at = now_utc()
        task.updated_at = now_utc()
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.next_run_at = None
        add_task_log(
            session,
            task_id=task.id,
            log_type="error",
            message=message,
            success=False,
        )
        session.add(task)

    def _mark_task_cancelled(self, session: Session, task: Task) -> None:
        task.state = "cancelled"
        task.error_message = "cancel requested"
        task.completed_at = now_utc()
        task.updated_at = now_utc()
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.next_run_at = None
        add_task_log(
            session,
            task_id=task.id,
            log_type="warning",
            message="task cancelled after cancel request",
            success=False,
        )
        session.add(task)

    def _finalize_retry_or_dead_letter(
        self,
        session: Session,
        task: Task,
        *,
        message: str,
        details: dict | None = None,
    ) -> WorkerRunResponse:
        now = now_utc()
        attempt_count = int(task.attempt_count or 0)
        max_attempts = normalize_max_attempts(
            task.max_attempts,
            settings.default_max_attempts,
        )
        task.max_attempts = max_attempts
        retry_base_seconds, retry_max_seconds = self._retry_policy(task)

        if should_dead_letter(attempt_count, max_attempts):
            task.state = "dead_letter"
            task.error_message = message
            task.completed_at = now
            task.updated_at = now
            task.claimed_by = None
            task.claimed_at = None
            task.lease_expires_at = None
            task.next_run_at = None
            add_task_log(
                session,
                task_id=task.id,
                log_type="error",
                message=f"dead-lettered after {attempt_count} attempts: {message}",
                details=details or {},
                success=False,
            )
            session.add(task)
            return WorkerRunResponse(
                processed=True,
                task_id=task.id,
                message=task.error_message,
            )

        retry_delay = compute_retry_delay_seconds(
            attempt_count=attempt_count,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
        task.state = "retrying"
        task.error_message = message
        task.completed_at = None
        task.updated_at = now
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.next_run_at = compute_next_retry_at(
            now=now,
            attempt_count=attempt_count,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
        add_task_log(
            session,
            task_id=task.id,
            log_type="warning",
            message=f"task failed, retrying in {retry_delay}s: {message}",
            details=details or {},
            success=False,
        )
        session.add(task)
        return WorkerRunResponse(
            processed=True,
            task_id=task.id,
            message=f"retry scheduled in {retry_delay}s",
        )

    def _finalize_deferred_task(
        self,
        session: Session,
        task: Task,
        *,
        message: str,
        defer_seconds: int | None,
        details: dict | None = None,
    ) -> WorkerRunResponse:
        now = now_utc()
        retry_delay = max(int(defer_seconds or settings.event_wait_poll_interval_seconds), 1)
        task.state = "retrying"
        task.error_message = message
        task.completed_at = None
        task.updated_at = now
        task.attempt_count = max(int(task.attempt_count or 1) - 1, 0)
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        task.next_run_at = compute_next_retry_at(
            now=now,
            attempt_count=1,
            retry_base_seconds=retry_delay,
            retry_max_seconds=retry_delay,
        )
        add_task_log(
            session,
            task_id=task.id,
            log_type="info",
            message=f"task deferred for {retry_delay}s: {message}",
            details=details or {},
            success=None,
        )
        session.add(task)
        return WorkerRunResponse(
            processed=True,
            task_id=task.id,
            message=f"deferred for {retry_delay}s",
        )

    def _park_task_for_pause(self, session: Session, task: Task) -> None:
        task.state = "paused"
        task.updated_at = now_utc()
        task.next_run_at = None
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        session.add(task)

    def _park_task_for_approval(self, session: Session, task: Task) -> None:
        task.state = "blocked"
        task.updated_at = now_utc()
        task.next_run_at = None
        task.claimed_by = None
        task.claimed_at = None
        task.lease_expires_at = None
        session.add(task)

    @staticmethod
    def _retry_policy(task: Task) -> tuple[int, int]:
        retry_base_seconds = max(int(task.retry_base_seconds or settings.retry_base_seconds), 1)
        retry_max_seconds = max(int(task.retry_max_seconds or settings.retry_max_seconds), retry_base_seconds)
        return retry_base_seconds, retry_max_seconds

    @staticmethod
    def _task_timeout_exceeded(now, task: Task) -> bool:
        timeout_seconds = task.timeout_seconds
        if timeout_seconds is None or task.started_at is None:
            return False
        started_at = coerce_utc(task.started_at)
        if started_at is None:
            return False
        return (now - started_at).total_seconds() >= max(int(timeout_seconds), 1)

    def _lease_renewer_loop(
        self,
        bind,
        task_id: int,
        worker_id: str,
        stop_event: threading.Event,
    ) -> None:
        lease_seconds = max(int(settings.task_lease_seconds), 10)
        renew_interval = max(2, lease_seconds // 3)
        while not stop_event.wait(renew_interval):
            with Session(bind=bind, expire_on_commit=False) as lease_session:
                task = lease_session.exec(select(Task).where(Task.id == task_id)).first()
                if task is None:
                    lease_session.rollback()
                    return
                if task.state != "running" or task.claimed_by != worker_id:
                    lease_session.rollback()
                    return
                ticket = get_ticket_by_ticket_id(lease_session, task.ticket_id)
                if ticket is not None and bool(ticket.paused):
                    task.cancel_requested = True
                    task.cancel_requested_at = task.cancel_requested_at or now_utc()
                now = now_utc()
                task.lease_expires_at = lease_expires_at(now, lease_seconds)
                task.updated_at = now
                lease_session.add(task)
                update_heartbeat(lease_session, worker_id, "working", task_id)
                lease_session.commit()

    def _reap_stale_running_tasks(self, bind) -> None:
        now = now_utc()
        with Session(bind=bind, expire_on_commit=False) as session:
            stale_statement = select(Task).where(Task.state == "running").with_for_update(
                skip_locked=True
            )
            stale_tasks = list(session.exec(stale_statement).all())
            if not stale_tasks:
                session.rollback()
                return

            for task in stale_tasks:
                if self._task_timeout_exceeded(now, task):
                    task.attempt_count = int(task.attempt_count or 0) + 1
                    self._finalize_retry_or_dead_letter(
                        session,
                        task,
                        message=f"task timed out after {task.timeout_seconds}s",
                    )
                    continue
                if not is_stale_running_task(
                    now,
                    lease_expires_at_value=task.lease_expires_at,
                    started_at=task.started_at,
                    stale_task_timeout_seconds=max(
                        settings.stale_task_timeout_seconds,
                        30,
                    ),
                ):
                    continue
                if bool(task.cancel_requested):
                    self._mark_task_cancelled(session, task)
                    continue
                # Treat lease expiry as a failed run and route through retry policy.
                task.attempt_count = int(task.attempt_count or 0) + 1
                self._finalize_retry_or_dead_letter(
                    session,
                    task,
                    message="task lease expired while running",
                )
            session.commit()

    def _finalize_requested_cancellations(self, session: Session) -> int:
        pending_statement = (
            select(Task)
            .where(Task.cancel_requested.is_(True))
            .where(Task.state.in_(["queued", "retrying", "paused", "blocked"]))
            .with_for_update(skip_locked=True)
        )
        rows = list(session.exec(pending_statement).all())
        if not rows:
            return 0

        affected_ticket_ids: set[str] = set()
        for task in rows:
            affected_ticket_ids.add(task.ticket_id)
            self._mark_task_cancelled(session, task)

        for ticket_id in affected_ticket_ids:
            ticket = get_ticket_by_ticket_id(session, ticket_id)
            if ticket is not None:
                self._sync_ticket_state(session, ticket)
        return len(rows)
