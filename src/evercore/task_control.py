"""Cooperative control helper for long-running executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlmodel import Session

from .models import Task, Ticket
from .repositories import get_task, get_ticket_by_ticket_id


@dataclass
class TaskControlSnapshot:
    task_exists: bool
    task_state: str | None
    cancel_requested: bool
    ticket_exists: bool
    ticket_paused: bool
    approval_pending: bool

    @property
    def should_stop(self) -> bool:
        if not self.task_exists or not self.ticket_exists:
            return True
        return bool(self.cancel_requested or self.ticket_paused or self.approval_pending)


class TaskControl:
    """Allows executor loops to cooperatively stop for pause/cancel/approval gates."""

    def __init__(self, session_factory: Callable[[], Session], task_id: int, ticket_id: str):
        self._session_factory = session_factory
        self.task_id = int(task_id)
        self.ticket_id = ticket_id

    def snapshot(self) -> TaskControlSnapshot:
        session = self._session_factory()
        try:
            task: Task | None = get_task(session, self.task_id)
            ticket: Ticket | None = get_ticket_by_ticket_id(session, self.ticket_id)
            task_exists = task is not None
            ticket_exists = ticket is not None
            approval_pending = bool(
                ticket_exists
                and ticket
                and ticket.approval_required
                and ticket.approval_status == "pending"
            )
            return TaskControlSnapshot(
                task_exists=task_exists,
                task_state=None if task is None else task.state,
                cancel_requested=bool(task.cancel_requested) if task else False,
                ticket_exists=ticket_exists,
                ticket_paused=bool(ticket.paused) if ticket else False,
                approval_pending=approval_pending,
            )
        finally:
            try:
                session.rollback()
            except Exception:
                pass
            session.close()

    def should_stop(self) -> bool:
        return self.snapshot().should_stop
