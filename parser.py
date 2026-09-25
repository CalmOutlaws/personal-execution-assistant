"""Deterministic natural-language interpretation for EXECUTE (V2).

The parser deliberately has no web-framework, request, session, or database
dependencies. Its output is a preview only: application code decides what, if
anything, to persist later.

V2 conventions:
* Bare 12-hour times without AM/PM (for example "at 5") map to PM.
* Vague periods such as "evening" are returned as ``approximate_time`` and
  never converted into a fabricated exact time.
* Relative dates use the optional ``reference`` datetime so callers and tests
  can remain deterministic.

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
    rf"\b(?:(?:by|on|before)\s+)?(?:next\s+)?(?:(?P<relative>this\s+week|today|tomorrow)|"
    rf"(?P<weekday>{WEEKDAY_PATTERN})\b|(?P<month>{MONTH_PATTERN})\s+"
    rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(?P<year>\d{{4}}))?|"
    rf"(?P<num_month>\d{{1,2}})/(?P<num_day>\d{{1,2}})"
    rf"(?:/(?P<num_year>\d{{4}}))?)\b",
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
APPROXIMATE_TIME_PATTERN = re.compile(
    r"\b(?P<period>morning|afternoon|evening|night)\b",
    re.IGNORECASE,
)
LOCATION_START_PATTERN = re.compile(r"\b(?:at|in)\s+(?!\d)", re.IGNORECASE)

ACTION_PATTERN = re.compile(
    r"^(?:buy|call|complete|finish|submit|apply|pay|return|email|send|read|"
    r"review|prepare|write|clean|meet|visit|go|attend|schedule|plan|ask|fix|"
    r"book|order|exercise|study|practice|check|learn|do|make|create|draft|"
    r"respond|follow up)\b",
    re.IGNORECASE,
)
COMMITMENT_ACTION_PATTERN = re.compile(
    r"^(?:submit|finish|apply|pay|return|send|email|hand in|turn in|deliver|"
    r"complete|book|reserve|schedule|donate|renew|reply|respond)\b",
    re.IGNORECASE,
)
EVENT_PHRASE_PATTERN = re.compile(
    r"^(?:a\s+|an\s+|the\s+)?(?:meet|meeting|appointment|class|visit|go\s+to|"
    r"attend|dinner\s+with|call\s+with)\b"
    r"|^i\s+(?:have|have\s+got)\s+(?:a\s+|an\s+)?(?:meeting|appointment|class)\b",
    re.IGNORECASE,
)
OBLIGATION_PATTERN = re.compile(
    r"^(?:please\s+)?(?:i\s+)?(?:have\s+to|have\s+got\s+to|need\s+to|must|should)\b",
    re.IGNORECASE,
)
GOAL_PREFIX_PATTERN = re.compile(
    r"^(?:my\s+)?goal\s*(?:is|:)\s*(?:to\s+)?",
    re.IGNORECASE,
)
GOAL_WANT_PATTERN = re.compile(
    r"^i\s+want\s+to\s+(?=(?:learn|get\s+fit|get\s+(?:a|an)\s+"
    r"(?:internship|job|promotion|degree|certification)|become|improve|master|"
    r"achieve)\b)",
    re.IGNORECASE,
)
REMINDER_PATTERN = re.compile(
    r"^(?:please\s+)?(?:remind\s+me\s+to|remember\s+to|don'?t\s+forget\s+to)\s+",
    re.IGNORECASE,
)
TITLE_WRAPPER_PATTERNS = (
    re.compile(r"^(?:please\s+)?(?:i\s+)?(?:have\s+to|have\s+got\s+to|need\s+to|must|should)\s+",
               re.IGNORECASE),
    re.compile(r"^(?:please\s+)?remind\s+me\s+to\s+", re.IGNORECASE),
    re.compile(r"^(?:please\s+)?remember\s+to\s+", re.IGNORECASE),
    re.compile(r"^(?:please\s+)?don'?t\s+forget\s+to\s+", re.IGNORECASE),
    re.compile(r"^(?:my\s+)?goal\s*(?:is|:)\s*(?:to\s+)?", re.IGNORECASE),
    re.compile(r"^i\s+want\s+to\s+", re.IGNORECASE),
    re.compile(r"^please\s+", re.IGNORECASE),
)
LOCATION_STOP_WORDS = {"the", "a", "an", "morning", "afternoon", "evening", "night"}
APPROXIMATE_PERIODS = ("morning", "afternoon", "evening", "night")


def normalize_text(text):
    """Collapse user whitespace and trim outer punctuation-safe padding."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _coerce_reference(reference):
    """Accept either a datetime or a date as the deterministic "now"."""
    if isinstance(reference, datetime):
        return reference
    if isinstance(reference, date):
        return datetime.combine(reference, datetime.min.time())
    return datetime.now()


