"""Ticket and task service methods."""

from __future__ import annotations

import uuid

from sqlmodel import Session

from evergreen_core.models import Task, Ticket
from evergreen_core.repositories import (
    add_task_dependencies,
    get_ticket_by_ticket_id,
    list_tasks_for_ticket,
    list_tickets,
)
from evergreen_core.schemas import TaskCreateRequest, TaskSummary, TicketCreateRequest, TicketSummary
from evergreen_core.settings import settings
from evergreen_core.time_utils import coerce_utc, now_utc
from evergreen_core.workflow_definitions import WorkflowLoader


class TicketService:
    def __init__(self, workflow_loader: WorkflowLoader):
        self.workflow_loader = workflow_loader

    def create_ticket(self, session: Session, payload: TicketCreateRequest) -> Ticket:
        workflow_key = (payload.workflow_key or settings.default_workflow_key).strip()
        workflow = self.workflow_loader.load(workflow_key)

        ticket = Ticket(
            ticket_id=f"tkt-{uuid.uuid4().hex[:10]}",
            title=payload.title,
            source_type=payload.source_type,
            workflow_key=workflow.key,
            workflow_version=payload.workflow_version or workflow.version,
            workflow_input=dict(payload.workflow_input or {}),
            context_data=dict(payload.context_data or {}),
            stage=workflow.initial_stage,
            status="active",
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(ticket)
        session.flush()
        return ticket

    def create_task(self, session: Session, ticket_id: str, payload: TaskCreateRequest) -> Task:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        task = Task(
            ticket_id=ticket.ticket_id,
            task_key=payload.task_key,
            state="queued",
            payload=dict(payload.payload or {}),
            result_data={},
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(task)
        session.flush()

        dependency_ids = [dep_id for dep_id in payload.depends_on_task_ids if dep_id > 0]
        add_task_dependencies(session, task.id, dependency_ids)

        ticket.stage = "running"
        ticket.updated_at = now_utc()
        session.add(ticket)
        return task

    def get_ticket_summary(self, session: Session, ticket_id: str) -> TicketSummary | None:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            return None

        tasks = list_tasks_for_ticket(session, ticket.ticket_id)
        return self._serialize_ticket(ticket, tasks)

    def list_ticket_summaries(self, session: Session, limit: int = 100) -> list[TicketSummary]:
        tickets = list_tickets(session, limit=limit)
        results: list[TicketSummary] = []
        for ticket in tickets:
            tasks = list_tasks_for_ticket(session, ticket.ticket_id)
            results.append(self._serialize_ticket(ticket, tasks))
        return results

    def _serialize_ticket(self, ticket: Ticket, tasks: list[Task]) -> TicketSummary:
        serialized_tasks = [
            TaskSummary(
                id=task.id,
                ticket_id=task.ticket_id,
                task_key=task.task_key,
                state=task.state,
                payload=task.payload,
                result_data=task.result_data,
                error_message=task.error_message,
                attempt_count=task.attempt_count,
                created_at=coerce_utc(task.created_at),
                started_at=coerce_utc(task.started_at),
                completed_at=coerce_utc(task.completed_at),
                updated_at=coerce_utc(task.updated_at),
            )
            for task in tasks
        ]

        return TicketSummary(
            id=ticket.id,
            ticket_id=ticket.ticket_id,
            title=ticket.title,
            workflow_key=ticket.workflow_key,
            workflow_version=ticket.workflow_version,
            workflow_input=ticket.workflow_input,
            stage=ticket.stage,
            status=ticket.status,
            source_type=ticket.source_type,
            context_data=ticket.context_data,
            created_at=coerce_utc(ticket.created_at),
            updated_at=coerce_utc(ticket.updated_at),
            completed_at=coerce_utc(ticket.completed_at),
            tasks=serialized_tasks,
        )
