from dataclasses import dataclass

import pytest

from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailOperationResult, EmailSearchQuery, OperationStatus
from core.email.policy import OperationCategory
from core.email.service import EmailService
from core.email.errors import ProviderCapabilityError
from core.email.providers.base import Capability, ProviderCapabilities


class FakeProvider:
    def __init__(self, capabilities=None):
        self.calls = []
        self._capabilities = ProviderCapabilities(capabilities or list(Capability))
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

    async def add_flag(self, ref, flag):
        self.calls.append(("add_flag", ref, flag))
        return EmailOperationResult("op", OperationStatus.SUCCESS, [ref])

    async def send(self, message, operation_id):
        self.calls.append(("send", message, operation_id))
        return EmailOperationResult(operation_id, OperationStatus.SUCCESS)


@pytest.mark.asyncio
async def test_search_normalizes_query_and_delegates_without_provider_syntax():
    provider = FakeProvider()
    service = EmailService({"a1": EmailAccount("a1", "generic")}, {"a1": provider})
    result = await service.search("a1", EmailSearchQuery(subject="invoice", limit=2))
    assert result == [EmailMessageRef("a1", "INBOX", "10")]
    assert provider.calls[0][0] == "search"
    assert provider.calls[0][1].subject == "invoice"


@pytest.mark.asyncio
async def test_search_rejects_missing_capability_before_provider_call():
    provider = FakeProvider([])
    service = EmailService({"a1": EmailAccount("a1", "generic")}, {"a1": provider})
    with pytest.raises(ProviderCapabilityError):
        await service.search("a1", EmailSearchQuery(subject="invoice"))
    assert provider.calls == []


@pytest.mark.asyncio
async def test_get_message_enforces_fetch_capability_and_arguments():
    provider = FakeProvider([Capability.FETCH])
    service = EmailService({"a1": EmailAccount("a1", "generic")}, {"a1": provider})
    ref = EmailMessageRef("a1", "INBOX", "10")
    assert await service.get_message("a1", ref, include_body=False, include_attachments=True) == "message"
    assert provider.calls == [("fetch_message", ref, False, True)]


@pytest.mark.asyncio
async def test_mark_read_delegates_and_returns_structured_result():
    provider = FakeProvider([Capability.READ_STATE])
    service = EmailService({"a1": EmailAccount("a1", "generic")}, {"a1": provider})
    ref = EmailMessageRef("a1", "INBOX", "10")
    result = await service.mark_read("a1", ref)
    assert result.is_success
    assert provider.calls == [("mark_read", ref)]


@pytest.mark.asyncio
async def test_send_requires_confirmation_callback():
    provider = FakeProvider([Capability.SEND])
    service = EmailService({"a1": EmailAccount("a1", "generic", primary_address=EmailAddress("me@example.com"))}, {"a1": provider})
    with pytest.raises(PermissionError):
        await service.send("a1", object(), confirmed=False)
    assert provider.calls == []


@pytest.mark.asyncio
async def test_send_uses_supplied_operation_id_and_provider_result():
    provider = FakeProvider([Capability.SEND])
    service = EmailService({"a1": EmailAccount("a1", "generic", primary_address=EmailAddress("me@example.com"))}, {"a1": provider})
    result = await service.send("a1", object(), confirmed=True, operation_id="op-42")
    assert result.operation_id == "op-42"
    assert provider.calls[0][2] == "op-42"


@pytest.mark.asyncio
async def test_unknown_account_is_rejected():
    service = EmailService({}, {})
    with pytest.raises(KeyError):
        await service.search("missing", EmailSearchQuery(subject="x"))