def _failed(text, error="I couldn't determine what type of item this is."):
    return {"type": "unknown", "title": text, "confidence": 0.0, "error": error}


def _remove_spans(text, matches):
    """Remove matched spans from text, starting from the right."""
    spans = sorted((match.span() for match in matches if match), reverse=True)
    for start, end in spans:
        text = text[:start] + text[end:]
    return text


def _next_weekday(reference, weekday):
    days_ahead = (weekday - reference.weekday()) % 7
    return reference + timedelta(days=days_ahead)


def parse_date(text, reference=None):
    """Return the first valid date phrase in text.

    The result includes the original match so callers can label deadlines and
    remove the phrase from a title.
    """
    reference = _coerce_reference(reference)
    reference_date = reference.date()
    for match in DATE_PATTERN.finditer(text):
        relative = match.group("relative")
        weekday = match.group("weekday")
        month = match.group("month")
        day = match.group("day")
        year = match.group("year")
        num_month = match.group("num_month")
        num_day = match.group("num_day")
        num_year = match.group("num_year")

        if relative:
            normalized = re.sub(r"\s+", " ", relative).lower()
            if normalized == "today":
                parsed = reference_date
            elif normalized == "tomorrow":
                parsed = reference_date + timedelta(days=1)
            else:  # this week: the upcoming Sunday (existing V1 convention)
                parsed = reference_date + timedelta(days=(6 - reference_date.weekday()) % 7)
        elif weekday:
            parsed = _next_weekday(reference_date, WEEKDAYS[weekday.lower()[:3]]
                                   if len(weekday) <= 3 else WEEKDAYS[weekday.lower()])
        elif month:
            parsed_month = MONTHS[month.lower()[:3]] if len(month) <= 3 else MONTHS[month.lower()]
            parsed_year = int(year) if year else reference_date.year
            try:
                parsed = date(parsed_year, parsed_month, int(day))
            except ValueError:
                continue
            if not year and parsed < reference_date:
                parsed = date(parsed_year + 1, parsed_month, int(day))
        else:
            try:
                parsed_month, parsed_day = int(num_month), int(num_day)
                parsed_year = int(num_year) if num_year else reference_date.year
                parsed = date(parsed_year, parsed_month, parsed_day)
            except ValueError:
                continue
            if not num_year and parsed < reference_date:
                parsed = date(parsed_year + 1, parsed_month, parsed_day)

        return {"date": parsed, "match": match,
                "label": match.group(0).strip()}
    return None


def parse_time(text):
    """Return an exact time match, preferring explicit AM/PM forms."""
    match = TIME_PATTERN.search(text)
    if match:
        hour = int(match.group("hour"))
        meridiem = match.group("meridiem").lower().replace(".", "")
        if meridiem.startswith("p") and hour < 12:
            hour += 12
        elif meridiem.startswith("a") and hour == 12:
            hour = 0
        return {"match": match,
                "hour": hour,
                "minute": int(match.group("minute") or 0),
                "meridiem": meridiem}
    match = BARE_TIME_PATTERN.search(text)
    if match:
        hour = int(match.group("hour"))
        # V1 convention: bare 12-hour times are interpreted as PM.
        if hour < 12:
            hour += 12
        return {"match": match, "hour": hour, "minute": int(match.group("minute") or 0),
                "meridiem": None}
    return None


