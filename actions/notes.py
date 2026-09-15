"""
Notes — persistent note-taking for JARVIS.

Stores notes as individual .md files in memory/notes/ (or as entries in
memory/notes_index.json for quick list/search). Supports create, read, list,
search, and delete operations. Each note is a real file on disk, so the user
can also edit them directly.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


NOTES_DIR       = _base_dir() / "memory" / "notes"
INDEX_PATH      = _base_dir() / "memory" / "notes_index.json"


# ── Index management ───────────────────────────────────────────────────────────

def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"notes": {}, "next_id": 1}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"notes": {}, "next_id": 1}


def _save_index(data: dict) -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _safe_filename(title: str) -> str:
    """Sanitize a title into a filesystem-safe filename."""
    slug = re.sub(r"[^\w\s\-]", "", title).strip()
    slug = re.sub(r"\s+", "-", slug)
    return slug[:80] or "untitled"


def _note_path(note_id: int) -> Path:
    return NOTES_DIR / f"{note_id}.md"


# ── Core operations ────────────────────────────────────────────────────────────

def create_note(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Create a new note.

    Parameters:
        title   : note title (auto-generated from first line if omitted)
        content : note body (markdown supported)
        tags    : comma-separated tags for categorisation
    """
    params    = parameters or {}
    title     = (params.get("title") or "").strip()
    content   = (params.get("content") or params.get("text") or "").strip()
    tags_str  = (params.get("tags") or "").strip()
    tags      = [t.strip().lower() for t in re.split(r"[,\s]+", tags_str) if t.strip()] if tags_str else []

    # Auto-title from first line of content
    if not title and content:
        first_line = content.splitlines()[0][:60]
        title = first_line or "Untitled"
    elif not title:
        title = "Untitled"

    data       = _load_index()
    note_id    = data["next_id"]
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_title = _safe_filename(title)

    # Build file content
    header_lines = [
        f"# {title}",
        f"",
        f"**Created:** {now_str}",
    ]
    if tags:
        header_lines.append(f"**Tags:** {', '.join(tags)}")
    header_lines.append("")
    header_lines.append("---")
    header_lines.append("")

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    file_content = "\n".join(header_lines) + content

    note_file = NOTES_DIR / f"{note_id}.md"
    note_file.write_text(file_content, encoding="utf-8")

    data["notes"][str(note_id)] = {
        "id":       note_id,
        "title":    title,
        "tags":     tags,
        "created":  now_str,
        "updated":  now_str,
        "path":     str(note_file),
    }
    data["next_id"] += 1
    _save_index(data)

    if player:
        player.write_log(f"[Notes] Created: {title} (#{note_id})")

    return f"Note created: '{title}' (ID {note_id}). Saved to {note_file}."


