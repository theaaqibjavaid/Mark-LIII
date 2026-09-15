"""
Calendar — local calendar management for JARVIS.

Stores events in memory/calendar.json. No external API required; works fully
offline. Gemini routes natural-language requests ("what's on my calendar",
"remind me to call mom at 5pm", "clear my afternoon") to the appropriate action.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


CALENDAR_PATH = _base_dir() / "memory" / "calendar.json"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load() -> dict:
    """Load the calendar store. Returns {'events': [...], 'next_id': int}."""
    if not CALENDAR_PATH.exists():
        return {"events": [], "next_id": 1}
    try:
        data = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        if "events" not in data:
            data["events"] = []
        if "next_id" not in data:
            data["next_id"] = 1
        return data
    except Exception:
        return {"events": [], "next_id": 1}


def _save(data: dict) -> None:
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _fmt_dt(dt_str: str) -> str:
    """Format an ISO datetime for human reading. Returns input on parse failure."""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%A, %B %d, %Y at %I:%M %p")
    except Exception:
        return dt_str


def _event_to_spoken(event: dict) -> str:
    title   = event.get("title", "(untitled)")
    start   = _fmt_dt(event["start"])
    end     = _fmt_dt(event.get("end", event["start"]))
    location = event.get("location", "")
    note    = event.get("note", "")
    lines = [f"'{title}' at {start}"]
    if location:
        lines.append(f" at {location}")
    if note:
        lines.append(f" — {note}")
    return "".join(lines)


# ── Date/time parsing ──────────────────────────────────────────────────────────

_MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_DAY_MAP: dict[str, int] = {
    "mon": 0, "monday": 0, "tue": 1, "tuesday": 1, "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3, "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}


def _parse_time(raw: str, base: datetime) -> Optional[datetime]:
    """Parse a loose time string against `base` as the date anchor."""
    raw = raw.strip().lower()
    now = base.replace(second=0, microsecond=0)

    # Natural-language relative times
    if raw in ("now", "right now", "asap", "as soon as possible"):
        return now
    if raw in ("tonight", "this evening"):
        return now.replace(hour=19, minute=0)
    if raw in ("tomorrow"):
        return (now + timedelta(days=1)).replace(hour=9, minute=0)
    if raw.startswith("tomorrow ") or raw.startswith("tmrw "):
        remainder = raw.replace("tomorrow", "", 1).replace("tmrw", "", 1).strip()
        # Strip leading "at" / "a" after removing "tomorrow" (e.g. "tomorrow at 3pm" → "3pm")
        remainder = re.sub(r"^(at\s*|a\s+)?", "", remainder).strip()
        return _parse_time(remainder, now + timedelta(days=1))
    if raw.startswith("next ") or raw.startswith(" nxt "):
        remainder = raw.replace("next ", "", 1).replace(" nxt ", "", 1).strip()
        day_num = _DAY_MAP.get(remainder[:3])
        if day_num is not None:
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).replace(hour=9, minute=0)

    # HH:MM / H:MM / HHMM
    m = re.match(r"^(\d{1,2}):?(\d{2})?\s*(am|pm)?$", raw)
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm   = (m.group(3) or "").lower()
        if ampm in ("pm", "p") and hour < 12:
            hour += 12
        if ampm in ("am", "a") and hour == 12:
            hour = 0
        return now.replace(hour=hour, minute=minute)

    # O'clock variants
    m = re.match(r"^(\d{1,2})\s*(o'?clock|oclock)$", raw)
    if m:
        hour = int(m.group(1))
        return now.replace(hour=hour, minute=0)

    return None


def _parse_date(raw: str, base: Optional[datetime] = None) -> datetime:
    """Parse a loose date string. Returns a datetime at 00:00 of that day."""
    base = base or datetime.now()
    raw = raw.strip().lower()

    today = base.date()

    if raw in ("today", "tonite", "tonight"):
        return datetime.combine(today, datetime.min.time())
    if raw in ("tomorrow", "tmrw"):
        return datetime.combine(today + timedelta(days=1), datetime.min.time())
    if raw in ("yesterday"):
        return datetime.combine(today - timedelta(days=1), datetime.min.time())

    # Day of week
    day_name = None
    for word, num in _DAY_MAP.items():
        if word in raw and len(word) >= 3:
            day_name = num
            break
    if day_name is not None:
        if "next " in raw or " nxt " in raw:
            days_ahead = (day_name - base.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return datetime.combine(today + timedelta(days=days_ahead), datetime.min.time())
        else:
            days_ahead = (day_name - base.weekday()) % 7
            return datetime.combine(today + timedelta(days=days_ahead), datetime.min.time())

    # YYYY-MM-DD format
    m = re.match(r"^(\d{4})[-](\d{1,2})[-](\d{1,2})$", raw)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # MM/DD/YYYY or DD/MM/YYYY format (slash separator)
    m = re.match(r"^(\d{1,2})[/](\d{1,2})[/](\d{4})$", raw)
    if m:
        first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # If first > 12, it must be DD/MM/YYYY
        if first > 12:
            return datetime(year, second, first)
        # Otherwise assume MM/DD/YYYY (US style)
        return datetime(year, first, second)
    # MM-DD-YYYY format (dash separator)
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(year, month, day)

    # "Jan 15" / "15 January" / "March 3rd"
    month_name = None
    for word, num in _MONTH_MAP.items():
        if word in raw and len(word) >= 3:
            month_name = num
            break
    if month_name:
        day_m = re.search(r"\b(\d{1,2})\b", raw)
        day = int(day_m.group(1)) if day_m else 1
        year = base.year
        return datetime(year, month_name, day)

    return datetime.combine(today, datetime.min.time())


def _parse_datetime(raw: str) -> tuple[datetime, datetime]:
    """Parse a combined date+time string, returning (start, end)."""
    raw = raw.strip()
    # Try splitting on common delimiters
    for sep in (" at ", " @ ", " – ", " - ", " from ", " to "):
        if sep in raw:
            parts = raw.split(sep, 1)
            date_part = parts[0].strip()
            time_part = parts[1].strip()
            dt = _parse_date(date_part)
            tm = _parse_time(time_part, dt)
            if tm:
                end = tm + timedelta(hours=1)
                return tm, end

    # Single time or single date
    dt = _parse_date(raw)
    tm = _parse_time(raw, dt)
    start = tm or dt
    end   = start + timedelta(hours=1)
    return start, end


# ── Public actions ─────────────────────────────────────────────────────────────

def create_event(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Create a calendar event.

    Gemini should extract `title`, `date`, `time`, optionally `duration`,
    `location`, and `note` from the user's natural language request.
    """
    params = parameters or {}
    title  = params.get("title", "").strip()
    date_raw = params.get("date", "").strip()
    time_raw = params.get("time", "").strip()
    duration_hrs = float(params.get("duration_hours", params.get("duration", 1)))
    location = (params.get("location") or "").strip()
    note     = (params.get("note") or params.get("description") or "").strip()

    if not title:
        return "I need a title for the event, sir."
    # Build start datetime from natural language if a single combined field was
    # provided; otherwise combine date + time separately.
    combined = (params.get("when") or "").strip()
    if combined:
        start, end = _parse_datetime(combined)
        # Override end time with custom duration if provided
        end = start + timedelta(hours=duration_hrs)
    elif date_raw:
        dt = _parse_date(date_raw)
        if time_raw:
            tm = _parse_time(time_raw, dt)
            start = tm or dt
        else:
            start = dt
        end = start + timedelta(hours=duration_hrs)
    elif combined:
        # Fallback: try the `when` field even when date_raw is empty
        start, end = _parse_datetime(combined)
    else:
        return "Please provide a date for the event."

    data   = _load()
    event  = {
        "id":       data["next_id"],
        "title":    title,
        "start":    start.isoformat(),
        "end":      end.isoformat(),
        "location": location,
        "note":     note,
        "created":  _now_str(),
    }
    data["events"].append(event)
    data["next_id"] += 1
    _save(data)

    if player:
        player.write_log(f"[Calendar] Created: {title} @ {_fmt_dt(start)}")

    return f"Event created: {_event_to_spoken(event)}"


