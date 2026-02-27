"""Standalone evergreen-core settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv("EVERGREEN_CORE_DATABASE_URL", "sqlite:///./evergreen_core.db")
    api_host: str = os.getenv("EVERGREEN_CORE_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("EVERGREEN_CORE_API_PORT", "8010"))
    workflow_dir: str = os.getenv("EVERGREEN_CORE_WORKFLOW_DIR", "./workflows")
    default_workflow_key: str = os.getenv("EVERGREEN_CORE_DEFAULT_WORKFLOW_KEY", "default_ticket")
    worker_poll_interval_seconds: float = float(os.getenv("EVERGREEN_CORE_WORKER_POLL_INTERVAL", "2.0"))
    worker_id: str = os.getenv("EVERGREEN_CORE_WORKER_ID", "evergreen-core-worker-1")
    default_lemlem_model: str = os.getenv("EVERGREEN_CORE_DEFAULT_LEMLEM_MODEL", "openrouter:gemini-2.5-flash")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def workflow_dir_path(self) -> Path:
        return Path(self.workflow_dir).expanduser().resolve()


settings = Settings()
