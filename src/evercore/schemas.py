"""API schemas for standalone evercore."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    title: Optional[str] = None
    source_type: Optional[str] = None
    workflow_key: Optional[str] = None
    workflow_version: Optional[str] = None
    workflow_input: dict[str, Any] = Field(default_factory=dict)
    context_data: dict[str, Any] = Field(default_factory=dict)


class TaskCreateRequest(BaseModel):
    task_key: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on_task_ids: list[int] = Field(default_factory=list)
    max_attempts: Optional[int] = Field(default=None, ge=1, le=20)
    retry_base_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    retry_max_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)


class TaskSummary(BaseModel):
    id: int
    ticket_id: str
    task_key: str
    state: str
    payload: dict[str, Any]
    result_data: dict[str, Any]
    error_message: Optional[str]
    cancel_requested: bool
    cancel_requested_at: Optional[datetime]
    attempt_count: int
    max_attempts: int
    retry_base_seconds: Optional[int]
    retry_max_seconds: Optional[int]
    timeout_seconds: Optional[int]
    next_run_at: Optional[datetime]
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]
    lease_expires_at: Optional[datetime]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    updated_at: datetime


class TicketSummary(BaseModel):
    id: int
    ticket_id: str
    title: Optional[str]
    workflow_key: str
    workflow_version: Optional[str]
    workflow_input: dict[str, Any]
    stage: str
    status: str
    paused: bool
    paused_at: Optional[datetime]
    resumed_at: Optional[datetime]
    approval_required: bool
    approval_status: str
    approval_requested_at: Optional[datetime]
    approval_decided_at: Optional[datetime]
    approval_notes: Optional[str]
    source_type: Optional[str]
    context_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    tasks: list[TaskSummary] = Field(default_factory=list)


class WorkerRunResponse(BaseModel):
    processed: bool
    task_id: Optional[int] = None
    message: Optional[str] = None


class TaskCancelRequestResponse(BaseModel):
    task_id: int
    cancel_requested: bool
    state: str


class TicketTransitionRequest(BaseModel):
    target_stage: str = Field(..., min_length=1)
    transition_context: dict[str, Any] = Field(default_factory=dict)


class TicketApprovalRequest(BaseModel):
    notes: Optional[str] = None


class TicketApprovalDecisionRequest(BaseModel):
    notes: Optional[str] = None


class TicketEventCreateRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class TicketEventSummary(BaseModel):
    id: int
    ticket_id: str
    event_type: str
    payload: dict[str, Any]
    consumed_at: Optional[datetime]
    consumed_by_task_id: Optional[int]
    created_at: datetime


class ScheduleCreateRequest(BaseModel):
    schedule_key: str = Field(..., min_length=1)
    first_run_at: Optional[datetime] = None
    interval_seconds: Optional[int] = Field(default=None, ge=1, le=86400 * 365)
    ticket_title: Optional[str] = None
    workflow_key: Optional[str] = None
    workflow_version: Optional[str] = None
    workflow_input: dict[str, Any] = Field(default_factory=dict)
    context_data: dict[str, Any] = Field(default_factory=dict)
    source_type: Optional[str] = None
    task_key: Optional[str] = None
    task_payload: dict[str, Any] = Field(default_factory=dict)
    task_max_attempts: Optional[int] = Field(default=None, ge=1, le=20)


class ScheduleSummary(BaseModel):
    id: int
    schedule_key: str
    active: bool
    next_run_at: Optional[datetime]
    interval_seconds: Optional[int]
    ticket_title: Optional[str]
    workflow_key: Optional[str]
    workflow_version: Optional[str]
    workflow_input: dict[str, Any]
    context_data: dict[str, Any]
    source_type: Optional[str]
    task_key: Optional[str]
    task_payload: dict[str, Any]
    task_max_attempts: Optional[int]
    last_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ScheduleTriggerResponse(BaseModel):
    schedule_id: int
    triggered_ticket_id: str
