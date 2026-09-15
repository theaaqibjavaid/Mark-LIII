"""
Conftest — shared fixtures for all action tests.
Provides temporary filesystem isolation so tests never touch real data.
"""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock


# ── Project root ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _add_project_to_path():
    """Ensure actions/ can be imported from tests/."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def fake_player():
    """A mock player object that records write_log calls."""
    player = MagicMock()
    player.write_log = MagicMock()
    return player


@pytest.fixture
def empty_calendar(tmp_path):
    """Return a pristine calendar data dict and its path."""
    cal_path = tmp_path / "calendar.json"
    cal_path.write_text(json.dumps({"events": [], "next_id": 1}))
    return cal_path


@pytest.fixture
def empty_notes_index(tmp_path):
    """Return a pristine notes index and its notes directory."""
    notes_dir  = tmp_path / "notes"
    index_path = tmp_path / "notes_index.json"
    notes_dir.mkdir()
    index_path.write_text(json.dumps({"notes": {}, "next_id": 1}))
    return {"notes_dir": notes_dir, "index_path": index_path}


@pytest.fixture
def fake_email_config(tmp_path):
    """Return a minimal email config dict and the path to write it to."""
    cfg = {
        "email_address": "test@example.com",
        "password":      "testpass",
        "smtp_server":   "smtp.example.com",
        "smtp_port":     587,
        "imap_server":   "imap.example.com",
        "imap_port":     993,
    }
    cfg_path = tmp_path / "api_keys.json"
    cfg_path.write_text(json.dumps({"email": cfg}))
    return cfg, cfg_path


@pytest.fixture
def sample_event():
    """Return a sample event dict for testing."""
    return {
        "id":       1,
        "title":    "Team standup",
        "start":    "2025-06-15T09:00:00",
        "end":      "2025-06-15T09:30:00",
        "location": "Zoom",
        "note":     "Daily sync",
        "created":  "2025-06-14T18:00:00",
    }
