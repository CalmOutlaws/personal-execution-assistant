"""Deterministic natural-language interpretation for EXECUTE.

The parser deliberately has no Flask or database dependencies. Its output is a
preview only: application code decides what, if anything, to persist later.

AI disclosure (CS50 final project requirement): this parser was implemented
with AI assistance and reviewed and tested by the author.
"""

import calendar
import re
from datetime import date, datetime, timedelta


MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name)
          if name}
MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr)
               if name})
WEEKDAYS = {name.lower(): number for number, name in enumerate(calendar.day_name)
            if name}
WEEKDAYS.update({name.lower(): number for number, name in enumerate(calendar.day_abbr)
                 if name})

MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))
WEEKDAY_PATTERN = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
DATE_PATTERN = re.compile(
    rf"\b(?:by\s+|on\s+|before\s+)?(?:(this\s+week|today|tomorrow)|"
    rf"({WEEKDAY_PATTERN})\b|({MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:\s*,?\s*(\d{{4}}))?)\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(
    r"(?:\bat\s+|\b)(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?"
    r"\s*(?P<meridiem>a\.?m\.?|p\.?m\.?)(?=\s|$|[.,!?])",
    re.IGNORECASE,
)
BARE_TIME_PATTERN = re.compile(
    r"\bat\s+(?P<hour>2[0-3]|[01]?\d)(?::(?P<minute>[0-5]\d))?"
    r"(?=\s|$|[.,!?])",
    re.IGNORECASE,
)
LOCATION_PATTERN = re.compile(
    r"\b(?:at|in)\s+(?!\d)(.+?)(?=\s+(?:by|on|before|today|tomorrow|this\s+week|"
    rf"{WEEKDAY_PATTERN}|{MONTH_PATTERN})\b|$)",
    re.IGNORECASE,
)
ACTION_PATTERN = re.compile(
    r"^(?:buy|call|complete|finish|submit|apply|pay|return|email|send|read|"
    r"review|prepare|write|clean|meet|visit|go|attend|schedule|plan|ask|fix|"
    r"book|order|exercise|study|learn|do|make|create|draft|respond|follow up)\b",
    re.IGNORECASE,
)
COMMITMENT_ACTION_PATTERN = re.compile(
    r"^(?:submit|finish|apply|pay|return|send|email|hand in|turn in|deliver|"
    r"complete|book|reserve|schedule|donate|renew|reply|respond)\b",
    re.IGNORECASE,
)
EVENT_PATTERN = re.compile(r"^(?:meet|meeting|go to|attend|visit)\b", re.IGNORECASE)
GOAL_PREFIX_PATTERN = re.compile(r"^(?:my goal is|goal:?)\s*", re.IGNORECASE)


class _Match:
    """A matched phrase plus the text left after removing it."""

    def __init__(self, value, start, end):
        self.value = value
        self.start = start
        self.end = end


def _failed(text, error="I couldn't determine what type of item this is."):
    return {
        "type": "unknown",
        "title": text,
        "confidence": 0.0,
        "error": error,
    }


def _clean_title(text):
    text = re.sub(r"\s+", " ", text).strip(" \t,;:.!?-")
    text = re.sub(r"^(?:please\s+)?(?:i need to|i have to|i must|remember to)\s+",
                  "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:my|the|a|an)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:my|our)\s+", "", text, flags=re.IGNORECASE)
    if text:
        text = text[0].upper() + text[1:]
    return text



def _next_weekday(reference, weekday):
    days_ahead = (weekday - reference.weekday()) % 7
    return reference + timedelta(days=days_ahead)


def _parse_date(text, reference):
    match = DATE_PATTERN.search(text)
    if not match:
        return None, None

    relative, weekday_name, month_name, day_text, year_text = match.groups()
    start, end = match.span()
    value = re.sub(r"^(?:by|on|before)\s+", "", match.group(0), flags=re.IGNORECASE)

    if relative:
        normalized = re.sub(r"\s+", " ", relative.lower())
        if normalized == "today":
            parsed = reference
        elif normalized == "tomorrow":
            parsed = reference + timedelta(days=1)
        else:
            # Interpret "this week" as Sunday, the last day of the current
            # Monday-Sunday week. This is deterministic and locale-independent.
            parsed = reference + timedelta(days=6 - reference.weekday())
    elif weekday_name:
        parsed = _next_weekday(reference, WEEKDAYS[weekday_name.lower()])
    else:
        try:
            year = int(year_text) if year_text else reference.year
            parsed = date(year, MONTHS[month_name.lower()], int(day_text))
            if not year_text and parsed < reference:
                parsed = parsed.replace(year=year + 1)
        except (ValueError, OverflowError):
            return None, None

    return _Match(parsed, start, end), match.group(0)


