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


class TaskSummary(BaseModel):
    id: int
    ticket_id: str
    task_key: str
    state: str
    payload: dict[str, Any]
    result_data: dict[str, Any]
    error_message: Optional[str]
    attempt_count: int
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
