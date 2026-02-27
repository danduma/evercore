import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = (ROOT / "workflows").resolve()
DB_PATH = Path(tempfile.gettempdir()) / "evercore_library_tests.db"

os.environ["EVERCORE_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["EVERCORE_WORKFLOW_DIR"] = str(WORKFLOW_DIR)
os.environ.setdefault("EVERCORE_DEFAULT_WORKFLOW_KEY", "default_ticket")
os.environ.setdefault("EVERCORE_WORKER_ID", "evercore-test-worker")


def reset_database() -> None:
    from sqlmodel import SQLModel

    from evercore.db import _engine

    SQLModel.metadata.drop_all(_engine)
    SQLModel.metadata.create_all(_engine)