def list_events(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    List calendar events. Supports `scope` parameter:
    today | tomorrow | this_week | upcoming | all.
    """
    params     = parameters or {}
    date_str   = params.get("date", "").strip()
    # If a specific date is provided, use it as the filter target
    if date_str:
        scope = "date"
    else:
        scope = (params.get("scope") or "today").lower().strip()

    data     = _load()
    events   = data.get("events", [])
    today    = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if scope == "today":
        cutoff = today + timedelta(days=1)
        filtered = [e for e in events if e["start"] >= today.isoformat() and e["start"] < cutoff.isoformat()]
    elif scope == "tomorrow":
        tomorrow = today + timedelta(days=1)
        cutoff   = tomorrow + timedelta(days=1)
        filtered = [e for e in events if e["start"] >= tomorrow.isoformat() and e["start"] < cutoff.isoformat()]
    elif scope == "this_week":
        cutoff = today + timedelta(days=7)
        filtered = [e for e in events if e["start"] >= today.isoformat() and e["start"] < cutoff.isoformat()]
    elif scope == "upcoming":
        cutoff = today + timedelta(days=30)
        filtered = [e for e in events if e["start"] >= today.isoformat() and e["start"] < cutoff.isoformat()]
    elif scope == "all":
        filtered = sorted(events, key=lambda e: e.get("start", ""))
    else:
        # Treat as a specific date string
        try:
            target = datetime.fromisoformat(date_str or today.isoformat())
        except ValueError:
            target = today
        cutoff = target + timedelta(days=1)
        filtered = [e for e in events if e["start"] >= target.isoformat() and e["start"] < cutoff.isoformat()]

    if not filtered:
        label = f"on {date_str}" if date_str else f"for {scope}"
        return f"No events {label}, sir."

    filtered.sort(key=lambda e: e.get("start", ""))
    lines: list[str] = []
    for ev in filtered:
        lines.append(_event_to_spoken(ev))

    return "Upcoming events:\n" + "\n".join(f"  • {l}" for l in lines)


def get_event(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Get details of a specific event by ID or title keyword.
    """
    params     = parameters or {}
    event_id   = params.get("event_id", "").strip()
    keyword    = params.get("keyword", "").strip()

    data     = _load()
    events   = data.get("events", [])

    if event_id:
        try:
            eid = int(event_id)
        except ValueError:
            return f"Could not parse event ID: {event_id}"
        for ev in events:
            if ev.get("id") == eid:
                return _format_event_detail(ev)
        return f"Event #{eid} not found."

    if keyword:
        matches = [
            ev for ev in events
            if keyword.lower() in ev.get("title", "").lower()
            or keyword.lower() in ev.get("note", "").lower()
        ]
        if not matches:
            return f"No events matching '{keyword}'."
        matches.sort(key=lambda e: e.get("start", ""))
        return "\n".join(_format_event_detail(e) for e in matches)

    return "Provide an event_id or keyword to look up an event."


def _format_event_detail(ev: dict) -> str:
    lines = [
        f"Event #{ev['id']}: '{ev.get('title', '(untitled)')}'",
        f"  Start : {_fmt_dt(ev['start'])}",
        f"  End   : {_fmt_dt(ev.get('end', ev['start']))}",
    ]
    if ev.get("location"):
        lines.append(f"  Place : {ev['location']}")
    if ev.get("note"):
        lines.append(f"  Note  : {ev['note']}")
    return "\n".join(lines)


def delete_event(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Delete a calendar event by ID or keyword match.
    """
    params      = parameters or {}
    event_id    = params.get("event_id", "").strip()
    keyword     = params.get("keyword", "").strip()

    data    = _load()
    events  = data.get("events", [])

    to_remove: list[int] = []

    if event_id:
        try:
            eid = int(event_id)
        except ValueError:
            return f"Could not parse event ID: {event_id}"
        to_remove = [eid]
    elif keyword:
        to_remove = [
            ev["id"] for ev in events
            if keyword.lower() in ev.get("title", "").lower()
        ]
    else:
        return "Provide an event_id or keyword to delete an event."

    before = len(events)
    events = [ev for ev in events if ev.get("id") not in to_remove]
    after  = len(events)

    if before == after:
        return f"No events found matching '{event_id or keyword}'."

    data["events"] = events
    _save(data)

    if player:
        player.write_log(f"[Calendar] Deleted {before - after} event(s)")

    return f"Deleted {before - after} event(s)."


def clear_events(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Clear all past events (keeps future ones). Use with caution.
    """
    params    = parameters or {}
    scope     = (params.get("scope") or "past").lower().strip()
    data      = _load()
    events    = data.get("events", [])
    now_str   = datetime.now().isoformat()

    if scope == "past":
        new_events = [e for e in events if e.get("end", e["start"]) >= now_str]
    elif scope == "future":
        new_events = [e for e in events if e.get("start", "") >= now_str]
    elif scope == "all":
        new_events = []
    else:
        return f"Unknown scope: {scope}. Use 'past', 'future', or 'all'."

    removed = len(events) - len(new_events)
    data["events"] = new_events
    _save(data)

    if player:
        player.write_log(f"[Calendar] Cleared {removed} event(s)")

    return f"Cleared {removed} past event(s). {len(new_events)} remaining."


def calendar(parameters: dict, player=None, session_memory=None) -> str:
    """
    Unified entry point. Gemini can route to create/list/get/delete/clear
    via the `action` parameter, or we auto-detect from the request text.
    """
    params  = parameters or {}
    action  = (params.get("action") or "").lower().strip()
    text    = (params.get("text") or "").strip()

    if action == "create" or (not action and text):
        return create_event(params, player, session_memory)
    if action == "list":
        return list_events(params, player, session_memory)
    if action == "get":
        return get_event(params, player, session_memory)
    if action == "delete":
        return delete_event(params, player, session_memory)
    if action == "clear":
        return clear_events(params, player, session_memory)
    return f"Unknown action: '{action}'. Use create, list, get, delete, or clear."


# ── Tool declaration ───────────────────────────────────────────────────────────

TOOL = {
    "name": "calendar",
    "description": (
        "Manage a local calendar. Use for: creating events ("
        "'remind me to call mom at 5pm tomorrow'), listing events "
        "('what's on my calendar today'), getting event details, deleting "
        "events, or clearing past events. Events are stored locally and "
        "survive across sessions. Does not require an internet connection."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create | list | get | delete | clear. Optional — auto-detected from text if omitted.",
            },
            "text": {
                "type": "STRING",
                "description": "Natural-language description of the calendar action (used when action is omitted).",
            },
            "title": {
                "type": "STRING",
                "description": "Event title (create action).",
            },
            "date": {
                "type": "STRING",
                "description": "Event date — any format: '2025-03-15', 'March 15', 'tomorrow', 'next Monday'.",
            },
            "time": {
                "type": "STRING",
                "description": "Event time — any format: '5pm', '17:00', '5 o\'clock', 'tonight'.",
            },
            "when": {
                "type": "STRING",
                "description": "Combined date+time string, e.g. 'tomorrow at 5pm' — alternative to date+time.",
            },
            "duration_hours": {
                "type": "NUMBER",
                "description": "Duration in hours (default: 1).",
            },
            "location": {
                "type": "STRING",
                "description": "Event location.",
            },
            "note": {
                "type": "STRING",
                "description": "Additional note or description for the event.",
            },
            "scope": {
                "type": "STRING",
                "description": "For list: today | tomorrow | this_week | upcoming | all. For clear: past | future | all.",
            },
            "event_id": {
                "type": "STRING",
                "description": "Numeric ID of the event to get or delete.",
            },
            "keyword": {
                "type": "STRING",
                "description": "Keyword to search for when getting or deleting an event.",
            },
        },
        "required": [],
    },
    "handler": calendar,
}
