"""Email mailbox/folder and message mutation actions."""
from __future__ import annotations

from core.email.models import EmailMessageRef
from core import confirm as confirm_gate
from core import undo as undo_stack
from .email_common import configure, error, ok, run, service, validate, nonempty

LEGACY_ALIASES = ("archive_email", "delete_email", "move_email", "flag_email", "email_mailbox")
_ALLOWED = {"operation", "account_id", "mailbox", "uid", "target_folder", "flag", "confirmed", "refs"}


def _ref(account_id, mailbox, uid): return EmailMessageRef(nonempty(account_id, "account_id"), nonempty(mailbox, "mailbox"), nonempty(uid, "uid"))


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, _ALLOWED, {"operation", "account_id"})
        op = nonempty(p["operation"], "operation").lower(); account_id = nonempty(p["account_id"], "account_id"); svc = service()
        if op == "list_folders": return ok(run(svc._providers[account_id].list_folders()))
        ref = _ref(account_id, p.get("mailbox"), p.get("uid"))
        if op == "mark_read": return ok(run(svc.mark_read(account_id, ref)))
        if op == "mark_unread": return ok(run(svc.mark_unread(account_id, ref)))
        if op == "flag": return ok(run(svc.add_flag(account_id, ref, nonempty(p.get("flag"), "flag"))))
        if op == "unflag": return ok(run(svc.remove_flag(account_id, ref, nonempty(p.get("flag"), "flag"))))
        if op == "archive": return ok(run(svc.archive(account_id, ref)))
        if op in {"move", "copy"}:
            target = nonempty(p.get("target_folder"), "target_folder")
            if op == "move":
                result = run(svc.move(account_id, ref, target))
                if result.is_success: undo_stack.push_undo(f"Move email {ref.uid} back to {ref.mailbox}", lambda: run(svc.move(account_id, ref, ref.mailbox)))
            else:
                result = run(svc.copy(account_id, ref, target))
                # Copy is reversible only when the provider returns an affected ref
                # in the target mailbox; otherwise no unsafe inverse is fabricated.
                if result.is_success and len(result.affected_refs) == 1:
                    copied = result.affected_refs[0]
                    undo_stack.push_undo(f"Remove copied email {copied.uid}", lambda: run(svc.delete(account_id, copied, confirmed=True)))
            return ok(result)
        if op == "delete":
            pending = confirm_gate.request(f"email:delete:{account_id}:{ref.uid}", "Delete email", f"Account {account_id}; message {ref.uid}", lambda: run(svc.delete(account_id, ref, confirmed=True)))
            return pending
        if op == "bulk_delete":
            refs = p.get("refs")
            if not isinstance(refs, list) or not refs or len(refs) > 100: raise ValueError("refs must contain 1 to 100 message references")
            parsed = [_ref(account_id, item.get("mailbox"), item.get("uid")) if isinstance(item, dict) else (_ for _ in ()).throw(ValueError("each ref must be an object")) for item in refs]
            def execute_bulk():
                return [run(svc.delete(account_id, r, confirmed=True)) for r in parsed]
            return confirm_gate.request(f"email:bulk_delete:{account_id}", "Delete multiple emails", f"Account {account_id}; {len(parsed)} messages", execute_bulk)
        raise ValueError("Unsupported mailbox operation")
    except Exception as exc: return error(exc)

TOOL = {"name": "email_mailbox", "description": "List folders and perform mailbox/message state operations; delete and bulk delete always use trusted confirmation.", "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}, "account_id": {"type": "STRING"}, "mailbox": {"type": "STRING"}, "uid": {"type": "STRING"}, "target_folder": {"type": "STRING"}, "flag": {"type": "STRING"}, "confirmed": {"type": "BOOLEAN"}, "refs": {"type": "ARRAY"}}, "required": ["operation", "account_id"]}, "handler": _handler}
