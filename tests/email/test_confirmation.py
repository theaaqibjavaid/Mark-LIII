import json
import importlib

from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailOperationResult, OperationStatus
from core.email.providers.base import Capability, ProviderCapabilities
from core.email.service import EmailService


def _service():
    class P:
        def __init__(self):
            self.calls=[]; self.metadata=type("M",(),{"capabilities":ProviderCapabilities(list(Capability))})()
        def supports(self,c): return self.metadata.capabilities.supports(c)
        async def send(self, **kw): self.calls.append("send"); return EmailOperationResult("x",OperationStatus.SUCCESS)
        async def delete_message(self, ref): self.calls.append("delete"); return EmailOperationResult("x",OperationStatus.SUCCESS,[ref])
        async def fetch_message(self, *a, **k): return type("M",(),{"is_read":False})()
    p=P(); return EmailService({"a1":EmailAccount("a1","x",primary_address=EmailAddress("me@example.com"))},{"a1":p}),p


def test_send_ignores_model_confirmed_and_uses_gate(monkeypatch):
    import actions.email_compose as m
    svc,p=_service(); m.configure(svc); captured={}
    monkeypatch.setattr(m.confirm_gate,"request",lambda key,title,detail,run: captured.update({"run":run}) or "[CONFIRMATION_PENDING] pending")
    result=json.loads(m.TOOL["handler"]({"operation":"send","account_id":"a1","to":["bob@example.com"],"subject":"Hi","body":"Hello","confirmed":True})) if False else m.TOOL["handler"]({"operation":"send","account_id":"a1","to":["bob@example.com"],"subject":"Hi","body":"Hello","confirmed":True})
    assert result.startswith("[CONFIRMATION_PENDING]") and p.calls == []
    captured["run"](); assert p.calls == ["send"]


def test_delete_ignores_forged_confirmed_flag(monkeypatch):
    import actions.email_mailbox as m
    svc,p=_service(); m.configure(svc); captured={}
    monkeypatch.setattr(m.confirm_gate,"request",lambda key,title,detail,run: captured.update({"run":run}) or "[CONFIRMATION_PENDING] pending")
    result=m.TOOL["handler"]({"operation":"delete","account_id":"a1","mailbox":"INBOX","uid":"1","confirmed":True})
    assert result.startswith("[CONFIRMATION_PENDING]") and p.calls == []
    captured["run"](); assert p.calls == ["delete"]
