"""Executor protocol and result objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .models import Task, Ticket


@dataclass
class ExecutionResult:
    success: bool
    message: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    defer: bool = False
    defer_seconds: int | None = None
    terminal_failure: bool = False


class TaskExecutor(ABC):
    @abstractmethod
    def execute(self, ticket: Ticket, task: Task) -> ExecutionResult:
        """Execute a task for a ticket and return a normalized result."""
