"""
Unit tests for calendar.py — date parsing, storage, CRUD operations.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


@pytest.fixture
def calendar_module(tmp_path, monkeypatch):
    """Return a fresh calendar module with CALENDAR_PATH pointing to tmp_path."""
    import actions.calendar as cal_mod
    fake_path = tmp_path / "calendar.json"
    fake_path.write_text(json.dumps({"events": [], "next_id": 1}))
    monkeypatch.setattr(cal_mod, "CALENDAR_PATH", fake_path)
    return cal_mod


# ═══════════════════════════════════════════════════════════════════════════════
# Date / time parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDate:
    def test_iso_format(self):
        import actions.calendar as cal
        result = cal._parse_date("2025-06-15")
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_slash_format_mmddyyyy(self):
        """MM/DD/YYYY format (US-style)."""
        import actions.calendar as cal
        result = cal._parse_date("06/15/2025")
        assert result.month == 6
        assert result.day == 15

    def test_slash_format_ddmmyyyy(self):
        """DD/MM/YYYY format (EU-style) — first number > 12 means it's the day."""
        import actions.calendar as cal
        result = cal._parse_date("15/06/2025")
        assert result.month == 6
        assert result.day == 15

    def test_dashed_format_mmdyyy(self):
        """MM-DD-YYYY format."""
        import actions.calendar as cal
        result = cal._parse_date("06-15-2025")
        assert result.month == 6
        assert result.day == 15

    def test_month_name(self):
        import actions.calendar as cal
        result = cal._parse_date("March 15")
        assert result.month == 3

    def test_abbreviated_month(self):
        import actions.calendar as cal
        result = cal._parse_date("Jun 15")
        assert result.month == 6

    def test_day_of_week(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)  # a Sunday
        result = cal._parse_date("monday", base)
        # Next Monday is June 16
        assert result.day == 16

    def test_tomorrow(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_date("tomorrow", base)
        expected = base + timedelta(days=1)
        assert result.date() == expected.date()

    def test_today(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15, 14, 30)
        result = cal._parse_date("today", base)
        assert result == base.replace(hour=0, minute=0, second=0, microsecond=0)

    def test_yesterday(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_date("yesterday", base)
        expected = base - timedelta(days=1)
        assert result.date() == expected.date()

    def test_next_weekday(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)  # Sunday
        result = cal._parse_date("next friday", base)
        # Next Friday is June 20
        assert result.day == 20
        assert result.month == 6

    def test_fallback_to_today(self):
        """Unrecognisable input falls back to today."""
        import actions.calendar as cal
        base = datetime(2025, 6, 15, 10, 0)
        result = cal._parse_date("foobar", base)
        assert result.date() == base.date()


class TestParseTime:
    def test_24h(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15, 10, 0)
        result = cal._parse_time("14:30", base)
        assert result.hour == 14
        assert result.minute == 30

    def test_12h_am(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("9am", base)
        assert result.hour == 9
        assert result.minute == 0

    def test_12h_pm(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("2pm", base)
        assert result.hour == 14

    def test_midnight_boundary(self):
        """12am should become 0, not 12."""
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("12am", base)
        assert result.hour == 0

    def test_noon(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("12pm", base)
        assert result.hour == 12

    def test_oclock(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("5 o'clock", base)
        assert result.hour == 5
        assert result.minute == 0

    def test_now(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15, 14, 33)
        result = cal._parse_time("now", base)
        assert result.hour == 14
        assert result.minute == 33

    def test_tonight(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("tonight", base)
        assert result.hour == 19
        assert result.minute == 0

    def test_tomorrow_with_time(self):
        import actions.calendar as cal
        base = datetime(2025, 6, 15)
        result = cal._parse_time("tomorrow at 3pm", base)
        assert result.day == 16
        assert result.hour == 15

    def test_unknown_returns_none(self):
        import actions.calendar as cal
        result = cal._parse_time("xyz123", datetime.now())
        assert result is None


class TestParseDatetime:
    def test_combined(self):
        import actions.calendar as cal
        start, end = cal._parse_datetime("tomorrow at 5pm")
        assert start.hour == 17
        assert end == start + timedelta(hours=1)

    def test_date_only(self):
        import actions.calendar as cal
        start, end = cal._parse_datetime("June 15")
        assert start.month == 6
        assert start.day == 15
        assert end == start + timedelta(hours=1)


# ═══════════════════════════════════════════════════════════════════════════════
# Storage helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestStorage:
    def test_load_empty_file(self, calendar_module):
        import actions.calendar as cal
        data = cal._load()
        assert data["events"] == []
        assert data["next_id"] == 1

    def test_load_corrupt_file(self, calendar_module, tmp_path, monkeypatch):
        import actions.calendar as cal
        fake_path = tmp_path / "corrupt.json"
        fake_path.write_text("NOT JSON!!!")
        monkeypatch.setattr(cal, "CALENDAR_PATH", fake_path)
        data = cal._load()
        assert data["events"] == []

    def test_save_and_load(self, calendar_module):
        import actions.calendar as cal
        cal._save({"events": [{"id": 1}], "next_id": 2})
        data = cal._load()
        assert data["next_id"] == 2
        assert len(data["events"]) == 1

    def test_fmt_dt(self):
        import actions.calendar as cal
        result = cal._fmt_dt("2025-06-15T14:30:00")
        assert "June" in result
        assert "2025" in result

    def test_fmt_dt_invalid(self):
        import actions.calendar as cal
        result = cal._fmt_dt("not-a-date")
        assert result == "not-a-date"


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateEvent:
    def test_minimal_create(self, calendar_module, player):
        import actions.calendar as cal
        result = cal.create_event({
            "title": "Lunch",
            "date": "2025-06-15",
            "time": "12:00",
        }, player)
        assert "Event created" in result
        data = cal._load()
        assert len(data["events"]) == 1
        ev = data["events"][0]
        assert ev["title"] == "Lunch"
        assert ev["start"] == "2025-06-15T12:00:00"

    def test_create_with_location_and_note(self, calendar_module, player):
        import actions.calendar as cal
        result = cal.create_event({
            "title": "Meeting",
            "when": "tomorrow at 3pm",
            "location": "Conference Room B",
            "note": "Bring the projector",
        }, player)
        assert "Conference Room B" in result
        data = cal._load()
        ev = data["events"][0]
        assert ev["location"] == "Conference Room B"
        assert ev["note"] == "Bring the projector"

    def test_create_missing_title(self, calendar_module):
        import actions.calendar as cal
        result = cal.create_event({"date": "today", "time": "5pm"})
        assert "title" in result.lower()

    def test_create_missing_date(self, calendar_module):
        import actions.calendar as cal
        result = cal.create_event({"title": "Lunch"})
        assert "date" in result.lower()

    def test_creates_sequential_ids(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "A", "date": "2025-01-01", "time": "10:00"})
        cal.create_event({"title": "B", "date": "2025-01-01", "time": "11:00"})
        data = cal._load()
        assert data["events"][0]["id"] == 1
        assert data["events"][1]["id"] == 2

    def test_default_duration_is_one_hour(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Short", "date": "2025-07-01", "time": "09:00"})
        data = cal._load()
        ev = data["events"][0]
        start = datetime.fromisoformat(ev["start"])
        end = datetime.fromisoformat(ev["end"])
        assert (end - start) == timedelta(hours=1)

    def test_custom_duration(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({
            "title": "Long", "date": "2025-07-01", "time": "09:00",
            "duration_hours": 2.5
        })
        data = cal._load()
        ev = data["events"][0]
        start = datetime.fromisoformat(ev["start"])
        end = datetime.fromisoformat(ev["end"])
        assert (end - start) == timedelta(hours=2, minutes=30)

    def test_writes_to_player(self, calendar_module, player):
        import actions.calendar as cal
        cal.create_event({"title": "Test", "date": "2025-01-01", "time": "10:00"}, player)
        player.write_log.assert_called_once()


class TestListEvents:
    def test_empty_list(self, calendar_module):
        import actions.calendar as cal
        result = cal.list_events({"scope": "today"})
        assert "No events" in result

    def test_list_today(self, calendar_module):
        import actions.calendar as cal
        today = datetime.now().strftime("%Y-%m-%d")
        cal.create_event({"title": "Today thing", "date": today, "time": "10:00"})
        result = cal.list_events({"scope": "today"})
        assert "Today thing" in result

    def test_list_scope_all(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Future event", "date": "2099-01-01", "time": "12:00"})
        result = cal.list_events({"scope": "all"})
        assert "Future event" in result

    def test_list_by_specific_date(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Report", "date": "2025-08-01", "time": "14:00"})
        result = cal.list_events({"date": "2025-08-01"})
        assert "Report" in result


class TestGetEvent:
    def test_get_by_id(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Interview", "date": "2025-09-01", "time": "10:00"})
        result = cal.get_event({"event_id": "1"})
        assert "Interview" in result

    def test_get_nonexistent_id(self, calendar_module):
        import actions.calendar as cal
        result = cal.get_event({"event_id": "999"})
        assert "not found" in result.lower()

    def test_get_by_keyword(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Dentist appointment", "date": "2025-09-01", "time": "10:00"})
        result = cal.get_event({"keyword": "dentist"})
        assert "Dentist appointment" in result

    def test_get_no_params(self, calendar_module):
        import actions.calendar as cal
        result = cal.get_event({})
        assert "Provide" in result


class TestDeleteEvent:
    def test_delete_by_id(self, calendar_module, player):
        import actions.calendar as cal
        cal.create_event({"title": "To delete", "date": "2025-09-01", "time": "10:00"})
        result = cal.delete_event({"event_id": "1"}, player)
        assert "Deleted" in result
        assert len(cal._load()["events"]) == 0
        player.write_log.assert_called_once()

    def test_delete_by_keyword(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "Meeting A", "date": "2025-09-01", "time": "10:00"})
        cal.create_event({"title": "Meeting B", "date": "2025-09-02", "time": "11:00"})
        result = cal.delete_event({"keyword": "Meeting"})
        assert "2" in result

    def test_delete_nonexistent(self, calendar_module):
        import actions.calendar as cal
        result = cal.delete_event({"event_id": "999"})
        assert "not found" in result.lower() or "found" in result.lower()


class TestClearEvents:
    def test_clear_past(self, calendar_module):
        import actions.calendar as cal
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        cal.create_event({"title": "Past", "date": yesterday, "time": "10:00"})
        cal.create_event({"title": "Future", "date": tomorrow, "time": "10:00"})
        result = cal.clear_events({"scope": "past"})
        assert "1 past" in result
        assert len(cal._load()["events"]) == 1

    def test_clear_all(self, calendar_module):
        import actions.calendar as cal
        cal.create_event({"title": "A", "date": "today", "time": "10:00"})
        result = cal.clear_events({"scope": "all"})
        assert len(cal._load()["events"]) == 0

    def test_clear_unknown_scope(self, calendar_module):
        import actions.calendar as cal
        result = cal.clear_events({"scope": "galaxy"})
        assert "Unknown scope" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Integration / unified entry point
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalendarUnified:
    def test_auto_detect_create_from_text(self, calendar_module):
        import actions.calendar as cal
        # When text is provided but no explicit action, it routes to create
        result = cal.calendar({"text": "remind me to call mom tomorrow at 5pm",
                               "title": "Call mom", "when": "tomorrow at 5pm"})
        assert "Event created" in result

    def test_unknown_action(self, calendar_module):
        import actions.calendar as cal
        result = cal.calendar({"action": "teleport"})
        assert "Unknown action" in result
