"""Provider-neutral email search action."""
from __future__ import annotations

from core.email.models import EmailSearchQuery
from .email_common import configure, error, ok, run, service, validate

LEGACY_ALIASES = ("read_emails", "email_search", "read_email")
_ALLOWED = {"account_id", "sender", "recipients", "subject", "body", "date_from", "date_to", "folders", "flags", "thread_id", "has_attachment", "limit", "offset", "sort_by", "sort_order"}


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, _ALLOWED, {"account_id"})
        account_id = p["account_id"].strip() if isinstance(p["account_id"], str) else p["account_id"]
        if not account_id: raise ValueError("account_id must be a non-empty string")
        query = EmailSearchQuery(**{k: v for k, v in p.items() if k != "account_id"})
        return ok(run(service().search(account_id, query)))
    except Exception as exc:
        return error(exc)

_PROPERTIES = {
    "account_id": {"type": "STRING"}, "sender": {"type": "STRING"}, "recipients": {"type": "ARRAY", "items": {"type": "STRING"}},
    "subject": {"type": "STRING"}, "body": {"type": "STRING"}, "date_from": {"type": "STRING"},
    "date_to": {"type": "STRING"}, "folders": {"type": "ARRAY", "items": {"type": "STRING"}}, "flags": {"type": "ARRAY", "items": {"type": "STRING"}},
    "thread_id": {"type": "STRING"}, "has_attachment": {"type": "BOOLEAN"}, "limit": {"type": "INTEGER"},
    "offset": {"type": "INTEGER"}, "sort_by": {"type": "STRING"}, "sort_order": {"type": "STRING"},
}
TOOL = {"name": "email_search", "description": "Search an email account using provider-neutral filters and bounded result limits.", "parameters": {"type": "OBJECT", "properties": _PROPERTIES, "required": ["account_id"]}, "handler": _handler}
