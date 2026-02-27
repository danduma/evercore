"""Workflow file loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from .types import WorkflowDefinition
from .validator import WorkflowValidator


class WorkflowLoader:
    """Loads and validates YAML workflows from a directory."""

    def __init__(self, workflow_dir: str | Path):
        self.workflow_dir = Path(workflow_dir).expanduser().resolve()
        self.validator = WorkflowValidator()

    def load(self, workflow_key: str) -> WorkflowDefinition:
        file_path = self.workflow_dir / f"{workflow_key}.yaml"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Workflow definition not found for '{workflow_key}' at {file_path}"
            )

        with file_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        if "key" not in payload:
            payload["key"] = workflow_key
        return self.validator.validate(payload)
