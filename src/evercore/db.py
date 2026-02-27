"""Database wiring for standalone evercore."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .settings import settings

_engine = create_engine(settings.database_url, echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(_engine)
    _run_runtime_migrations()


def _column_exists(conn, table_name: str, column_name: str, url: str) -> bool:
    if "postgres" in url:
        row = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = :table_name
                  AND column_name = :column_name
                LIMIT 1
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).fetchone()
        return row is not None
    rows = conn.execute(text(f'PRAGMA table_info("{table_name}")')).fetchall()
    return any(row[1] == column_name for row in rows)


def _index_exists(conn, table_name: str, index_name: str, url: str) -> bool:
    if "postgres" in url:
        row = conn.execute(
            text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = :table_name
                  AND indexname = :index_name
                LIMIT 1
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).fetchone()
        return row is not None
    rows = conn.execute(text(f'PRAGMA index_list("{table_name}")')).fetchall()
    return any(row[1] == index_name for row in rows)


def _run_runtime_migrations() -> None:
    url = str(_engine.url)
    with _engine.begin() as conn:
        task_columns: list[tuple[str, str]] = [
            ("cancel_requested", "BOOLEAN DEFAULT FALSE"),
            ("cancel_requested_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("max_attempts", "INTEGER DEFAULT 3"),
            ("retry_base_seconds", "INTEGER"),
            ("retry_max_seconds", "INTEGER"),
            ("timeout_seconds", "INTEGER"),
            ("next_run_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("claimed_by", "VARCHAR(255)" if "postgres" in url else "TEXT"),
            ("claimed_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("lease_expires_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
        ]
        for column_name, column_type in task_columns:
            if not _column_exists(conn, "tasks", column_name, url):
                conn.execute(
                    text(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}")
                )
        index_specs = [
            ("ix_tasks_cancel_requested", "cancel_requested"),
            ("ix_tasks_next_run_at", "next_run_at"),
            ("ix_tasks_claimed_by", "claimed_by"),
            ("ix_tasks_claimed_at", "claimed_at"),
            ("ix_tasks_lease_expires_at", "lease_expires_at"),
        ]
        for index_name, column_name in index_specs:
            if not _index_exists(conn, "tasks", index_name, url):
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON tasks ({column_name})"
                    )
                )

        ticket_columns: list[tuple[str, str]] = [
            ("paused", "BOOLEAN DEFAULT FALSE"),
            ("paused_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("resumed_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("approval_required", "BOOLEAN DEFAULT FALSE"),
            ("approval_status", "VARCHAR(32) DEFAULT 'none'" if "postgres" in url else "TEXT DEFAULT 'none'"),
            ("approval_requested_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("approval_decided_at", "TIMESTAMP WITH TIME ZONE" if "postgres" in url else "TIMESTAMP"),
            ("approval_notes", "TEXT"),
        ]
        for column_name, column_type in ticket_columns:
            if not _column_exists(conn, "tickets", column_name, url):
                conn.execute(
                    text(f"ALTER TABLE tickets ADD COLUMN {column_name} {column_type}")
                )

        ticket_index_specs = [
            ("ix_tickets_paused", "paused"),
            ("ix_tickets_approval_required", "approval_required"),
            ("ix_tickets_approval_status", "approval_status"),
        ]
        for index_name, column_name in ticket_index_specs:
            if not _index_exists(conn, "tickets", index_name, url):
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON tickets ({column_name})"
                    )
                )


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(_engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Session:
    return Session(_engine)
