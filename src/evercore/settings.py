"""Standalone evercore settings."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


def _default_worker_id() -> str:
    hostname = socket.gethostname().strip() or "host"
    return f"evercore-worker-{hostname}-{os.getpid()}"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./evercore.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8010
    workflow_dir: str = "./workflows"
    default_workflow_key: str = "default_ticket"
    worker_poll_interval_seconds: float = 2.0
    worker_id: str = Field(default_factory=_default_worker_id)
    task_lease_seconds: int = 300
    stale_task_timeout_seconds: int = 900
    default_max_attempts: int = 3
    retry_base_seconds: int = 10
    retry_max_seconds: int = 600
    event_wait_poll_interval_seconds: int = 15
    schedule_batch_size: int = 10
    default_lemlem_model: str = "openrouter:gemini-2.5-flash"

    class Config:
        env_file = ".env"
        env_prefix = "EVERCORE_"
        extra = "ignore"

    @property
    def workflow_dir_path(self) -> Path:
        return Path(self.workflow_dir).expanduser().resolve()


settings = Settings()
