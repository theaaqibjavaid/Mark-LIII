"""Email draft/send composition action. Drafting is never an implicit send."""
from __future__ import annotations

from core.email.limits import EmailLimits
from core.email.models import EmailAddress, EmailAttachment, EmailDraft
from core import confirm as confirm_gate
from .email_common import configure, error, ok, run, service, validate, nonempty, list_of_strings

LEGACY_ALIASES = ("send_email", "compose_email", "write_email", "email_compose")
_ALLOWED = {"operation", "account_id", "to", "cc", "bcc", "reply_to", "subject", "body", "html", "attachments", "draft_id", "mailbox", "uid", "operation_id", "confirmed"}


def _addresses(value, name, required=False):
    if value is None:
        if required: raise ValueError(f"{name} must be provided")
        return []
    return [EmailAddress(x) for x in list_of_strings(value, name, max_items=EmailLimits.MAX_RECIPIENTS_PER_MESSAGE)]


def _attachments(value):
    if value is None: return []
    if not isinstance(value, list) or len(value) > EmailLimits.MAX_ATTACHMENTS_PER_MESSAGE:
        raise ValueError("attachments exceeds configured maximum")
    result = []
    for item in value:
        if not isinstance(item, dict): raise ValueError("each attachment must be an object")
        required = {"attachment_id", "filename", "content_type", "byte_size"}
        if not required.issubset(item): raise ValueError("attachment metadata is incomplete")
        result.append(EmailAttachment(item["attachment_id"], item["filename"], item["content_type"], int(item["byte_size"]), content_handle=item.get("content_handle")))
    EmailLimits.validate_total_attachment_size(sum(x.byte_size for x in result))
    return result


def _draft(p):
    return EmailDraft(draft_id=p.get("draft_id"), recipients=_addresses(p.get("to"), "to"), subject=p.get("subject", ""), body_plain=p.get("body"), body_html=p.get("html"), attachments=_attachments(p.get("attachments")))


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, _ALLOWED, {"operation", "account_id"})
        op = nonempty(p["operation"], "operation").lower()
        svc = service(); account_id = nonempty(p["account_id"], "account_id")
        if op == "create_draft": return ok(run(svc.create_draft(account_id, _draft(p))))
        if op == "update_draft":
            ref = __import__("core.email.models", fromlist=["EmailMessageRef"]).EmailMessageRef(account_id, nonempty(p.get("mailbox"), "mailbox"), nonempty(p.get("uid"), "uid"))
            return ok(run(svc.update_draft(account_id, ref, _draft(p))))
        if op == "send":
            recipients = _addresses(p.get("to"), "to", required=True)
            cc = _addresses(p.get("cc"), "cc"); bcc = _addresses(p.get("bcc"), "bcc")
            EmailLimits.validate_recipient_count(len(recipients) + len(cc) + len(bcc))
            subject = p.get("subject", "")
            if not isinstance(subject, str): raise ValueError("subject must be a string")
            EmailLimits.validate_subject_length(len(subject))
            attachments = _attachments(p.get("attachments"))
            def execute():
                return run(svc.send(account_id, recipients, subject, body_plain=p.get("body"), body_html=p.get("html"), attachments=attachments, cc=cc, bcc=bcc, reply_to=EmailAddress(p["reply_to"]) if p.get("reply_to") else None, confirmed=True, operation_id=p.get("operation_id")))
            pending = confirm_gate.request(f"email:send:{account_id}:{p.get('operation_id','new')}", "Send email", f"Account {account_id}; {len(recipients)+len(cc)+len(bcc)} recipient(s)", execute)
            return pending
        raise ValueError("Unsupported compose operation")
    except Exception as exc:
        return error(exc)

TOOL = {"name": "email_compose", "description": "Create or update drafts, or send an email only after the trusted user confirmation gate; draft operations never send.", "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}, "account_id": {"type": "STRING"}, "to": {"type": "ARRAY", "items": {"type": "STRING"}}, "cc": {"type": "ARRAY", "items": {"type": "STRING"}}, "bcc": {"type": "ARRAY", "items": {"type": "STRING"}}, "reply_to": {"type": "STRING"}, "subject": {"type": "STRING"}, "body": {"type": "STRING"}, "html": {"type": "STRING"}, "attachments": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"attachment_id": {"type": "STRING"}, "filename": {"type": "STRING"}, "content_type": {"type": "STRING"}, "byte_size": {"type": "INTEGER"}, "content_handle": {"type": "STRING"}}, "required": ["attachment_id", "filename", "content_type", "byte_size"]}}, "draft_id": {"type": "STRING"}, "mailbox": {"type": "STRING"}, "uid": {"type": "STRING"}, "operation_id": {"type": "STRING"}, "confirmed": {"type": "BOOLEAN"}}, "required": ["operation", "account_id"]}, "handler": _handler}
