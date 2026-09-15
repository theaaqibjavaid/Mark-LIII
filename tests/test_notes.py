"""
Unit tests for notes.py — create, read, list, search, update, delete.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from actions.notes import (
    create_note, read_note, list_notes, search_notes, update_note, delete_note, notes,
    NOTES_DIR, INDEX_PATH, _safe_filename, _note_path, _load_index, _save_index,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_paths(tmp_path, monkeypatch):
    """Redirect NOTES_DIR and INDEX_PATH to temp locations."""
    notes_dir  = tmp_path / "notes"
    index_path = tmp_path / "notes_index.json"
    monkeypatch.setattr("actions.notes.NOTES_DIR",       notes_dir)
    monkeypatch.setattr("actions.notes.INDEX_PATH",      index_path)
    return {"notes_dir": notes_dir, "index_path": index_path}


@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


@pytest.fixture
def sample_note_content():
    return (
        "# My Note\n\n"
        "**Created:** 2025-01-01 10:00\n\n"
        "---\n\n"
        "This is the body of the note.\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# _safe_filename
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeFilename:
    def test_basic_title(self):
        assert _safe_filename("My Note") == "My-Note"

    def test_special_chars_stripped(self):
        result = _safe_filename("Note: Hello! World?")
        assert ":" not in result
        assert "?" not in result
        assert "Hello" in result

    def test_empty_title(self):
        assert _safe_filename("") == "untitled"

    def test_very_long_title_truncated(self):
        long = "A" * 200
        result = _safe_filename(long)
        assert len(result) <= 80


# ═══════════════════════════════════════════════════════════════════════════════
# Storage helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestStorageHelpers:
    def test_load_index_empty(self, _patch_paths):
        data = _load_index()
        assert data["notes"] == {}
        assert data["next_id"] == 1

    def test_load_index_corrupt(self, _patch_paths, tmp_path, monkeypatch):
        idx = _patch_paths["index_path"]
        idx.write_text("{broken")
        monkeypatch.setattr("actions.notes.INDEX_PATH", idx)
        data = _load_index()
        assert data["notes"] == {}

    def test_save_and_load(self, _patch_paths):
        _save_index({"notes": {"1": {"title": "A"}}, "next_id": 2})
        data = _load_index()
        assert data["next_id"] == 2
        assert "1" in data["notes"]


# ═══════════════════════════════════════════════════════════════════════════════
# Create note
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateNote:
    def test_minimal_create(self, _patch_paths, player):
        result = create_note({"title": "Shopping", "content": "Milk, eggs, bread"}, player)
        assert "Note created" in result
        assert "Shopping" in result

        # Verify file exists
        notes_dir = _patch_paths["notes_dir"]
        assert (notes_dir / "1.md").exists()

        # Verify index updated
        data = _load_index()
        assert "1" in data["notes"]
        assert data["notes"]["1"]["title"] == "Shopping"
        player.write_log.assert_called_once()

    def test_create_with_tags(self, _patch_paths, player):
        create_note({"title": "Ideas", "content": "Build a rocket", "tags": "personal, work"})
        data = _load_index()
        assert "personal" in data["notes"]["1"]["tags"]
        assert "work"     in data["notes"]["1"]["tags"]

    def test_auto_title_from_content(self, _patch_paths):
        create_note({"content": "First line is the title\nSecond line is body"})
        data = _load_index()
        assert data["notes"]["1"]["title"] == "First line is the title"

    def test_create_untitled(self, _patch_paths):
        create_note({"content": ""})
        data = _load_index()
        assert data["notes"]["1"]["title"] == "Untitled"

    def test_sequential_ids(self, _patch_paths):
        create_note({"title": "A", "content": "a"})
        create_note({"title": "B", "content": "b"})
        data = _load_index()
        assert data["notes"]["1"]["title"] == "A"
        assert data["notes"]["2"]["title"] == "B"

    def test_content_written_to_file(self, _patch_paths):
        create_note({"title": "Test", "content": "Hello world"})
        content = (_patch_paths["notes_dir"] / "1.md").read_text()
        assert "Hello world" in content
        assert "# Test" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Read note
# ═══════════════════════════════════════════════════════════════════════════════

class TestReadNote:
    def test_read_by_id(self, _patch_paths, player):
        create_note({"title": "Diary", "content": "Dear diary..."})
        result = read_note({"note_id": "1"}, player)
        assert "Dear diary" in result

    def test_read_nonexistent_id(self, _patch_paths):
        result = read_note({"note_id": "999"})
        assert "not found" in result.lower()

    def test_read_by_keyword(self, _patch_paths):
        create_note({"title": "Recipe", "content": "Mix flour and eggs"})
        result = read_note({"keyword": "Recipe"})
        assert "Mix flour" in result

    def test_read_by_path(self, _patch_paths):
        note_path = _patch_paths["notes_dir"] / "1.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Direct\n\nSome content")
        result = read_note({"path": str(note_path)})
        assert "Some content" in result

    def test_read_missing_path(self, _patch_paths):
        result = read_note({"path": "/does/not/exist.md"})
        assert "not found" in result.lower()

    def test_read_no_params(self, _patch_paths):
        result = read_note({})
        assert "Provide" in result


# ═══════════════════════════════════════════════════════════════════════════════
# List notes
# ═══════════════════════════════════════════════════════════════════════════════

class TestListNotes:
    def test_empty_list(self, _patch_paths):
        result = list_notes({})
        assert "No notes" in result

    def test_list_shows_all(self, _patch_paths):
        create_note({"title": "Alpha", "content": "a"})
        create_note({"title": "Beta",  "content": "b"})
        result = list_notes({})
        assert "Alpha" in result
        assert "Beta"  in result

    def test_list_sorted_by_title(self, _patch_paths):
        create_note({"title": "Zebra",  "content": "z"})
        create_note({"title": "Ant",    "content": "a"})
        create_note({"title": "Monkey", "content": "m"})
        result = list_notes({})
        lines = result.splitlines()
        # Find positions of each title
        pos_ant    = next(i for i, l in enumerate(lines) if "Ant"    in l)
        pos_monkey = next(i for i, l in enumerate(lines) if "Monkey" in l)
        pos_zebra  = next(i for i, l in enumerate(lines) if "Zebra"  in l)
        assert pos_ant < pos_monkey < pos_zebra

    def test_list_sorted_by_date(self, _patch_paths):
        # Manually create two notes with different timestamps
        notes_dir = _patch_paths["notes_dir"]
        index_path = _patch_paths["index_path"]
        notes_dir.mkdir(parents=True, exist_ok=True)

        # Write first note with old timestamp
        note1_content = "# Old\n\n**Created:** 2025-01-01 10:00\n\n---\nold content"
        (notes_dir / "1.md").write_text(note1_content, encoding="utf-8")

        # Write second note with new timestamp
        note2_content = "# New\n\n**Created:** 2025-12-31 23:59\n\n---\nnew content"
        (notes_dir / "2.md").write_text(note2_content, encoding="utf-8")

        # Write index
        index_data = {
            "notes": {
                "1": {"id": 1, "title": "Old", "tags": [], "created": "2025-01-01 10:00", "updated": "2025-01-01 10:00", "path": str(notes_dir / "1.md")},
                "2": {"id": 2, "title": "New", "tags": [], "created": "2025-12-31 23:59", "updated": "2025-12-31 23:59", "path": str(notes_dir / "2.md")},
            },
            "next_id": 3
        }
        index_path.write_text(json.dumps(index_data))

        result = list_notes({"sort_by": "date"})
        lines = result.splitlines()
        pos_new = next(i for i, l in enumerate(lines) if "New" in l)
        pos_old = next(i for i, l in enumerate(lines) if "Old" in l)
        assert pos_new < pos_old  # Newest should appear first

    def test_list_filter_by_tag(self, _patch_paths):
        create_note({"title": "Work A",  "content": "a", "tags": "work"})
        create_note({"title": "Personal", "content": "b", "tags": "personal"})
        create_note({"title": "Work B",   "content": "c", "tags": "work"})
        result = list_notes({"tag": "work"})
        assert "Work A" in result
        assert "Work B" in result
        assert "Personal" not in result

    def test_list_tag_no_matches(self, _patch_paths):
        create_note({"title": "A", "content": "a", "tags": "x"})
        result = list_notes({"tag": "y"})
        assert "No notes" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Search notes
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchNotes:
    def test_search_finds_content(self, _patch_paths):
        create_note({"title": "Groceries", "content": "Buy milk and eggs"})
        result = search_notes({"query": "milk"})
        assert "Groceries" in result
        assert "milk" in result.lower()

    def test_search_no_match(self, _patch_paths):
        create_note({"title": "A", "content": "xyz"})
        result = search_notes({"query": "nonexistent123"})
        assert "No notes found" in result

    def test_search_empty_query(self, _patch_paths):
        result = search_notes({"query": ""})
        assert "provide" in result.lower()

    def test_search_limit(self, _patch_paths):
        for i in range(15):
            create_note({"title": f"Note {i}", "content": f"Content {i}"})
        result = search_notes({"query": "Content", "limit": 5})
        assert result.count("📝") <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Update note
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateNote:
    def test_update_content(self, _patch_paths, player):
        create_note({"title": "Draft", "content": "Old content"})
        result = update_note({"note_id": "1", "content": "New content"}, player)
        assert "updated" in result.lower()
        content = (_patch_paths["notes_dir"] / "1.md").read_text()
        assert "New content" in content
        assert "Old content" not in content
        player.write_log.assert_called_once()

    def test_update_title(self, _patch_paths):
        create_note({"title": "Old Title", "content": "body"})
        update_note({"note_id": "1", "title": "New Title"})
        content = (_patch_paths["notes_dir"] / "1.md").read_text()
        assert "# New Title" in content
        data = _load_index()
        assert data["notes"]["1"]["title"] == "New Title"

    def test_update_append(self, _patch_paths):
        create_note({"title": "List", "content": "Item 1"})
        update_note({"note_id": "1", "content": "Item 2", "append": True})
        content = (_patch_paths["notes_dir"] / "1.md").read_text()
        assert "Item 1" in content
        assert "Item 2" in content

    def test_update_nonexistent(self, _patch_paths):
        result = update_note({"note_id": "999", "content": "x"})
        assert "not found" in result.lower()

    def test_update_no_content(self, _patch_paths):
        create_note({"title": "X", "content": "y"})
        result = update_note({"note_id": "1"})
        assert "provide" in result.lower()

    def test_update_no_id(self, _patch_paths):
        result = update_note({"content": "x"})
        assert "note_id" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Delete note
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeleteNote:
    def test_delete_by_id(self, _patch_paths, player):
        create_note({"title": "ToDelete", "content": "x"})
        result = delete_note({"note_id": "1"}, player)
        assert "deleted" in result.lower()
        assert not (_patch_paths["notes_dir"] / "1.md").exists()
        data = _load_index()
        assert "1" not in data["notes"]
        player.write_log.assert_called_once()

    def test_delete_nonexistent(self, _patch_paths):
        result = delete_note({"note_id": "999"})
        assert "not found" in result.lower()

    def test_delete_no_id(self, _patch_paths):
        result = delete_note({})
        assert "note_id" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Unified entry point
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotesUnified:
    def test_unknown_action(self, _patch_paths):
        result = notes({"action": "levitate"})
        assert "Unknown action" in result

    def test_alias_route_create(self, _patch_paths):
        for alias in ("new", "add"):
            result = notes({"action": alias, "title": "X", "content": "y"})
            assert "created" in result.lower() or "Note" in result

    def test_alias_route_read(self, _patch_paths):
        create_note({"title": "Readme", "content": "hello"})
        for alias in ("get", "open"):
            result = notes({"action": alias, "note_id": "1"})
            assert "hello" in result or "not found" in result.lower()

    def test_alias_route_delete(self, _patch_paths):
        create_note({"title": "DelMe", "content": "x"})
        result = notes({"action": "remove", "note_id": "1"})
        assert "deleted" in result.lower()