def parse_approximate_time(text):
    match = APPROXIMATE_TIME_PATTERN.search(text)
    if not match:
        return None
    return {"match": match, "period": match.group("period").lower()}


def parse_location(text, date_info=None, time_info=None, approximate_info=None):
    """Extract a location phrase without consuming schedule language."""
    stop_spans = []
    for info in (date_info, time_info):
        if info:
            stop_spans.append(info["match"].span())
    if approximate_info:
        approximate_start = approximate_info["match"].start()
        # Include the introducing "in the"/"at" in the stop span so a
        # location before a vague period does not swallow that phrase.
        introduction = re.search(r"\b(?:at|in)\s+(?:the\s+)?$",
                                 text[:approximate_start], flags=re.IGNORECASE)
        if introduction:
            stop_spans.append((introduction.start(), approximate_start))
        else:
            stop_spans.append(approximate_info["match"].span())

    for match in LOCATION_START_PATTERN.finditer(text):
        prefix_start = match.start()
        start = match.end()
        # Skip candidates that are themselves part of a schedule phrase, such
        # as "at 6 PM" or "in the evening".
        if any(span_start < start and span_end > prefix_start
               for span_start, span_end in stop_spans):
            continue
        later_starts = [span_start for span_start, _ in stop_spans
                        if span_start > start]
        end = min(later_starts) if later_starts else len(text)
        if end <= start:
            continue
        raw = text[start:end].strip(" ,.;:!?")
        if not raw or raw.lower() in LOCATION_STOP_WORDS:
            continue
        # Match V1's title cleanup for locations: "at the library" stores
        # "library" while preserving meaningful names such as "Church Street".
        value = re.sub(r"^(?:the|a|an)\s+", "", raw, flags=re.IGNORECASE).strip()
        if not value:
            continue
        pattern = re.compile(re.escape(match.group(0)) + re.escape(raw))
        span_match = pattern.match(text, prefix_start)
        return {"match": span_match, "value": value}
    return None


