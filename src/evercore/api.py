"""Standalone evercore FastAPI application."""

from __future__ import annotations

from collections.abc import Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session, select

from evercore.db import create_db_and_tables, get_session
from evercore.executors import ExecutorRegistry
from evercore.models import Task
from evercore.schemas import (
    ScheduleCreateRequest,
    ScheduleSummary,
    ScheduleTriggerResponse,
    TaskCancelRequestResponse,
    TaskCreateRequest,
    TicketApprovalDecisionRequest,
    TicketApprovalRequest,
    TicketCreateRequest,
    TicketEventCreateRequest,
    TicketEventSummary,
    TicketTransitionRequest,
    TicketSummary,
    WorkerRunResponse,
)
from evercore.services import SchedulerService, TicketService, WorkerService
from evercore.settings import settings
from evercore.time_utils import now_utc
from evercore.workflow import WorkflowLoader

app = FastAPI(title="evercore", version="0.1.0")

workflow_loader = WorkflowLoader(settings.workflow_dir_path)
ticket_service = TicketService(workflow_loader)
scheduler_service = SchedulerService(ticket_service)
worker_service = WorkerService(ExecutorRegistry.default())


def db_session() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.on_event("startup")
def startup() -> None:
    create_db_and_tables()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "evercore"}


@app.post("/tickets", response_model=TicketSummary, status_code=201)
def create_ticket(payload: TicketCreateRequest, session: Session = Depends(db_session)) -> TicketSummary:
    try:
        ticket = ticket_service.create_ticket(session, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket.ticket_id)
    if summary is None:
        raise HTTPException(status_code=500, detail="ticket was created but could not be reloaded")
    return summary


