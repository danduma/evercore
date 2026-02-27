"""Standalone evercore engine."""

from .workflow import StageDefinition, WorkflowDefinition, WorkflowLoader

__all__ = [
    "__version__",
    "WorkflowDefinition",
    "StageDefinition",
    "WorkflowLoader",
]

__version__ = "0.1.0"
