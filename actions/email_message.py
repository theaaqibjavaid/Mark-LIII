"""Email message retrieval and state actions with safety boundaries."""
from __future__ import annotations

from core.email.models import EmailAddress, EmailMessageRef
from core.email.policy import OperationCategory
from core import confirm as confirm_gate
from core import undo as undo_stack
from .email_common import configure, error, ok, run, service, validate, nonempty

LEGACY_ALIASES = ("send_email", "reply_email", "reply_all_email", "forward_email", "email_message")
_ALLOWED = {"operation", "account_id", "mailbox", "uid", "body", "html", "recipients", "confirmed", "operation_id"}
_HIGH_IMPACT = {"send", "reply", "reply_all", "forward"}


def _ref(p):
    return EmailMessageRef(nonempty(p["account_id"], "account_id"), nonempty(p["mailbox"], "mailbox"), nonempty(p["uid"], "uid"))


def _confirmed_execution(operation, p):
    svc = service()
    ref = _ref(p)
    body = p.get("body")
    html = p.get("html")
    if operation == "reply":
        return lambda: run(svc.reply(ref.account_id, ref, body_plain=body, body_html=html, confirmed=True, operation_id=p.get("operation_id")))
    if operation == "reply_all":
        return lambda: run(svc.reply_all(ref.account_id, ref, body_plain=body, body_html=html, confirmed=True, operation_id=p.get("operation_id")))
    recipients = [EmailAddress(x) for x in p.get("recipients", [])]
    return lambda: run(svc.forward(ref.account_id, ref, recipients, body_plain=body, body_html=html, confirmed=True, operation_id=p.get("operation_id")))


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, _ALLOWED, {"operation", "account_id", "mailbox", "uid"})
        operation = nonempty(p["operation"], "operation").lower()
        svc = service()
        ref = _ref(p)
        if operation == "get": return ok(run(svc.get_message(ref.account_id, ref, include_body=True, include_attachments=True)))
        if operation == "mark_read":
            before = run(svc.get_message(ref.account_id, ref, include_body=False, include_attachments=False))
            result = run(svc.mark_read(ref.account_id, ref))
            if result.is_success and getattr(before, "is_read", False) is False:
                undo_stack.push_undo(f"Mark email {ref.uid} unread", lambda: run(svc.mark_unread(ref.account_id, ref)))
            return ok(result)
        if operation == "mark_unread":
            before = run(svc.get_message(ref.account_id, ref, include_body=False, include_attachments=False))
            result = run(svc.mark_unread(ref.account_id, ref))
            if result.is_success and getattr(before, "is_read", False) is True:
                undo_stack.push_undo(f"Mark email {ref.uid} read", lambda: run(svc.mark_read(ref.account_id, ref)))
            return ok(result)
        if operation in _HIGH_IMPACT:
            title = {"reply": "Reply to email", "reply_all": "Reply-all to email", "forward": "Forward email"}[operation]
            detail = f"Account {ref.account_id}, message {ref.uid}"
            pending = confirm_gate.request(f"email:{operation}:{ref.account_id}:{ref.uid}", title, detail, _confirmed_execution(operation, p))
            return pending if pending.startswith("[CONFIRMATION_PENDING]") else ok({"status": "confirmation_pending", "message": pending})
        raise ValueError("Unsupported message operation")
    except Exception as exc:
        return error(exc)

TOOL = {"name": "email_message", "description": "Retrieve email messages, change read state, or prepare reply/reply-all/forward actions behind the trusted confirmation gate.", "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}, "account_id": {"type": "STRING"}, "mailbox": {"type": "STRING"}, "uid": {"type": "STRING"}, "body": {"type": "STRING"}, "html": {"type": "STRING"}, "recipients": {"type": "ARRAY"}, "confirmed": {"type": "BOOLEAN"}, "operation_id": {"type": "STRING"}}, "required": ["operation", "account_id", "mailbox", "uid"]}, "handler": _handler}