def read_note(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Read a note by ID or title keyword.
    """
    params    = parameters or {}
    note_id   = params.get("note_id", "").strip()
    keyword   = params.get("keyword", "").strip()
    path      = params.get("path", "").strip()

    if path:
        p = Path(path)
        if not p.exists():
            return f"Note file not found: {path}"
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read note: {e}"

    data = _load_index()

    # Lookup by numeric ID
    if note_id:
        try:
            nid = int(note_id)
        except ValueError:
            return f"Could not parse note ID: {note_id}"
        note_info = data["notes"].get(str(nid))
        if not note_info:
            return f"Note #{nid} not found."
        note_file = NOTES_DIR / f"{nid}.md"
        if note_file.exists():
            return note_file.read_text(encoding="utf-8")
        return f"Note #{nid} index entry exists but file is missing."

    # Lookup by keyword
    if keyword:
        matches = [
            (nid, info) for nid, info in data["notes"].items()
            if keyword.lower() in info.get("title", "").lower()
            or keyword.lower() in [t.lower() for t in info.get("tags", [])]
        ]
        if not matches:
            # Also search file contents
            matches = []
            for f in sorted(NOTES_DIR.glob("*.md")):
                try:
                    content = f.read_text(encoding="utf-8")
                    if keyword.lower() in content.lower():
                        matches.append((f.stem, {"title": f.stem, "tags": [], "path": str(f)}))
                except Exception:
                    continue
        if not matches:
            return f"No notes matching '{keyword}'."
        results = []
        for nid, info in matches:
            note_file = NOTES_DIR / f"{nid}.md"
            if note_file.exists():
                results.append(f"=== {info.get('title', nid)} ===\n{note_file.read_text(encoding='utf-8')}")
        return "\n\n".join(results)

    return "Provide a note_id, keyword, or path to read a note."


def list_notes(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    List all notes, optionally filtered by tag or sorted.
    """
    params    = parameters or {}
    tag       = (params.get("tag") or "").strip().lower()
    sort_by   = (params.get("sort_by") or "title").lower()

    data = _load_index()
    notes = list(data.get("notes", {}).values())

    if tag:
        notes = [n for n in notes if tag in [t.lower() for t in n.get("tags", [])]]

    if sort_by == "date":
        notes.sort(key=lambda n: n.get("updated", ""), reverse=True)
    else:
        notes.sort(key=lambda n: n.get("title", "").lower())

    if not notes:
        if tag:
            return f"No notes with tag '{tag}'."
        return "No notes yet. Create one with 'create a note about …'."

    lines = [f"Notes ({len(notes)} total):", ""]
    for n in notes:
        tags_str = f"  [{', '.join(n.get('tags', []))}]" if n.get("tags") else ""
        lines.append(f"  #{n['id']}  {n['title']}{tags_str}  ({n.get('updated', '?')})")

    return "\n".join(lines)


def search_notes(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Search note contents for a keyword. Returns matching snippets.
    """
    params    = parameters or {}
    query     = (params.get("query") or params.get("keyword") or "").strip().lower()
    limit     = min(int(params.get("limit") or 10), 50)

    if not query:
        return "Please provide a search query."

    results: list[dict] = []
    for f in sorted(NOTES_DIR.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if query not in content.lower():
            continue

        # Extract title from first line
        title = f.stem
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Find matching snippet
        lines = content.splitlines()
        snippet_lines = []
        for i, line in enumerate(lines):
            if query in line.lower():
                start = max(0, i - 2)
                end   = min(len(lines), i + 3)
                snippet_lines = lines[start:end]
                break

        results.append({
            "id":       f.stem,
            "title":    title,
            "snippet":  "\n".join(snippet_lines).strip(),
            "path":     str(f),
        })
        if len(results) >= limit:
            break

    if not results:
        return f"No notes found containing '{query}'."

    lines = [f"Search results for '{query}' ({len(results)} found):", ""]
    for r in results:
        lines.append(f"  📝 {r['title']} (#{r['id']})")
        lines.append(f"     {r['snippet'][:150]}")
        lines.append("")

    return "\n".join(lines)


def update_note(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Update an existing note's content or metadata.

    Parameters:
        note_id  : numeric ID of the note to update
        content  : new full content (replaces everything after the header)
        title    : new title (updates header and index)
        append   : if True, append content instead of replacing
    """
    params    = parameters or {}
    note_id_s = params.get("note_id", "").strip()
    new_title = (params.get("title") or "").strip()
    content   = (params.get("content") or params.get("text") or "").strip()
    append    = bool(params.get("append", False))

    if not note_id_s:
        return "Please provide a note_id to update."
    try:
        nid = int(note_id_s)
    except ValueError:
        return f"Could not parse note ID: {note_id_s}"

    note_file = NOTES_DIR / f"{nid}.md"
    if not note_file.exists():
        return f"Note #{nid} not found."

    try:
        existing = note_file.read_text(encoding="utf-8")
    except Exception as e:
        return f"Could not read note #{nid}: {e}"

    new_title = (params.get("title") or "").strip()
    content   = (params.get("content") or params.get("text") or "").strip()
    append    = bool(params.get("append", False))

    # If no content provided but title is, just update the title
    if not content and new_title:
        # Only update header
        header_lines = []
        for line in existing.splitlines():
            if line.startswith("# "):
                header_lines.append(f"# {new_title}")
            elif line.startswith("**Updated:**"):
                header_lines.append(f"**Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            else:
                header_lines.append(line)
        note_file.write_text("\n".join(header_lines) + "\n" + existing.split("---", 1)[1] if "---" in existing else "\n".join(header_lines), encoding="utf-8")

        data = _load_index()
        info = data["notes"].get(str(nid))
        if info:
            info["title"]    = new_title
            info["updated"]  = datetime.now().strftime("%Y-%m-%d %H:%M")
            data["notes"][str(nid)] = info
            _save_index(data)

        if player:
            player.write_log(f"[Notes] Updated: #{nid}")
        return f"Note #{nid} updated."
    elif not content:
        return "Please provide new content."

    # Split header from body
    sep_idx = existing.find("\n---\n")
    if sep_idx == -1:
        sep_idx = existing.find("\n---")
    if sep_idx == -1:
        header = ""
        body   = existing
    else:
        header = existing[:sep_idx + 1]
        body   = existing[sep_idx + 1:].lstrip("\n")

    if append:
        new_body = body + "\n\n" + content
    else:
        new_body = content

    # Update title in header if provided
    if new_title:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        header_lines = []
        for line in header.splitlines():
            if line.startswith("# "):
                header_lines.append(f"# {new_title}")
            elif line.startswith("**Updated:**"):
                header_lines.append(f"**Updated:** {now_str}")
            else:
                header_lines.append(line)
        header = "\n".join(header_lines) + "\n"

        # Update index
        data = _load_index()
        info = data["notes"].get(str(nid))
        if info:
            info["title"]    = new_title
            info["updated"]  = now_str
            data["notes"][str(nid)] = info
            _save_index(data)

    note_file.write_text(header + new_body, encoding="utf-8")

    if player:
        player.write_log(f"[Notes] Updated: #{nid}")

    return f"Note #{nid} updated."


def delete_note(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Delete a note by ID.
    """
    params    = parameters or {}
    note_id_s = params.get("note_id", "").strip()

    if not note_id_s:
        return "Please provide a note_id to delete."
    try:
        nid = int(note_id_s)
    except ValueError:
        return f"Could not parse note ID: {note_id_s}"

    note_file = NOTES_DIR / f"{nid}.md"
    if not note_file.exists():
        return f"Note #{nid} not found."

    note_file.unlink()

    data = _load_index()
    if str(nid) in data.get("notes", {}):
        del data["notes"][str(nid)]
        _save_index(data)

    if player:
        player.write_log(f"[Notes] Deleted: #{nid}")

    return f"Note #{nid} deleted."


def notes(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    """
    Unified entry point. Gemini should set the `action` parameter.
    """
    params   = parameters or {}
    action   = (params.get("action") or "").lower().strip()

    if action in ("create", "new", "add"):
        return create_note(params, player, session_memory)
    if action in ("read", "get", "open"):
        return read_note(params, player, session_memory)
    if action in ("list", "show"):
        return list_notes(params, player, session_memory)
    if action in ("search", "find"):
        return search_notes(params, player, session_memory)
    if action in ("update", "edit"):
        return update_note(params, player, session_memory)
    if action in ("delete", "remove"):
        return delete_note(params, player, session_memory)
    return (
        f"Unknown action: '{action}'. "
        "Use create, read, list, search, update, or delete."
    )


# ── Tool declaration ───────────────────────────────────────────────────────────

TOOL = {
    "name": "notes",
    "description": (
        "Create, read, list, search, update, and delete notes. Notes are "
        "stored as real .md files in memory/notes/ and indexed in "
        "memory/notes_index.json. Use 'action=create' with a title and "
        "content to write a new note, 'action=read' with a note_id or "
        "keyword to retrieve one, 'action=list' to see all notes, "
        "'action=search' to find notes by keyword, 'action=update' to "
        "edit an existing note, and 'action=delete' to remove one."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create | read | list | search | update | delete",
            },
            "title": {
                "type": "STRING",
                "description": "Note title (create/update).",
            },
            "content": {
                "type": "STRING",
                "description": "Note body content (markdown supported).",
            },
            "text": {
                "type": "STRING",
                "description": "Alias for content.",
            },
            "tags": {
                "type": "STRING",
                "description": "Comma-separated tags for categorisation.",
            },
            "note_id": {
                "type": "STRING",
                "description": "Numeric ID of a note (read/update/delete).",
            },
            "keyword": {
                "type": "STRING",
                "description": "Keyword to search by title, tag, or content.",
            },
            "query": {
                "type": "STRING",
                "description": "Search query (alternative to keyword).",
            },
            "tag": {
                "type": "STRING",
                "description": "Filter list by tag.",
            },
            "sort_by": {
                "type": "STRING",
                "description": "Sort order for list: 'title' (default) or 'date'.",
            },
            "append": {
                "type": "BOOLEAN",
                "description": "Append to note instead of replacing content.",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Max results for search (default: 10).",
            },
            "path": {
                "type": "STRING",
                "description": "Direct file path for read operations.",
            },
        },
        "required": ["action"],
    },
    "handler": notes,
}
