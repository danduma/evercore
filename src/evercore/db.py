"""Database wiring for standalone evercore."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .settings import settings

_engine = create_engine(settings.database_url, echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(_engine)


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
