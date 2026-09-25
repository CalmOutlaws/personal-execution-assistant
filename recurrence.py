"""Deterministic recurrence helpers for EXECUTE recurring tasks (V1).

Pure functions only: no Flask, no SQLite, no network calls. The caller
decides what, if anything, to persist.

AI disclosure (CS50 final project requirement): this module was created with
AI assistance and reviewed and tested by the author.
"""

import calendar
from datetime import datetime, timedelta

RECURRENCES = ("daily", "weekly", "monthly")

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def normalize_recurrence(value):
    """Return a valid recurrence or None; invalid values become None."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("", "none", "no", "never", "does not repeat", "does-not-repeat"):
        return None
    if text in RECURRENCES:
        return text
    return None


def is_valid_recurrence(value):
    """Return True only for the allowlisted recurrence values."""
    return isinstance(value, str) and value.strip().lower() in RECURRENCES


def _coerce_datetime(value, now=None):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.strptime(value.strip(), TIMESTAMP_FORMAT)
        except ValueError:
            pass
    if isinstance(now, datetime):
        return now
    return datetime.now()


def _add_months(source, months=1):
    month = source.month - 1 + months
    year = source.year + month // 12
    month = month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return source.replace(year=year, month=month, day=min(source.day, last_day))


def next_due_at(recurrence, due_at=None, now=None):
    """Return the next due_at timestamp string for a recurrence.

    Returns None when recurrence is invalid/None. Never raises on bad input:
    falls back to now plus the interval.
    """
    normalized = normalize_recurrence(recurrence)
    if normalized is None:
        return None
    base = _coerce_datetime(due_at, now if isinstance(now, datetime) else None)
    if normalized == "daily":
        nxt = base + timedelta(days=1)
    elif normalized == "weekly":
        nxt = base + timedelta(days=7)
    else:
        nxt = _add_months(base, 1)
    return nxt.strftime(TIMESTAMP_FORMAT)
