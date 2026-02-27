"""Shared task-runtime policy helpers used by evercore and Evergreen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytz


@dataclass(frozen=True)
class TaskRuntimePolicy:
    lease_seconds: int
    stale_task_timeout_seconds: int
    retry_base_seconds: int
    retry_max_seconds: int
    default_max_attempts: int


def utcnow() -> datetime:
    return datetime.now(pytz.UTC)


def normalize_max_attempts(value: int | None, default_max_attempts: int) -> int:
    default = max(int(default_max_attempts or 1), 1)
    if value is None:
        return default
    return max(int(value), 1)


def lease_expires_at(now: datetime, lease_seconds: int) -> datetime:
    return now + timedelta(seconds=max(int(lease_seconds or 1), 1))


def is_retry_ready(now: datetime, next_run_at: datetime | None) -> bool:
    if next_run_at is None:
        return True
    if next_run_at.tzinfo is None:
        next_run_at = pytz.UTC.localize(next_run_at)
    return next_run_at <= now


def compute_retry_delay_seconds(attempt_count: int, retry_base_seconds: int, retry_max_seconds: int) -> int:
    base = max(int(retry_base_seconds or 1), 1)
    maximum = max(int(retry_max_seconds or base), base)
    return min(maximum, base * (2 ** max(0, int(attempt_count) - 1)))


def compute_next_retry_at(
    now: datetime,
    attempt_count: int,
    retry_base_seconds: int,
    retry_max_seconds: int,
) -> datetime:
    delay_seconds = compute_retry_delay_seconds(
        attempt_count=attempt_count,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    )
    return now + timedelta(seconds=delay_seconds)


def should_dead_letter(attempt_count: int, max_attempts: int) -> bool:
    return int(attempt_count) >= max(int(max_attempts), 1)


def is_stale_running_task(
    now: datetime,
    *,
    lease_expires_at_value: datetime | None,
    started_at: datetime | None,
    stale_task_timeout_seconds: int,
) -> bool:
    if lease_expires_at_value is not None:
        if lease_expires_at_value.tzinfo is None:
            lease_expires_at_value = pytz.UTC.localize(lease_expires_at_value)
        return lease_expires_at_value <= now
    if started_at is None:
        return False
    if started_at.tzinfo is None:
        started_at = pytz.UTC.localize(started_at)
    stale_cutoff = now - timedelta(seconds=max(int(stale_task_timeout_seconds or 1), 1))
    return started_at <= stale_cutoff
