"""Safe email attachment metadata access."""
from __future__ import annotations

from core.email.models import EmailMessageRef
from .email_common import configure, error, ok, run, service, validate, nonempty

LEGACY_ALIASES = ("email_attachment", "get_email_attachments")


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, {"account_id", "mailbox", "uid"}, {"account_id", "mailbox", "uid"})
        ref = EmailMessageRef(nonempty(p["account_id"], "account_id"), nonempty(p["mailbox"], "mailbox"), nonempty(p["uid"], "uid"))
        return ok(run(service().fetch_attachments(ref.account_id, ref)))
    except Exception as exc: return error(exc)

TOOL = {"name": "email_attachment", "description": "Return bounded provider-neutral attachment metadata only; attachment content is never implicitly exposed as action output.", "parameters": {"type": "OBJECT", "properties": {"account_id": {"type": "STRING"}, "mailbox": {"type": "STRING"}, "uid": {"type": "STRING"}}, "required": ["account_id", "mailbox", "uid"]}, "handler": _handler}