def _parse_time(text):
    match = TIME_PATTERN.search(text) or BARE_TIME_PATTERN.search(text)
    if not match:
        return None

    hour_text = match.group("hour")
    minute_text = match.group("minute") or "0"
    meridiem = match.groupdict().get("meridiem") or ""
    hour = int(hour_text)
    if meridiem:
        if meridiem.lower().startswith("p") and hour != 12:
            hour += 12
        elif meridiem.lower().startswith("a") and hour == 12:
            hour = 0
    elif hour < 12:
        # A bare 12-hour time in EXECUTE's concise input language means PM.
        # Explicit AM/PM above still controls its own conversion; 17:00 remains
        # unchanged because it is already a 24-hour value.
        hour += 12

    return _Match((hour, int(minute_text or 0)), match.start(), match.end())


def _remove(text, match):
    if match is None:
        return text
    return (text[:match.start] + " " + text[match.end:]).strip()


def _remove_many(text, matches):
    for match in sorted((item for item in matches if item is not None),
                        key=lambda item: item.start, reverse=True):
        text = (text[:match.start] + " " + text[match.end:]).strip()
    return text


def _timestamp(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute).strftime("%Y-%m-%d %H:%M:%S")



def parse_input(text, reference=None):
    """Interpret plain text without accessing Flask, a session, or SQLite.

    ``reference`` is an optional naive datetime used as "now" for relative
    expressions. It makes callers and tests deterministic; production calls omit
    it and use the current local time. Bare times use 24-hour time (5 means
    5:00 AM) because the text does not say whether they are AM or PM.
    """
    original = "" if text is None else str(text).strip()
    if not original:
        return _failed("", "Please enter what you want to add.")

    now = reference or datetime.now()
    normalized = original.rstrip(".!?")

    location_regex = LOCATION_PATTERN.search(normalized)
    location = _clean_title(location_regex.group(1)) if location_regex else ""
    if location_regex:
        location_match = _Match(location_regex.group(1), location_regex.start(),
                                location_regex.end())
        normalized = _remove(normalized, location_match)
    date_match, date_label = _parse_date(normalized, now.date())
    time_match = _parse_time(normalized)
    normalized = _remove_many(normalized, (date_match, time_match))
    cleaned = _clean_title(normalized)

    # A commitment needs an explicit deadline obligation. This avoids treating
    # an ordinary task such as "Buy a notebook tomorrow" as a promise.
    has_deadline_word = bool(
        date_label and re.match(r"^(?:by|on|before)\s+", date_label, re.IGNORECASE)
    )
    is_commitment = (
        date_match
        and COMMITMENT_ACTION_PATTERN.match(cleaned)
        and (has_deadline_word or date_label.lower() == "this week")
        and not cleaned.lower().startswith("complete ")
    )

    if EVENT_PATTERN.match(cleaned):
        if date_match is None:
            return _failed(original)
        result = {
            "type": "event",
            "title": cleaned,
            "starts_at": _timestamp(date_match.value.year, date_match.value.month,
                                   date_match.value.day,
                                   *(time_match.value if time_match else (0, 0))),
            "confidence": 0.95 if time_match else 0.85,
        }
        if location:
            result["location"] = location
        return result

    if is_commitment and date_match:
        return {
            "type": "commitment",
            "title": cleaned,
            "deadline": _timestamp(date_match.value.year, date_match.value.month,
                                   date_match.value.day),
            "confidence": 0.95,
        }

    goal_match = GOAL_PREFIX_PATTERN.match(cleaned)
    if goal_match:
        goal_title = _clean_title(normalized[goal_match.end():])
        if goal_title:
            return {"type": "goal", "title": goal_title, "confidence": 0.9}

    if not cleaned or not ACTION_PATTERN.match(cleaned):
        return _failed(original)

    result = {
        "type": "task",
        "title": cleaned,
        "confidence": 0.9 if date_match or time_match else 0.75,
    }
    if date_match:
        if time_match:
            result["due_at"] = _timestamp(date_match.value.year,
                                         date_match.value.month, date_match.value.day,
                                         *time_match.value)
        else:
            result["due_at"] = _timestamp(date_match.value.year,
                                         date_match.value.month, date_match.value.day)
    elif time_match:
        result["due_at"] = _timestamp(now.year, now.month, now.day,
                                      *time_match.value)
    return result
