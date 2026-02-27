"""Standalone evercore settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv("EVERCORE_DATABASE_URL", "sqlite:///./evercore.db")
    api_host: str = os.getenv("EVERCORE_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("EVERCORE_API_PORT", "8010"))
    workflow_dir: str = os.getenv("EVERCORE_WORKFLOW_DIR", "./workflows")
    default_workflow_key: str = os.getenv("EVERCORE_DEFAULT_WORKFLOW_KEY", "default_ticket")
    worker_poll_interval_seconds: float = float(os.getenv("EVERCORE_WORKER_POLL_INTERVAL", "2.0"))
    worker_id: str = os.getenv("EVERCORE_WORKER_ID", "evercore-worker-1")
    default_lemlem_model: str = os.getenv("EVERCORE_DEFAULT_LEMLEM_MODEL", "openrouter:gemini-2.5-flash")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def workflow_dir_path(self) -> Path:
        return Path(self.workflow_dir).expanduser().resolve()


settings = Settings()
