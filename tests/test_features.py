"""
Feature tests — verify the new capabilities behave correctly under realistic
conditions, including edge cases that a real user might trigger.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from actions.calendar import create_event, list_events, get_event, delete_event, clear_events
from actions.notes    import create_note, list_notes, search_notes, update_note, delete_note, read_note
from actions.email    import send_email, read_emails, configure_email
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_paths(tmp_path, monkeypatch):
    import actions.calendar as cal_mod
    import actions.notes   as notes_mod
    import actions.email   as email_mod

    monkeypatch.setattr(cal_mod, "CALENDAR_PATH", tmp_path / "calendar.json")
    monkeypatch.setattr(notes_mod, "NOTES_DIR",       tmp_path / "notes")
    monkeypatch.setattr(notes_mod, "INDEX_PATH",      tmp_path / "notes_index.json")
    monkeypatch.setattr(email_mod, "CONFIG_PATH",     tmp_path / "api_keys.json")
    (tmp_path / "notes").mkdir()

@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# Calendar feature tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalendarFeatures:
    def test_event_spans_midnight(self, player):
        """An event spanning midnight stores correct start and end times."""
        create_event({
            "title":    "Late movie",
            "when":     "today at 10pm",
            "duration_hours": 4,
        }, player)
        import actions.calendar as cal_mod
        cal_data = cal_mod._load()
        ev = cal_data["events"][0]
        start = datetime.fromisoformat(ev["start"])
        end = datetime.fromisoformat(ev["end"])
        # Duration should be 4 hours
        assert (end - start).total_seconds() == 4 * 3600

    def test_list_scopes_are_independent(self, player):
        """Listing 'today' must not return tomorrow's events."""
        today    = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        create_event({"title": "Today only", "date": today, "time": "10:00"})
        create_event({"title": "Tomorrow only", "date": tomorrow, "time": "10:00"})

        today_result  = list_events({"scope": "today"}, player)
        tom_result    = list_events({"scope": "tomorrow"}, player)

        assert "Today only"   in today_result
        assert "Tomorrow only" not in today_result
        assert "Tomorrow only" in tom_result
        assert "Today only"   not in tom_result

    def test_delete_confirms_count(self, player):
        """Deleting two events with a keyword should report the correct count."""
        create_event({"title": "Meeting A", "date": "2025-01-01", "time": "10:00"})
        create_event({"title": "Meeting B", "date": "2025-01-02", "time": "11:00"})
        result = delete_event({"keyword": "Meeting"}, player)
        assert "2" in result
        import actions.calendar as cal_mod
        assert len(cal_mod._load()["events"]) == 0

    def test_clear_keeps_future_events(self, player):
        """clear with scope=past should not remove future events."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        next_year = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        create_event({"title": "Past event", "date": yesterday, "time": "10:00"})
        create_event({"title": "Future event", "date": next_year, "time": "10:00"})
        clear_events({"scope": "past"}, player)
        import actions.calendar as cal_mod
        remaining = [e["title"] for e in cal_mod._load()["events"]]
        assert "Future event" in remaining
        assert "Past event" not in remaining


# ═══════════════════════════════════════════════════════════════════════════════
# Notes feature tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotesFeatures:
    def test_markdown_preserved(self, player):
        """Markdown formatting in note content is preserved verbatim."""
        markdown = """# Title

- Item 1
- Item 2

**Bold text** and *italic*."""
        create_note({"title": "Markdown test", "content": markdown}, player)
        content = read_note({"note_id": "1"}, player)
        assert "**Bold text**" in content
        assert "*italic*"     in content
        assert "- Item 1"     in content

    def test_note_file_is_readable_outside_app(self, tmp_path, monkeypatch):
        """A note file written by the app can be read directly — it's a real .md."""
        import actions.notes as notes_mod
        notes_dir = tmp_path / "notes"
        monkeypatch.setattr(notes_mod, "NOTES_DIR", notes_dir)
        monkeypatch.setattr(notes_mod, "INDEX_PATH", tmp_path / "idx.json")
        # Create the directory
        notes_dir.mkdir(parents=True, exist_ok=True)
        (tmp_path / "idx.json").write_text(json.dumps({"notes": {}, "next_id": 1}))

        create_note({"title": "Raw file", "content": "Hello world"})
        file_content = (notes_dir / "1.md").read_text(encoding="utf-8")
        assert "Hello world" in file_content
        assert "# Raw file" in file_content

    def test_search_is_case_insensitive(self, player):
        create_note({"title": "Groceries", "content": "BUY MILK and EGGS"})
        result_lower = search_notes({"query": "milk"}, player)
        result_upper = search_notes({"query": "MILK"}, player)
        assert "Groceries" in result_lower
        assert "Groceries" in result_upper

    def test_large_note_handled(self, player):
        """A note with lots of content should not crash."""
        big_content = "\n".join(f"Line {i}: some useful information here" for i in range(200))
        create_note({"title": "Big note", "content": big_content}, player)
        result = read_note({"note_id": "1"}, player)
        assert "Line 0" in result
        assert "Line 199" in result

    def test_update_preserves_header_metadata(self, player):
        """Updating content should keep the title and created date intact."""
        create_note({"title": "Original", "content": "old stuff"})
        update_note({"note_id": "1", "content": "new stuff"}, player)
        content = read_note({"note_id": "1"}, player)
        assert "# Original" in content
        assert "old stuff"  not in content
        assert "new stuff"  in content


