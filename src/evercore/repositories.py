"""Repository helpers for standalone evercore entities."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from .models import (
    Task,
    TaskDependency,
    TaskLog,
    Ticket,
    TicketEvent,
    TicketSchedule,
    WorkerHeartbeat,
)
from .time_utils import now_utc


def get_ticket_by_ticket_id(session: Session, ticket_id: str) -> Optional[Ticket]:
    statement = select(Ticket).where(Ticket.ticket_id == ticket_id)
    return session.exec(statement).first()


def list_tickets(session: Session, limit: int = 100) -> list[Ticket]:
    statement = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
    return list(session.exec(statement).all())


def list_tasks_for_ticket(session: Session, ticket_id: str) -> list[Task]:
    statement = select(Task).where(Task.ticket_id == ticket_id).order_by(Task.created_at.asc())
    return list(session.exec(statement).all())


def add_task_dependencies(session: Session, task_id: int, depends_on_task_ids: list[int]) -> None:
    for depends_on_task_id in depends_on_task_ids:
        dependency = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_task_id)
        session.add(dependency)


def list_dependencies(session: Session, task_id: int) -> list[TaskDependency]:
    statement = select(TaskDependency).where(TaskDependency.task_id == task_id)
    return list(session.exec(statement).all())


def list_queued_tasks(session: Session) -> list[Task]:
    now = now_utc()
    statement = (
        select(Task)
        .where(Task.state.in_(["queued", "retrying"]))
        .where(or_(Task.next_run_at.is_(None), Task.next_run_at <= now))
        .order_by(Task.created_at.asc())
    )
    return list(session.exec(statement).all())


def get_task(session: Session, task_id: int) -> Optional[Task]:
    statement = select(Task).where(Task.id == task_id)
    return session.exec(statement).first()


def update_heartbeat(session: Session, worker_id: str, state: str, current_task_id: int | None) -> None:
    statement = select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id)
    row = session.exec(statement).first()
    if row is None:
        row = WorkerHeartbeat(
            worker_id=worker_id,
            state=state,
            current_task_id=current_task_id,
            last_seen_at=now_utc(),
        )
        session.add(row)
        return

    row.state = state
    row.current_task_id = current_task_id
    row.last_seen_at = now_utc()
    session.add(row)


def add_task_log(
    session: Session,
    *,
    task_id: int,
    message: str,
    log_type: str = "info",
    success: bool | None = None,
    details: dict | None = None,
) -> TaskLog:
    row = TaskLog(
        task_id=task_id,
        message=message,
        log_type=log_type,
        success=success,
        details=details or {},
    )
    session.add(row)
    return row


def add_ticket_event(
    session: Session,
    *,
    ticket_id: str,
    event_type: str,
    payload: dict | None = None,
) -> TicketEvent:
    row = TicketEvent(
        ticket_id=ticket_id,
        event_type=event_type,
        payload=payload or {},
    )
    session.add(row)
    return row


def list_ticket_events(session: Session, ticket_id: str, limit: int = 100) -> list[TicketEvent]:
    statement = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket_id)
        .order_by(TicketEvent.created_at.desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())


def get_unconsumed_ticket_event(
    session: Session,
    *,
    ticket_id: str,
    event_type: str,
) -> Optional[TicketEvent]:
    statement = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket_id)
        .where(TicketEvent.event_type == event_type)
        .where(TicketEvent.consumed_at.is_(None))
        .order_by(TicketEvent.created_at.asc())
    )
    return session.exec(statement).first()


def get_schedule_by_id(session: Session, schedule_id: int) -> Optional[TicketSchedule]:
    statement = select(TicketSchedule).where(TicketSchedule.id == schedule_id)
    return session.exec(statement).first()


def get_schedule_by_key(session: Session, schedule_key: str) -> Optional[TicketSchedule]:
    statement = select(TicketSchedule).where(TicketSchedule.schedule_key == schedule_key)
    return session.exec(statement).first()


def list_schedules(session: Session, limit: int = 200) -> list[TicketSchedule]:
    statement = (
        select(TicketSchedule)
        .order_by(TicketSchedule.created_at.asc())
        .limit(limit)
    )
    return list(session.exec(statement).all())
