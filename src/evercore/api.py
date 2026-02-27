"""Standalone evercore FastAPI application."""

from __future__ import annotations

from collections.abc import Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session

from evercore.db import create_db_and_tables, get_session
from evercore.executors import ExecutorRegistry
from evercore.schemas import TaskCreateRequest, TicketCreateRequest, TicketSummary, WorkerRunResponse
from evercore.services import TicketService, WorkerService
from evercore.settings import settings
from evercore.workflow import WorkflowLoader

app = FastAPI(title="evercore", version="0.1.0")

workflow_loader = WorkflowLoader(settings.workflow_dir_path)
ticket_service = TicketService(workflow_loader)
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
    return worker_service.process_once(session, worker_id=worker_id)


def main() -> None:
    uvicorn.run(
        "evercore.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
