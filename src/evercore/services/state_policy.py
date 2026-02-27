"""Ticket state policy primitives for worker-side lifecycle updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from evercore.models import Task, Ticket
from evercore.time_utils import now_utc


@dataclass
class TicketStateUpdate:
    """Resolved ticket lifecycle state after task processing."""

    stage: str
    status: str
    completed_at: datetime | None


class TicketStatePolicy(Protocol):
    """Policy interface for deciding ticket state from task set."""

    def resolve(self, ticket: Ticket, tasks: list[Task]) -> TicketStateUpdate:
        """Return the next ticket state from current ticket + tasks."""


class DefaultTicketStatePolicy:
    """Default task-driven policy for standalone evercore."""

    def resolve(self, ticket: Ticket, tasks: list[Task]) -> TicketStateUpdate:
        if bool(ticket.paused):
            return TicketStateUpdate(stage=ticket.stage, status="paused", completed_at=ticket.completed_at)

        if bool(ticket.approval_required) and ticket.approval_status == "pending":
            return TicketStateUpdate(stage="pending_approval", status="waiting_approval", completed_at=None)

        if bool(ticket.approval_required) and ticket.approval_status == "rejected":
            return TicketStateUpdate(stage="review", status="attention", completed_at=None)

        if not tasks:
            return TicketStateUpdate(stage="queued", status="active", completed_at=None)

        any_failed = any(task.state in {"failed", "dead_letter"} for task in tasks)
        any_running = any(task.state == "running" for task in tasks)
        any_queued = any(task.state in {"queued", "retrying"} for task in tasks)
        all_completed = all(task.state == "completed" for task in tasks)

        if any_failed:
            return TicketStateUpdate(stage="review", status="attention", completed_at=None)
        if all_completed:
            return TicketStateUpdate(stage="finished", status="completed", completed_at=now_utc())
        if any_running or any_queued:
            return TicketStateUpdate(stage="running", status="active", completed_at=None)
        return TicketStateUpdate(stage="running", status="active", completed_at=None)
