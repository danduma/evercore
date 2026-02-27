"""Validation helpers for workflow definitions."""

from __future__ import annotations

from typing import Any, Dict

from .types import WorkflowDefinition


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition is invalid."""


class WorkflowValidator:
    """Validates and normalizes workflow payloads."""

    def validate(self, payload: Dict[str, Any]) -> WorkflowDefinition:
        try:
            return WorkflowDefinition.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise WorkflowValidationError(str(exc)) from exc