def clean_title(text, matches=None):
    """Remove schedule/location phrases and obligation wrappers from a title."""
    matches = matches or []
    cleaned = _remove_spans(text, matches)
    previous = None
    while cleaned != previous:
        previous = cleaned
        for pattern in TITLE_WRAPPER_PATTERNS:
            cleaned = pattern.sub("", cleaned, count=1)
    cleaned = re.sub(r"\b(?:my|our)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    # A vague period can be introduced by "in the"/"at"; after the period is
    # removed, do not leave that dangling prepositional fragment in the title.
    cleaned = re.sub(r"\b(?:at|in)\s+(?:the\s+)?$", "", cleaned,
                     flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t,;:.-!?")
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _clean_title(text):
    """Backward-compatible one-argument title cleaner from V1 callers."""
    return clean_title(text)


def classify_intent(text, cleaned, date_info, time_info, approximate_info,
                    reminder=False):
    """Choose a deterministic intent from lexical signals.

    The order is deliberate: clear scheduled event language wins over generic
    obligation language, reminders stay tasks, and commitments require either
    an obligation or an explicit deadline construction.
    """
    if not cleaned:
        return "unknown"

    # Reminder wording is an explicit task request even when the wrapped verb
    # could otherwise look like a scheduled event.
    if reminder:
        return "task"

    event_signal = bool(EVENT_PHRASE_PATTERN.search(cleaned))
    has_schedule = bool(date_info or time_info or approximate_info)

    if event_signal and has_schedule:
        return "event"

    obligation = bool(OBLIGATION_PATTERN.search(text))
    if obligation:
        return "commitment"

    deadline_label = date_info["label"] if date_info else ""
    has_deadline = bool(
        deadline_label
        and (re.match(r"^(?:by|on|before)\s+", deadline_label, re.IGNORECASE)
             or deadline_label.lower() == "this week")
    )
    if COMMITMENT_ACTION_PATTERN.match(cleaned) and has_deadline:
        return "commitment"

    if ACTION_PATTERN.match(cleaned):
        return "task"

    return "unknown"


def _timestamp(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute).strftime("%Y-%m-%d %H:%M:%S")


def _schedule_fields(result, date_info, time_info, approximate_info, reference,
                     field_name):
    """Attach exact or approximate schedule fields to a parsed result."""
    if date_info:
        day = date_info["date"]
    elif time_info or approximate_info:
        day = reference.date()
    else:
        return result

    if time_info:
        result[field_name] = _timestamp(day.year, day.month, day.day,
                                        time_info["hour"], time_info["minute"])
    elif approximate_info:
        # Never invent an exact time for "evening", "morning", etc. Keep the
        # date and expose the period so the UI can render it truthfully.
        result[field_name] = None
        result["date"] = _timestamp(day.year, day.month, day.day)
        result["approximate_time"] = approximate_info["period"]
        result["time_text"] = approximate_info["period"]
    else:
        result[field_name] = _timestamp(day.year, day.month, day.day)
    return result


def parse_input(text, reference=None):
    """Interpret plain text without accessing a web framework, session, or database.

    ``reference`` is an optional naive datetime used as "now" for relative
    expressions. It makes callers and tests deterministic; production calls
    omit it and use the current local time. Bare times use the existing V1
    convention (5 means 17:00) when no meridiem is supplied.
    """
    original = "" if text is None else str(text).strip()
    if not original:
        return _failed("", "Please enter what you want to add.")

    reference = _coerce_reference(reference)
    normalized = normalize_text(original)

    date_info = parse_date(normalized, reference)
    time_info = parse_time(normalized)
    approximate_info = parse_approximate_time(normalized)
    location_info = parse_location(normalized, date_info, time_info,
                                   approximate_info)

    schedule_matches = [
        info["match"] for info in (date_info, time_info, approximate_info)
        if info
    ]
    if location_info:
        schedule_matches.append(location_info["match"])
    cleaned = clean_title(normalized, schedule_matches)

    reminder = bool(REMINDER_PATTERN.search(normalized))
    goal_match = GOAL_PREFIX_PATTERN.search(normalized)
    if goal_match is None:
        goal_match = GOAL_WANT_PATTERN.search(normalized)
    if goal_match:
        # Strip only the goal prefix while preserving the remaining phrase.
        goal_title = clean_title(normalized[goal_match.end():], [
            match for match in schedule_matches
            if match.start() >= goal_match.end()
        ])
        if goal_title:
            return {"type": "goal", "title": goal_title, "confidence": 0.9}

    intent = classify_intent(normalized, cleaned, date_info, time_info,
                             approximate_info, reminder)
    if intent == "unknown":
        return _failed(original)

    if intent == "event":
        # Events need at least a date, exact time, or vague period; a bare
        # event phrase is not a reliable interpretation.
        if not (date_info or time_info or approximate_info):
            return _failed(original)
        result = {
            "type": "event",
            "title": cleaned,
            "confidence": 0.95 if time_info else
            (0.9 if approximate_info else 0.85),
        }
        if location_info:
            result["location"] = location_info["value"]
        return _schedule_fields(result, date_info, time_info, approximate_info,
                                reference, "starts_at")

    if intent == "commitment":
        result = {
            "type": "commitment",
            "title": cleaned,
            "confidence": 0.95,
        }
        if approximate_info and not time_info:
            # A vague deadline keeps an explicit None deadline plus the parsed
            # date/period; persistence can normalize the date at midnight.
            day = date_info["date"] if date_info else reference.date()
            result["deadline"] = None
            result["date"] = _timestamp(day.year, day.month, day.day)
            result["approximate_time"] = approximate_info["period"]
            result["time_text"] = approximate_info["period"]
        elif date_info:
            # Commitment deadlines are dates, not clock times.
            result["deadline"] = _timestamp(date_info["date"].year,
                                            date_info["date"].month,
                                            date_info["date"].day)
        return result

    result = {
        "type": "task",
        "title": cleaned,
        "confidence": 0.9 if (date_info or time_info or approximate_info)
        else 0.75,
    }
    return _schedule_fields(result, date_info, time_info, approximate_info,
                            reference, "due_at")
