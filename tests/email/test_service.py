import asyncio

import pytest

from core.email.errors import ProviderCapabilityError
from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailOperationResult, EmailSearchQuery, OperationStatus
from core.email.service import EmailService
from core.email.providers.base import Capability, ProviderCapabilities


class FakeProvider:
    def __init__(self, capabilities=None):
        self.calls = []
        self._capabilities = ProviderCapabilities(capabilities if capabilities is not None else list(Capability))
        self.metadata = type("Meta", (), {"account_id": "a1", "capabilities": self._capabilities})()

    async def search(self, query):
        self.calls.append(("search", query))
        return [EmailMessageRef("a1", "INBOX", "10")]

    async def fetch_message(self, ref, include_body=True, include_attachments=False):
        self.calls.append(("fetch_message", ref, include_body, include_attachments))
        return "message"

    async def mark_read(self, ref):
        self.calls.append(("mark_read", ref))
        return EmailOperationResult("op", OperationStatus.SUCCESS, [ref])

    async def send(self, message, operation_id):
        self.calls.append(("send", message, operation_id))
        return EmailOperationResult(operation_id, OperationStatus.SUCCESS)

    async def reply(self, payload, operation_id):
        self.calls.append(("reply", payload, operation_id))
        return EmailOperationResult(operation_id, OperationStatus.SUCCESS)


def run(coro):
    return asyncio.run(coro)


def make_service(provider, *, primary=False):
    account = EmailAccount("a1", "generic", primary_address=EmailAddress("me@example.com") if primary else None)
    return EmailService({"a1": account}, {"a1": provider})


def test_search_normalizes_query_and_delegates_without_provider_syntax():
    provider = FakeProvider()
    result = run(make_service(provider).search("a1", EmailSearchQuery(subject=" invoice ", limit=2)))
    assert result == [EmailMessageRef("a1", "INBOX", "10")]
    assert provider.calls[0][1].subject == "invoice"


def test_search_rejects_missing_capability_before_provider_call():
    provider = FakeProvider([])
    with pytest.raises(ProviderCapabilityError):
        run(make_service(provider).search("a1", EmailSearchQuery(subject="invoice")))
    assert provider.calls == []


def test_get_message_enforces_fetch_capability_and_arguments():
    provider = FakeProvider([Capability.FETCH])
    ref = EmailMessageRef("a1", "INBOX", "10")
    assert run(make_service(provider).get_message("a1", ref, include_body=False, include_attachments=True)) == "message"
    assert provider.calls == [("fetch_message", ref, False, True)]


def test_mark_read_delegates_and_returns_structured_result():
    provider = FakeProvider([Capability.READ_STATE])
    ref = EmailMessageRef("a1", "INBOX", "10")
    result = run(make_service(provider).mark_read("a1", ref))
    assert result.is_success
    assert provider.calls == [("mark_read", ref)]


def test_send_requires_confirmation_before_provider_call():
    provider = FakeProvider([Capability.SEND])
    with pytest.raises(PermissionError, match="Confirmation"):
        run(make_service(provider, primary=True).send("a1", object(), confirmed=False))
    assert provider.calls == []


def test_send_uses_supplied_operation_id_and_provider_result():
    provider = FakeProvider([Capability.SEND])
    result = run(make_service(provider, primary=True).send("a1", object(), confirmed=True, operation_id="op-42"))
    assert result.operation_id == "op-42"
    assert provider.calls[0][2] == "op-42"


def test_send_same_operation_and_same_payload_is_replayed_without_provider_call():
    provider = FakeProvider([Capability.SEND])
    service = make_service(provider, primary=True)
    message = {"to": ["a@example.com"], "subject": "x", "body": "y"}
    first = run(service.send("a1", message, confirmed=True, operation_id="op-1"))
    second = run(service.send("a1", message, confirmed=True, operation_id="op-1"))
    assert first == second
    assert len(provider.calls) == 1


def test_send_same_operation_with_different_payload_is_rejected():
    provider = FakeProvider([Capability.SEND])
    service = make_service(provider, primary=True)
    run(service.send("a1", {"body": "one"}, confirmed=True, operation_id="op-1"))
    with pytest.raises(ValueError, match="fingerprint"):
        run(service.send("a1", {"body": "two"}, confirmed=True, operation_id="op-1"))
    assert len(provider.calls) == 1


def test_reply_requires_capability_and_confirmation():
    provider = FakeProvider([Capability.REPLY])
    with pytest.raises(PermissionError):
        run(make_service(provider).reply("a1", {"ref": "10"}, confirmed=False))
    assert provider.calls == []


def test_reference_cannot_cross_account_boundary():
    provider = FakeProvider([Capability.FETCH])
    ref = EmailMessageRef("other", "INBOX", "10")
    with pytest.raises(ValueError, match="different account"):
        run(make_service(provider).get_message("a1", ref))


def test_disabled_account_is_rejected_before_provider_access():
    provider = FakeProvider([Capability.SEARCH])
    account = EmailAccount("a1", "generic", enabled=False)
    service = EmailService({"a1": account}, {"a1": provider})
    with pytest.raises(PermissionError, match="disabled"):
        run(service.search("a1", EmailSearchQuery(subject="x")))
    assert provider.calls == []


def test_unknown_account_is_rejected():
    service = EmailService({}, {})
    with pytest.raises(KeyError):
        run(service.search("missing", EmailSearchQuery(subject="x")))
