"""Workflow definition loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class WorkflowTransition(BaseModel):
    target: str
    when: Optional[str] = None


class WorkflowStage(BaseModel):
    id: str
    executor: str
    transitions: list[WorkflowTransition] = Field(default_factory=list)


class WorkflowDefinition(BaseModel):
    key: str
    version: str = "1.0.0"
    description: Optional[str] = None
    initial_stage: str
    workspace_type: str = "none"
    stages: list[WorkflowStage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        stage_ids = {stage.id for stage in self.stages}
        if self.initial_stage not in stage_ids:
            raise ValueError(
                f"initial_stage '{self.initial_stage}' is not in workflow stages"
            )
        for stage in self.stages:
            for transition in stage.transitions:
                if transition.target not in stage_ids:
                    raise ValueError(
                        f"stage '{stage.id}' has unknown transition target '{transition.target}'"
                    )
        return self


class WorkflowLoader:
    def __init__(self, workflow_dir: Path):
        self.workflow_dir = workflow_dir

    def load(self, workflow_key: str) -> WorkflowDefinition:
        file_path = self.workflow_dir / f"{workflow_key}.yaml"
        if not file_path.exists():
            raise FileNotFoundError(f"Workflow '{workflow_key}' not found at {file_path}")

        with file_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        if "key" not in payload:
            payload["key"] = workflow_key
        return WorkflowDefinition.model_validate(payload)
