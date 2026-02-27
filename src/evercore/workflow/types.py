"""Typed workflow definitions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class StageTransition(BaseModel):
    """Transition rule between workflow stages."""

    target: str = Field(..., min_length=1)
    when: Optional[str] = None


class StageDefinition(BaseModel):
    """One executable stage in a workflow definition."""

    id: str = Field(..., min_length=1)
    executor: str = Field(..., min_length=1)
    tools: List[str] = Field(default_factory=list)
    requires_approval: bool = False
    transitions: List[StageTransition] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """A complete workflow specification."""

    key: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    description: Optional[str] = None
    workspace_type: str = Field(default="none", min_length=1)
    initial_stage: str = Field(..., min_length=1)
    stages: List[StageDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stage_graph(self) -> "WorkflowDefinition":
        stage_ids = {stage.id for stage in self.stages}
        if self.initial_stage not in stage_ids:
            raise ValueError(
                f"initial_stage '{self.initial_stage}' is not present in stages"
            )

        for stage in self.stages:
            for transition in stage.transitions:
                if transition.target not in stage_ids and transition.target != "finished":
                    raise ValueError(
                        f"Stage '{stage.id}' references unknown transition target "
                        f"'{transition.target}'"
                    )
        return self

    def stage_by_id(self, stage_id: str) -> StageDefinition | None:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        return None
