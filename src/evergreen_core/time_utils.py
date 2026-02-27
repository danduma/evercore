"""Timezone-safe datetime helpers."""

from __future__ import annotations

from datetime import datetime

import pytz


def now_utc() -> datetime:
    return datetime.now(pytz.UTC)


def coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return pytz.UTC.localize(value)
    return value.astimezone(pytz.UTC)
