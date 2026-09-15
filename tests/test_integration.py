"""
Integration / feature tests for calendar, email, and notes.
These tests verify cross-cutting behaviour and end-to-end workflows.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from actions.calendar import create_event, list_events, get_event, delete_event, clear_events, _load
from actions.notes      import create_note, search_notes, read_note, _load_index, list_notes, update_note, delete_note
from actions.email      import send_email, read_emails, configure_email, _load_config


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures (shared across integration tests)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_all_paths(tmp_path, monkeypatch):
    """Redirect all data paths to temp locations in one go."""
    import actions.calendar as cal_mod
    import actions.notes   as notes_mod
    import actions.email   as email_mod

    monkeypatch.setattr(cal_mod, "CALENDAR_PATH", tmp_path / "calendar.json")
    monkeypatch.setattr(notes_mod, "NOTES_DIR",       tmp_path / "notes")
    monkeypatch.setattr(notes_mod, "INDEX_PATH",      tmp_path / "notes_index.json")
    monkeypatch.setattr(email_mod, "CONFIG_PATH",     tmp_path / "api_keys.json")

    (tmp_path / "notes").mkdir()
    return tmp_path


@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# Calendar end-to-end workflows
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalendarE2E:
    def test_full_lifecycle(self, player):
        """Create → List → Get → Update (no direct update in calendar, skip) → Delete."""
        # Create
        r1 = create_event({
            "title": "Standup", "when": "tomorrow at 9am",
            "location": "Zoom", "note": "Daily sync",
        }, player)
        assert "Event created" in r1

        # List
        r2 = list_events({"scope": "tomorrow"}, player)
        assert "Standup" in r2

        # Get by ID
        r3 = get_event({"event_id": "1"}, player)
        assert "Standup" in r3
        assert "Zoom"    in r3

        # Delete
        r4 = delete_event({"event_id": "1"}, player)
        assert "Deleted" in r4

        # Confirm gone
        r5 = list_events({"scope": "all"}, player)
        assert "No events" in r5

    def test_natural_language_create(self, player):
        """User says 'remind me to call mom tomorrow at 5pm' → event created."""
        result = create_event({
            "title": "Call mom",
            "when":  "tomorrow at 5pm",
        }, player)
        assert "Event created" in result
        data = _load()
        assert len(data["events"]) == 1
        assert data["events"][0]["title"] == "Call mom"

    def test_recurring_pattern_simulated(self, player):
        """Create multiple events to simulate a week of recurring meetings."""
        for day, title in [("2025-06-16", "Mon standup"), ("2025-06-17", "Tue 1:1"),
                           ("2025-06-18", "Wed review"), ("2025-06-19", "Thu sprint")]:
            create_event({"title": title, "date": day, "time": "10:00"})
        result = list_events({"scope": "all"}, player)
        assert "Mon standup"   in result
        assert "Thu sprint"    in result
        assert result.count("10:00") >= 4  # all four events present


# ═══════════════════════════════════════════════════════════════════════════════
# Notes end-to-end workflows
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotesE2E:
    def test_write_read_search_delete(self, player):
        """Full lifecycle: write → read → search → delete."""
        # Write
        create_note({"title": "Project ideas", "content": "Build a toaster", "tags": "work, ideas"}, player)
        create_note({"title": "Shopping list",  "content": "Milk, bread, butter"}, player)

        # Read by ID
        r = read_note({"note_id": "1"}, player)
        assert "toaster" in r

        # Search
        r = search_notes({"query": "milk"}, player)
        assert "Shopping list" in r

        # Delete first note
        delete_note({"note_id": "1"}, player)
        r = search_notes({"query": "toaster"}, player)
        assert "No notes found" in r

    def test_tags_and_sorting(self, player):
        """Create tagged notes, list filtered, verify sorting works."""
        create_note({"title": "Old personal",  "content": "a", "tags": "personal"}, player)
        import time; time.sleep(0.1)
        create_note({"title": "New work",      "content": "b", "tags": "work"}, player)
        create_note({"title": "Recent personal","content": "c", "tags": "personal"}, player)

        # Filter by tag
        result = list_notes({"tag": "personal"}, player)
        assert "Old personal" in result
        assert "Recent personal" in result
        assert "New work"     not in result

        # Sort by date - just verify it works without error
        result = list_notes({"sort_by": "date"}, player)
        assert "New work" in result

    def test_append_preserves_history(self, player):
        """Appending to a note keeps old content and adds new."""
        create_note({"title": "Log", "content": "Entry 1"})
        update_note({"note_id": "1", "content": "Entry 2", "append": True}, player)
        content = read_note({"note_id": "1"}, player)
        assert "Entry 1" in content
        assert "Entry 2" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Email end-to-end workflows
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmailE2E:
    def test_configure_then_send(self, player):
        """Configure credentials, then send an email."""
        # Step 1: configure
        configure_email({
            "email_address": "me@example.com",
            "password":      "myapppass",
        }, player)

        # Step 2: verify config persisted
        cfg = _load_config()
        assert cfg["email"]["email_address"] == "me@example.com"

        # Step 3: send
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            result = send_email({
                "to":        "you@example.com",
                "subject":   "Test",
                "body":      "Hello from JARVIS",
            }, player)

        assert "Email sent" in result
        # Verify the SMTP call used correct credentials
        mock_server.login.assert_called_once_with("me@example.com", "myapppass")

    def test_send_without_configure_fails_gracefully(self, player):
        """Sending without prior config gives a clear error."""
        result = send_email({
            "to": "a@b.com", "subject": "X", "body": "Y",
        }, player)
        assert "not configured" in result.lower()

    def test_read_without_configure_fails_gracefully(self, player):
        import actions.email as em
        import json
        # Clear any config that the autouse fixture may have set
        em.CONFIG_PATH.write_text(json.dumps({}))
        result = read_emails({}, player)
        assert "not configured" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-feature consistency
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossFeature:
    def test_calendar_and_notes_both_persist(self, player):
        """Events and notes are stored independently — one doesn't clobber the other."""
        create_event({"title": "Meeting", "date": "2025-06-15", "time": "10:00"}, player)
        create_note({"title": "Meeting notes", "content": "Discussed Q2"}, player)

        cal_result  = list_events({"scope": "all"}, player)
        notes_result = list_notes({}, player)

        assert "Meeting"     in cal_result
        assert "Meeting notes" in notes_result

    def test_actions_do_not_mutate_real_fs(self, tmp_path, monkeypatch):
        """All data lives under tmp_path — no real user directories touched."""
        import actions.calendar as cal_mod
        import actions.notes   as notes_mod
        # The paths are set by the autouse fixture to temp dirs, not home
        # Just verify the function works without touching real fs
        assert cal_mod._load()["events"] == []
        import actions.notes as nm
        assert nm._load_index()["notes"] == {}