@app.get("/tickets", response_model=list[TicketSummary])
def list_tickets(
    session: Session = Depends(db_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TicketSummary]:
    return ticket_service.list_ticket_summaries(session, limit=limit)


@app.get("/tickets/{ticket_id}", response_model=TicketSummary)
def get_ticket(ticket_id: str, session: Session = Depends(db_session)) -> TicketSummary:
    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/tasks", response_model=TicketSummary, status_code=201)
def create_task(
    ticket_id: str,
    payload: TaskCreateRequest,
    session: Session = Depends(db_session),
) -> TicketSummary:
    try:
        ticket_service.create_task(session, ticket_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/workers/run-once", response_model=WorkerRunResponse)
def run_worker_once(
    worker_id: str | None = Query(default=None),
    session: Session = Depends(db_session),
) -> WorkerRunResponse:
    scheduler_service.process_due_schedules(session, limit=settings.schedule_batch_size)
    return worker_service.process_once(session, worker_id=worker_id)


@app.post("/tasks/{task_id}/cancel-request", response_model=TaskCancelRequestResponse)
def request_task_cancel(task_id: int, session: Session = Depends(db_session)) -> TaskCancelRequestResponse:
    task = session.exec(select(Task).where(Task.id == task_id)).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    if task.state in {"completed", "failed", "dead_letter", "cancelled"}:
        return TaskCancelRequestResponse(
            task_id=task.id,
            cancel_requested=bool(task.cancel_requested),
            state=task.state,
        )

    task.cancel_requested = True
    task.cancel_requested_at = task.cancel_requested_at or now_utc()
    session.add(task)
    session.commit()
    session.refresh(task)
    return TaskCancelRequestResponse(
        task_id=task.id,
        cancel_requested=True,
        state=task.state,
    )


@app.post("/tickets/{ticket_id}/transition", response_model=TicketSummary)
def transition_ticket(
    ticket_id: str,
    payload: TicketTransitionRequest,
    session: Session = Depends(db_session),
) -> TicketSummary:
    try:
        ticket_service.transition_ticket(
            session,
            ticket_id,
            target_stage=payload.target_stage,
            transition_context=dict(payload.transition_context or {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/pause", response_model=TicketSummary)
def pause_ticket(ticket_id: str, session: Session = Depends(db_session)) -> TicketSummary:
    try:
        ticket_service.pause_ticket(session, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/resume", response_model=TicketSummary)
def resume_ticket(ticket_id: str, session: Session = Depends(db_session)) -> TicketSummary:
    try:
        ticket_service.resume_ticket(session, ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/approval/request", response_model=TicketSummary)
def request_ticket_approval(
    ticket_id: str,
    payload: TicketApprovalRequest,
    session: Session = Depends(db_session),
) -> TicketSummary:
    try:
        ticket_service.request_approval(session, ticket_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/approval/approve", response_model=TicketSummary)
def approve_ticket(
    ticket_id: str,
    payload: TicketApprovalDecisionRequest,
    session: Session = Depends(db_session),
) -> TicketSummary:
    try:
        ticket_service.approve_ticket(session, ticket_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/approval/reject", response_model=TicketSummary)
def reject_ticket(
    ticket_id: str,
    payload: TicketApprovalDecisionRequest,
    session: Session = Depends(db_session),
) -> TicketSummary:
    try:
        ticket_service.reject_ticket(session, ticket_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    summary = ticket_service.get_ticket_summary(session, ticket_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return summary


@app.post("/tickets/{ticket_id}/events", response_model=TicketEventSummary, status_code=201)
def publish_ticket_event(
    ticket_id: str,
    payload: TicketEventCreateRequest,
    session: Session = Depends(db_session),
) -> TicketEventSummary:
    try:
        row = ticket_service.publish_event(
            session,
            ticket_id,
            event_type=payload.event_type,
            payload=dict(payload.payload or {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TicketEventSummary(
        id=row.id,
        ticket_id=row.ticket_id,
        event_type=row.event_type,
        payload=row.payload,
        consumed_at=row.consumed_at,
        consumed_by_task_id=row.consumed_by_task_id,
        created_at=row.created_at,
    )


@app.get("/tickets/{ticket_id}/events", response_model=list[TicketEventSummary])
def get_ticket_events(
    ticket_id: str,
    session: Session = Depends(db_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TicketEventSummary]:
    try:
        rows = ticket_service.get_ticket_events(session, ticket_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        TicketEventSummary(
            id=row.id,
            ticket_id=row.ticket_id,
            event_type=row.event_type,
            payload=row.payload,
            consumed_at=row.consumed_at,
            consumed_by_task_id=row.consumed_by_task_id,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _serialize_schedule(row) -> ScheduleSummary:
    return ScheduleSummary(
        id=row.id,
        schedule_key=row.schedule_key,
        active=bool(row.active),
        next_run_at=row.next_run_at,
        interval_seconds=row.interval_seconds,
        ticket_title=row.ticket_title,
        workflow_key=row.workflow_key,
        workflow_version=row.workflow_version,
        workflow_input=row.workflow_input or {},
        context_data=row.context_data or {},
        source_type=row.source_type,
        task_key=row.task_key,
        task_payload=row.task_payload or {},
        task_max_attempts=row.task_max_attempts,
        last_run_at=row.last_run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.post("/schedules", response_model=ScheduleSummary, status_code=201)
def create_schedule(
    payload: ScheduleCreateRequest,
    session: Session = Depends(db_session),
) -> ScheduleSummary:
    try:
        row = scheduler_service.create_schedule(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_schedule(row)


@app.get("/schedules", response_model=list[ScheduleSummary])
def get_schedules(
    session: Session = Depends(db_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ScheduleSummary]:
    rows = scheduler_service.list_schedules(session, limit=limit)
    return [_serialize_schedule(row) for row in rows]


@app.post("/schedules/{schedule_id}/pause", response_model=ScheduleSummary)
def pause_schedule(schedule_id: int, session: Session = Depends(db_session)) -> ScheduleSummary:
    try:
        row = scheduler_service.pause_schedule(session, schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_schedule(row)


@app.post("/schedules/{schedule_id}/resume", response_model=ScheduleSummary)
def resume_schedule(schedule_id: int, session: Session = Depends(db_session)) -> ScheduleSummary:
    try:
        row = scheduler_service.resume_schedule(session, schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_schedule(row)


@app.post("/schedules/{schedule_id}/trigger", response_model=ScheduleTriggerResponse)
def trigger_schedule(schedule_id: int, session: Session = Depends(db_session)) -> ScheduleTriggerResponse:
    try:
        ticket_id = scheduler_service.trigger_schedule_once(session, schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScheduleTriggerResponse(schedule_id=schedule_id, triggered_ticket_id=ticket_id)


def main() -> None:
    uvicorn.run(
        "evercore.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
