"""Provider-neutral email search normalization and best-effort threading."""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import Optional

from .models import EmailMessage, EmailSearchQuery, EmailThread


def normalize_search_query(query: EmailSearchQuery) -> EmailSearchQuery:
    if not isinstance(query, EmailSearchQuery):
        raise TypeError("query must be an EmailSearchQuery")
    if query.date_from and query.date_to and query.date_from > query.date_to:
        raise ValueError("date_from must not be after date_to")
    fields = (query.sender, query.subject, query.body, query.thread_id, query.folders, query.flags, query.has_attachment)
    if not any(v not in (None, "", []) for v in fields):
        raise ValueError("search query must contain at least one criterion")
    folders = [f.strip() for f in query.folders or [] if f and f.strip()]
    flags = [f.strip() for f in query.flags or [] if f and f.strip()]
    if query.folders is not None and not folders:
        raise ValueError("folders must contain a non-empty folder")
    if query.flags is not None and not flags:
        raise ValueError("flags must contain a non-empty flag")
    if query.sort_by not in {"date", "subject", "sender"}:
        raise ValueError("unsupported sort field")
    if query.sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be asc or desc")
    return replace(
        query,
        sender=query.sender.strip() if query.sender else None,
        subject=query.subject.strip() if query.subject else None,
        body=query.body.strip() if query.body else None,
        folders=folders or None,
        flags=flags or None,
        limit=query.resolved_limit,
    )


def thread_key_for_message(
    provider_thread_id: Optional[str],
    message_id: Optional[str],
    references: list[str],
    subject: str,
) -> str:
    if provider_thread_id:
        return f"provider:{provider_thread_id}"
    if references:
        return f"ref:{references[0]}"
    if message_id:
        return f"msg:{message_id}"
    normalized = re.sub(r"^\s*(re|fwd?)\s*:\s*", "", subject or "", flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return f"subject:{normalized}"


def resolve_thread(messages: list[EmailMessage]) -> EmailThread:
    if not messages:
        raise ValueError("cannot resolve an empty thread")
    keys = []
    for message in messages:
        metadata = message.provider_metadata or {}
        refs = metadata.get("references", [])
        keys.append(thread_key_for_message(metadata.get("thread_id") or message.thread_id, metadata.get("message_id"), refs, message.subject))
    key = keys[0]
    ordered = sorted(messages, key=lambda m: m.date or datetime.min)
    return EmailThread(
        thread_key=key,
        messages=[m.reference for m in ordered],
        subject=ordered[-1].subject,
        first_message_date=ordered[0].date,
        last_message_date=ordered[-1].date,
    )
