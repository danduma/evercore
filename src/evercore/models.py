"""SQLModel entities for standalone evercore."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Dict

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel

from .time_utils import now_utc


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: str = Field(index=True, unique=True)
    title: Optional[str] = None
    workflow_key: str = Field(default="default_ticket", index=True)
    workflow_version: Optional[str] = None
    workflow_input: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    stage: str = Field(default="queued", index=True)
    status: str = Field(default="active", index=True)
    paused: bool = Field(default=False, index=True)
    paused_at: Optional[datetime] = Field(default=None)
    resumed_at: Optional[datetime] = Field(default=None)
    approval_required: bool = Field(default=False, index=True)
    approval_status: str = Field(default="none", index=True)
    approval_requested_at: Optional[datetime] = Field(default=None)
    approval_decided_at: Optional[datetime] = Field(default=None)
    approval_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_type: Optional[str] = None
    context_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    completed_at: Optional[datetime] = None


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: str = Field(index=True, foreign_key="tickets.ticket_id")
    task_key: str = Field(index=True)
    state: str = Field(default="queued", index=True)
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    cancel_requested: bool = Field(default=False, index=True)
    cancel_requested_at: Optional[datetime] = Field(default=None)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    retry_base_seconds: Optional[int] = Field(default=None)
    retry_max_seconds: Optional[int] = Field(default=None)
    timeout_seconds: Optional[int] = Field(default=None)
    next_run_at: Optional[datetime] = Field(default=None, index=True)
    claimed_by: Optional[str] = Field(default=None, index=True)
    claimed_at: Optional[datetime] = Field(default=None, index=True)
    lease_expires_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now_utc)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=now_utc)


class TaskDependency(SQLModel, table=True):
    __tablename__ = "task_dependencies"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="tasks.id")
    depends_on_task_id: int = Field(index=True, foreign_key="tasks.id")
    created_at: datetime = Field(default_factory=now_utc)


class TaskLog(SQLModel, table=True):
    __tablename__ = "task_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="tasks.id")
    log_type: str = Field(default="info", index=True)
    message: str = Field(sa_column=Column(Text))
    details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    success: Optional[bool] = None
    created_at: datetime = Field(default_factory=now_utc)


class WorkerHeartbeat(SQLModel, table=True):
    __tablename__ = "worker_heartbeats"

    id: Optional[int] = Field(default=None, primary_key=True)
    worker_id: str = Field(index=True, unique=True)
    state: str = Field(default="idle", index=True)
    current_task_id: Optional[int] = Field(default=None, index=True)
    last_seen_at: datetime = Field(default_factory=now_utc, index=True)


class TicketEvent(SQLModel, table=True):
    __tablename__ = "ticket_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: str = Field(index=True, foreign_key="tickets.ticket_id")
    event_type: str = Field(index=True)
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    consumed_at: Optional[datetime] = Field(default=None, index=True)
    consumed_by_task_id: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=now_utc, index=True)


class TicketSchedule(SQLModel, table=True):
    __tablename__ = "ticket_schedules"

    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_key: str = Field(index=True, unique=True)
    active: bool = Field(default=True, index=True)
    next_run_at: Optional[datetime] = Field(default=None, index=True)
    interval_seconds: Optional[int] = Field(default=None)
    ticket_title: Optional[str] = None
    workflow_key: Optional[str] = Field(default=None, index=True)
    workflow_version: Optional[str] = None
    workflow_input: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    context_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_type: Optional[str] = None
    task_key: Optional[str] = Field(default=None, index=True)
    task_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    task_max_attempts: Optional[int] = Field(default=None)
    last_run_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
