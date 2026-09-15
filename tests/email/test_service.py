import asyncio
import pytest
from core.email.errors import ProviderCapabilityError
from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailOperationResult, EmailSearchQuery, OperationStatus
from core.email.service import EmailService
from core.email.providers.base import Capability, ProviderCapabilities

class FakeProvider:
    def __init__(self, capabilities=None, send_exception=None, send_result=None):
        self.calls=[]; self.send_exception=send_exception; self.send_result=send_result
        self._capabilities=ProviderCapabilities(capabilities if capabilities is not None else list(Capability))
        self.metadata=type("Meta",(),{"account_id":"a1","capabilities":self._capabilities})()
    def supports(self, capability): return self._capabilities.supports(capability)
    async def search(self, query): self.calls.append(("search",query)); return [EmailMessageRef("a1","INBOX","10")]
    async def fetch_message(self, ref, include_body=True, include_attachments=False): self.calls.append(("fetch_message",ref,include_body,include_attachments)); return "message"
    async def mark_read(self, ref): self.calls.append(("mark_read",ref)); return EmailOperationResult("op",OperationStatus.SUCCESS,[ref])
    async def send(self, **kwargs):
        self.calls.append(("send",kwargs))
        if self.send_exception: raise self.send_exception
        return self.send_result or EmailOperationResult("provider-op",OperationStatus.SUCCESS)

def run(coro): return asyncio.run(coro)
def service(provider, enabled=True): return EmailService({"a1":EmailAccount("a1","generic",primary_address=EmailAddress("me@example.com"),enabled=enabled)},{"a1":provider})
def args(): return ("a1",[EmailAddress("bob@example.com")],"Hello")

def test_search_normalizes_and_delegates():
    p=FakeProvider(); assert run(service(p).search("a1",EmailSearchQuery(subject=" invoice ")))[0].uid=="10"; assert p.calls[0][1].subject=="invoice"
def test_search_capability_is_checked_before_call():
    p=FakeProvider([])
    with pytest.raises(ProviderCapabilityError): run(service(p).search("a1",EmailSearchQuery(subject="x")))
    assert not p.calls
def test_get_message_enforces_reference_and_fetch_capability():
    p=FakeProvider([Capability.FETCH]); ref=EmailMessageRef("a1","INBOX","10"); assert run(service(p).get_message("a1",ref,include_body=False,include_attachments=True))=="message"
def test_mark_read_delegates():
    p=FakeProvider([Capability.READ_STATE]); assert run(service(p).mark_read("a1",EmailMessageRef("a1","INBOX","10"))).is_success
def test_send_requires_confirmation():
    p=FakeProvider([Capability.SEND])
    with pytest.raises(PermissionError): run(service(p).send(*args()))
    assert not p.calls
def test_send_replays_success_without_second_provider_call():
    p=FakeProvider([Capability.SEND]); s=service(p); first=run(s.send(*args(),confirmed=True,operation_id="op-1")); second=run(s.send(*args(),confirmed=True,operation_id="op-1")); assert first==second and len(p.calls)==1
def test_send_rejects_fingerprint_reuse_with_different_payload():
    p=FakeProvider([Capability.SEND]); s=service(p); run(s.send(*args(),confirmed=True,operation_id="op-1"))
    with pytest.raises(ValueError,match="fingerprint"): run(s.send("a1",[EmailAddress("bob@example.com")],"Different",confirmed=True,operation_id="op-1"))
def test_ambiguous_send_is_persisted_and_not_retried():
    p=FakeProvider([Capability.SEND],send_exception=RuntimeError("transport dropped")); s=service(p); first=run(s.send(*args(),confirmed=True,operation_id="op-u")); second=run(s.send(*args(),confirmed=True,operation_id="op-u")); assert first.status==OperationStatus.UNKNOWN and second==first and len(p.calls)==1
def test_provider_unknown_is_persisted():
    p=FakeProvider([Capability.SEND],send_result=EmailOperationResult("x",OperationStatus.UNKNOWN,error_code="unknown")); s=service(p); first=run(s.send(*args(),confirmed=True,operation_id="op-u")); second=run(s.send(*args(),confirmed=True,operation_id="op-u")); assert first==second and len(p.calls)==1
def test_cross_account_reference_is_rejected():
    p=FakeProvider([Capability.FETCH])
    with pytest.raises(ValueError,match="different account"): run(service(p).get_message("a1",EmailMessageRef("other","INBOX","10")))
def test_disabled_account_is_rejected():
    p=FakeProvider([Capability.SEARCH])
    with pytest.raises(PermissionError,match="disabled"): run(service(p,enabled=False).search("a1",EmailSearchQuery(subject="x")))
def test_reply_confirmation_precedes_provider_unsupported_error():
    p=FakeProvider([Capability.REPLY])
    with pytest.raises(PermissionError,match="Confirmation"): run(service(p).reply("a1",EmailMessageRef("a1","INBOX","10")))
def test_reply_requires_advertised_capability():
    p=FakeProvider([])
    with pytest.raises(ProviderCapabilityError): run(service(p).reply("a1",EmailMessageRef("a1","INBOX","10"),confirmed=True))
def test_unknown_account_is_rejected():
    with pytest.raises(KeyError): run(EmailService({},{}).search("missing",EmailSearchQuery(subject="x")))