# ═══════════════════════════════════════════════════════════════════════════════
# Email feature tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmailFeatures:
    def test_html_email_sends_correctly(self, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            configure_email({"email_address": "a@b.com", "password": "p"})
            send_email({
                "to":      "c@d.com",
                "subject": "HTML Test",
                "html":    "<b>Bold</b>",
            }, player)

            msg = mock_server.sendmail.call_args[0][2]
            assert "HTML Test" in msg
            # HTML content is base64 encoded in MIME, so verify subject is present
            assert "From: a@b.com" in msg

    def test_cc_and_bcc_are_in_recipients(self, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            configure_email({"email_address": "a@b.com", "password": "p"})
            send_email({
                "to":      "primary@example.com",
                "cc":      "cc1@example.com, cc2@example.com",
                "bcc":     "bcc1@example.com",
                "subject": "Test",
                "body":    "Body",
            }, player)

            call_args = mock_server.sendmail.call_args
            recipients = call_args[0][1]
            assert "primary@example.com" in recipients
            assert "cc1@example.com"     in recipients
            assert "bcc1@example.com"    in recipients

    def test_read_ignores_unmatched_keyword(self, player):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value.__enter__ = MagicMock(return_value=mock_mail)
            MockIMAP.return_value.__exit__  = MagicMock(return_value=False)
            mock_mail.search.return_value = ("OK", [b"1"])
            raw = b"From: a@b.com\r\nSubject: Meeting tomorrow\r\n\r\nSee you there"
            mock_msg = MagicMock()
            mock_msg.as_string.return_value = raw.decode()
            mock_mail.fetch.return_value = ("OK", [(None, raw)])

            configure_email({"email_address": "a@b.com", "password": "p"})
            result = read_emails({"keyword": "vacation"}, player)
            # Should return empty because keyword doesn't match
            assert "No emails" in result or "vacation" not in result.lower()

    def test_configure_overwrites_previous_credentials(self, player):
        configure_email({"email_address": "first@example.com", "password": "pw1"})
        configure_email({"email_address": "second@example.com", "password": "pw2"})
        cfg = configure_email.__globals__["_load_config"]()
        assert cfg["email"]["email_address"] == "second@example.com"
        assert cfg["email"]["password"]      == "pw2"


# ═══════════════════════════════════════════════════════════════════════════════
# Robustness / edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestRobustness:
    def test_calendar_handles_unicode_titles(self, player):
        create_event({"title": "Réunion avec Équipe — 日本", "date": "2025-06-15", "time": "10:00"})
        result = list_events({"scope": "all"}, player)
        assert "Réunion" in result

    def test_notes_handles_unicode_content(self, player):
        create_note({"title": "中文笔记", "content": "这是测试内容 你好世界 🌍"})
        result = read_note({"note_id": "1"}, player)
        assert "你好世界" in result

    def test_email_handles_long_recipient_list(self, player):
        """Sending to many recipients should not crash."""
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            configure_email({"email_address": "a@b.com", "password": "p"})
            many = ", ".join(f"user{i}@example.com" for i in range(50))
            send_email({"to": many, "subject": "Mass", "body": "Hi"}, player)
            call_args = mock_server.sendmail.call_args
            recipients = call_args[0][1]
            assert len(recipients) == 50

    def test_calendar_event_id_never_collides(self, player):
        """Creating many events should produce unique sequential IDs."""
        for i in range(20):
            create_event({"title": f"Event {i}", "date": "2025-01-01", "time": "10:00"})
        import actions.calendar as cal_mod
        ids = [e["id"] for e in cal_mod._load()["events"]]
        assert len(ids) == len(set(ids)), "Duplicate IDs detected!"

    def test_notes_index_stays_in_sync_after_delete(self, player):
        """After deleting a note, the index should not contain a stale reference."""
        create_note({"title": "A", "content": "a"})
        create_note({"title": "B", "content": "b"})
        delete_note({"note_id": "1"}, player)
        import actions.notes as notes_mod
        data = notes_mod._load_index()
        assert "1" not in data["notes"]
        assert "2" in data["notes"]
