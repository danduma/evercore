"""Ticket and task service methods."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlmodel import Session

from evercore.models import Task, Ticket, TicketEvent
from evercore.repositories import (
    add_task_dependencies,
    add_ticket_event,
    get_ticket_by_ticket_id,
    list_ticket_events,
    list_tasks_for_ticket,
    list_tickets,
)
from evercore.schemas import TaskCreateRequest, TaskSummary, TicketCreateRequest, TicketSummary
from evercore.settings import settings
from evercore.time_utils import coerce_utc, now_utc
from evercore.workflow import WorkflowLoader


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
            approval_required=False,
            approval_status="none",
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

        initial_state = "queued"
        if bool(ticket.paused):
            initial_state = "paused"
        elif bool(ticket.approval_required) and ticket.approval_status == "pending":
            initial_state = "blocked"

        task = Task(
            ticket_id=ticket.ticket_id,
            task_key=payload.task_key,
            state=initial_state,
            payload=dict(payload.payload or {}),
            result_data={},
            max_attempts=payload.max_attempts or settings.default_max_attempts,
            retry_base_seconds=payload.retry_base_seconds,
            retry_max_seconds=payload.retry_max_seconds,
            timeout_seconds=payload.timeout_seconds,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(task)
        session.flush()

        dependency_ids = [dep_id for dep_id in payload.depends_on_task_ids if dep_id > 0]
        add_task_dependencies(session, task.id, dependency_ids)

        if initial_state == "blocked":
            ticket.stage = "pending_approval"
            ticket.status = "waiting_approval"
        elif initial_state == "paused":
            ticket.status = "paused"
        else:
            ticket.stage = "running"
            ticket.status = "active"
        ticket.updated_at = now_utc()
        session.add(ticket)
        return task

    def transition_ticket(
        self,
        session: Session,
        ticket_id: str,
        *,
        target_stage: str | None = None,
        transition_context: dict | None = None,
    ) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        workflow = self.workflow_loader.load(ticket.workflow_key)
        stage_def = workflow.stage_by_id(ticket.stage)
        if stage_def is None:
            raise ValueError(f"current stage '{ticket.stage}' is not defined in workflow '{workflow.key}'")

        chosen_transition = None
        for transition in stage_def.transitions:
            if target_stage and transition.target != target_stage:
                continue
            if self._evaluate_when(transition.when, ticket, transition_context):
                chosen_transition = transition
                break

        if chosen_transition is None:
            if target_stage:
                raise ValueError(
                    f"transition to '{target_stage}' is not allowed from stage '{ticket.stage}'"
                )
            raise ValueError(f"no valid transition from stage '{ticket.stage}'")

        ticket.stage = chosen_transition.target
        if ticket.stage == "finished":
            ticket.status = "completed"
            ticket.completed_at = ticket.completed_at or now_utc()
        elif ticket.stage == "pending_approval":
            ticket.approval_required = True
            if ticket.approval_status == "none":
                ticket.approval_status = "pending"
            ticket.status = "waiting_approval"
        elif ticket.paused:
            ticket.status = "paused"
        else:
            ticket.status = "active"
        ticket.updated_at = now_utc()
        session.add(ticket)
        return ticket

    def request_approval(
        self,
        session: Session,
        ticket_id: str,
        *,
        notes: str | None = None,
    ) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        now = now_utc()
        ticket.approval_required = True
        ticket.approval_status = "pending"
        ticket.approval_requested_at = ticket.approval_requested_at or now
        ticket.approval_decided_at = None
        ticket.approval_notes = notes
        ticket.stage = "pending_approval"
        ticket.status = "waiting_approval"
        ticket.updated_at = now
        session.add(ticket)

        tasks = list_tasks_for_ticket(session, ticket.ticket_id)
        for task in tasks:
            if task.state in {"queued", "retrying"}:
                task.state = "blocked"
                task.next_run_at = None
                task.updated_at = now
                session.add(task)
        return ticket

    def approve_ticket(
        self,
        session: Session,
        ticket_id: str,
        *,
        notes: str | None = None,
    ) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        now = now_utc()
        ticket.approval_required = True
        ticket.approval_status = "approved"
        ticket.approval_decided_at = now
        ticket.approval_notes = notes
        if ticket.stage == "pending_approval":
            ticket.stage = "running"
        ticket.status = "paused" if ticket.paused else "active"
        ticket.updated_at = now
        session.add(ticket)

        tasks = list_tasks_for_ticket(session, ticket.ticket_id)
        if not ticket.paused:
            for task in tasks:
                if task.state == "blocked":
                    task.state = "queued"
                    task.next_run_at = now
                    task.updated_at = now
                    session.add(task)
        return ticket

    def reject_ticket(
        self,
        session: Session,
        ticket_id: str,
        *,
        notes: str | None = None,
    ) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        now = now_utc()
        ticket.approval_required = True
        ticket.approval_status = "rejected"
        ticket.approval_decided_at = now
        ticket.approval_notes = notes
        ticket.stage = "review"
        ticket.status = "attention"
        ticket.updated_at = now
        session.add(ticket)
        return ticket

    def pause_ticket(self, session: Session, ticket_id: str) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        now = now_utc()
        ticket.paused = True
        ticket.paused_at = now
        ticket.status = "paused"
        ticket.updated_at = now
        session.add(ticket)

        tasks = list_tasks_for_ticket(session, ticket.ticket_id)
        for task in tasks:
            if task.state in {"queued", "retrying", "blocked"}:
                task.state = "paused"
                task.next_run_at = None
                task.updated_at = now
                session.add(task)
            elif task.state == "running":
                task.cancel_requested = True
                task.cancel_requested_at = now
                task.updated_at = now
                session.add(task)
        return ticket

    def resume_ticket(self, session: Session, ticket_id: str) -> Ticket:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")

        now = now_utc()
        ticket.paused = False
        ticket.resumed_at = now
        if bool(ticket.approval_required) and ticket.approval_status == "pending":
            ticket.stage = "pending_approval"
            ticket.status = "waiting_approval"
        elif ticket.stage != "finished":
            ticket.status = "active"
        ticket.updated_at = now
        session.add(ticket)

        tasks = list_tasks_for_ticket(session, ticket.ticket_id)
        for task in tasks:
            if task.state != "paused":
                continue
            if bool(ticket.approval_required) and ticket.approval_status == "pending":
                task.state = "blocked"
                task.next_run_at = None
            else:
                task.state = "queued"
                task.next_run_at = now
            task.updated_at = now
            session.add(task)
        return ticket

    def publish_event(
        self,
        session: Session,
        ticket_id: str,
        *,
        event_type: str,
        payload: dict | None = None,
    ) -> TicketEvent:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")
        row = add_ticket_event(
            session,
            ticket_id=ticket_id,
            event_type=event_type.strip(),
            payload=payload or {},
        )
        session.flush()
        return row

    def get_ticket_events(self, session: Session, ticket_id: str, limit: int = 100) -> list[TicketEvent]:
        ticket = get_ticket_by_ticket_id(session, ticket_id)
        if ticket is None:
            raise ValueError(f"ticket not found: {ticket_id}")
        return list_ticket_events(session, ticket_id=ticket_id, limit=limit)

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
                cancel_requested=bool(task.cancel_requested),
                cancel_requested_at=coerce_utc(task.cancel_requested_at),
                attempt_count=task.attempt_count,
                max_attempts=task.max_attempts,
                retry_base_seconds=task.retry_base_seconds,
                retry_max_seconds=task.retry_max_seconds,
                timeout_seconds=task.timeout_seconds,
                next_run_at=coerce_utc(task.next_run_at),
                claimed_by=task.claimed_by,
                claimed_at=coerce_utc(task.claimed_at),
                lease_expires_at=coerce_utc(task.lease_expires_at),
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
            paused=bool(ticket.paused),
            paused_at=coerce_utc(ticket.paused_at),
            resumed_at=coerce_utc(ticket.resumed_at),
            approval_required=bool(ticket.approval_required),
            approval_status=ticket.approval_status or "none",
            approval_requested_at=coerce_utc(ticket.approval_requested_at),
            approval_decided_at=coerce_utc(ticket.approval_decided_at),
            approval_notes=ticket.approval_notes,
            source_type=ticket.source_type,
            context_data=ticket.context_data,
            created_at=coerce_utc(ticket.created_at),
            updated_at=coerce_utc(ticket.updated_at),
            completed_at=coerce_utc(ticket.completed_at),
            tasks=serialized_tasks,
        )

    def _evaluate_when(
        self,
        when: str | None,
        ticket: Ticket,
        transition_context: dict | None,
    ) -> bool:
        expression = (when or "").strip()
        if not expression:
            return True
        if expression.lower() in {"true", "always"}:
            return True
        if expression.lower() in {"false", "never"}:
            return False

        left, operator, right = self._split_comparison(expression)
        if operator:
            left_value = self._lookup(left, ticket, transition_context)
            right_value = self._coerce_literal(right)
            if operator == "==":
                return left_value == right_value
            return left_value != right_value

        invert = False
        lookup_key = expression
        if expression.startswith("not "):
            invert = True
            lookup_key = expression[4:].strip()
        elif expression.startswith("!"):
            invert = True
            lookup_key = expression[1:].strip()

        resolved = bool(self._lookup(lookup_key, ticket, transition_context))
        return not resolved if invert else resolved

    @staticmethod
    def _split_comparison(expression: str) -> tuple[str, str | None, str]:
        for operator in ("==", "!="):
            if operator in expression:
                left, right = expression.split(operator, 1)
                return left.strip(), operator, right.strip()
        return expression.strip(), None, ""

    @staticmethod
    def _coerce_literal(raw_value: str) -> object:
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        if value.lower() == "none" or value.lower() == "null":
            return None
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    @staticmethod
    def _lookup(path: str, ticket: Ticket, transition_context: dict | None) -> object:
        token = path.strip()
        if token.startswith("ticket."):
            return TicketService._dig(vars(ticket), token.split(".", 1)[1])
        if token.startswith("context."):
            return TicketService._dig(transition_context or {}, token.split(".", 1)[1])
        if token.startswith("workflow_input."):
            return TicketService._dig(ticket.workflow_input or {}, token.split(".", 1)[1])
        if token.startswith("task_result."):
            return TicketService._dig(transition_context or {}, token.split(".", 1)[1])

        if transition_context and token in transition_context:
            return transition_context[token]
        if ticket.workflow_input and token in ticket.workflow_input:
            return ticket.workflow_input[token]
        if hasattr(ticket, token):
            return getattr(ticket, token)
        return None

    @staticmethod
    def _dig(root: object, dotted_path: str) -> object:
        current = root
        for key in TicketService._path_parts(dotted_path):
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    @staticmethod
    def _path_parts(path: str) -> Iterable[str]:
        for part in path.split("."):
            cleaned = part.strip()
            if cleaned:
                yield cleaned
