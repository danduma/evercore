"""Schedule service for recurring or delayed ticket creation."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from evercore.models import TicketSchedule
from evercore.repositories import get_schedule_by_id, get_schedule_by_key, list_schedules
from evercore.schemas import ScheduleCreateRequest, TaskCreateRequest, TicketCreateRequest
from evercore.settings import settings
from evercore.time_utils import coerce_utc, now_utc

from .ticket_service import TicketService


class SchedulerService:
    def __init__(self, ticket_service: TicketService):
        self.ticket_service = ticket_service

    def create_schedule(self, session: Session, payload: ScheduleCreateRequest) -> TicketSchedule:
        if get_schedule_by_key(session, payload.schedule_key):
            raise ValueError(f"schedule already exists: {payload.schedule_key}")
        if payload.interval_seconds is None and payload.first_run_at is None:
            raise ValueError("either first_run_at or interval_seconds must be provided")

        first_run_at = coerce_utc(payload.first_run_at) or now_utc()
        schedule = TicketSchedule(
            schedule_key=payload.schedule_key.strip(),
            active=True,
            next_run_at=first_run_at,
            interval_seconds=payload.interval_seconds,
            ticket_title=payload.ticket_title,
            workflow_key=(payload.workflow_key or settings.default_workflow_key),
            workflow_version=payload.workflow_version,
            workflow_input=dict(payload.workflow_input or {}),
            context_data=dict(payload.context_data or {}),
            source_type=payload.source_type,
            task_key=payload.task_key,
            task_payload=dict(payload.task_payload or {}),
            task_max_attempts=payload.task_max_attempts,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(schedule)
        session.flush()
        return schedule

    def list_schedules(self, session: Session, limit: int = 200) -> list[TicketSchedule]:
        return list_schedules(session, limit=limit)

    def pause_schedule(self, session: Session, schedule_id: int) -> TicketSchedule:
        schedule = get_schedule_by_id(session, schedule_id)
        if schedule is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        schedule.active = False
        schedule.updated_at = now_utc()
        session.add(schedule)
        return schedule

    def resume_schedule(self, session: Session, schedule_id: int) -> TicketSchedule:
        schedule = get_schedule_by_id(session, schedule_id)
        if schedule is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        schedule.active = True
        if schedule.next_run_at is None:
            schedule.next_run_at = now_utc()
        schedule.updated_at = now_utc()
        session.add(schedule)
        return schedule

    def trigger_schedule_once(self, session: Session, schedule_id: int) -> str:
        schedule = get_schedule_by_id(session, schedule_id)
        if schedule is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        return self._run_schedule(session, schedule)

    def process_due_schedules(self, session: Session, limit: int = 10) -> int:
        now = now_utc()
        statement = (
            select(TicketSchedule)
            .where(TicketSchedule.active.is_(True))
            .where(TicketSchedule.next_run_at.is_not(None))
            .where(TicketSchedule.next_run_at <= now)
            .order_by(TicketSchedule.next_run_at.asc())
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
        due_rows = list(session.exec(statement).all())
        if not due_rows:
            return 0

        for schedule in due_rows:
            self._run_schedule(session, schedule)
        return len(due_rows)

    def _run_schedule(self, session: Session, schedule: TicketSchedule) -> str:
        now = now_utc()
        ticket = self.ticket_service.create_ticket(
            session,
            TicketCreateRequest(
                title=schedule.ticket_title,
                source_type=schedule.source_type,
                workflow_key=schedule.workflow_key,
                workflow_version=schedule.workflow_version,
                workflow_input=dict(schedule.workflow_input or {}),
                context_data=dict(schedule.context_data or {}),
            ),
        )
        if schedule.task_key:
            self.ticket_service.create_task(
                session,
                ticket.ticket_id,
                TaskCreateRequest(
                    task_key=schedule.task_key,
                    payload=dict(schedule.task_payload or {}),
                    max_attempts=schedule.task_max_attempts,
                ),
            )

        schedule.last_run_at = now
        if schedule.interval_seconds and schedule.interval_seconds > 0:
            schedule.next_run_at = now + timedelta(seconds=int(schedule.interval_seconds))
            schedule.active = True
        else:
            schedule.next_run_at = None
            schedule.active = False
        schedule.updated_at = now
        session.add(schedule)
        return ticket.ticket_id
