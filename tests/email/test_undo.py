import json
import importlib

from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailOperationResult, OperationStatus
from core.email.providers.base import Capability, ProviderCapabilities
from core.email.service import EmailService
from core import undo as undo_stack


def test_read_state_change_registers_safe_inverse(monkeypatch):
    import actions.email_message as m
    undo_stack.clear()
    class P:
        def __init__(self): self.calls=[]; self.metadata=type("M",(),{"capabilities":ProviderCapabilities([Capability.FETCH,Capability.READ_STATE])})()
        def supports(self,c): return self.metadata.capabilities.supports(c)
        async def fetch_message(self,*a,**k): return type("M",(),{"is_read":False})()
        async def mark_read(self,ref): self.calls.append("read"); return EmailOperationResult("x",OperationStatus.SUCCESS,[ref])
        async def mark_unread(self,ref): self.calls.append("unread"); return EmailOperationResult("x",OperationStatus.SUCCESS,[ref])
    p=P(); svc=EmailService({"a1":EmailAccount("a1","x")},{"a1":p}); m.configure(svc)
    result=json.loads(m.TOOL["handler"]({"operation":"mark_read","account_id":"a1","mailbox":"INBOX","uid":"1"}))
    assert result["ok"] and p.calls == ["read"] and undo_stack.can_undo()
    assert "Undone" in undo_stack.undo_last() and p.calls == ["read","unread"]


def test_send_is_never_registered_as_undoable():
    undo_stack.clear()
    assert not undo_stack.can_undo()
