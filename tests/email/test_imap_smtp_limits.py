from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.errors import InvalidRecipientError
from core.email.models import EmailAccount, EmailAddress, EmailServerConfig
from core.email.providers.imap_smtp import ImapSmtpProvider

from tests.email.test_imap_smtp import FakeIMAP, FakeSMTP


def _account() -> EmailAccount:
    return EmailAccount(
        "user@example.com",
        "imap_smtp",
        primary_address=EmailAddress("user@example.com"),
        server_config=EmailServerConfig(
            "imap.example.com", 993, "smtp.example.com", 587, "ssl", "starttls"
        ),
    )


def _credentials() -> InMemoryCredentialStore:
    store = InMemoryCredentialStore()
    store.set_password("imap_smtp", "user@example.com", "test-password")
    return store


def test_send_rejects_recipient_count_over_limit_before_smtp():
    account, credentials = _account(), _credentials()
    provider = ImapSmtpProvider()
    imap, smtp = FakeIMAP(), FakeSMTP()
    recipients = [EmailAddress(f"user{i}@example.com") for i in range(101)]
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch(
        "core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp
    ):
        asyncio.run(provider.connect(account, credentials))
        with pytest.raises(InvalidRecipientError):
            asyncio.run(provider.send(account, recipients, "Subject", "Body"))
    assert not any(call[0] == "sendmail" for call in smtp.calls)


def test_send_rejects_oversized_subject_before_smtp():
    account, credentials = _account(), _credentials()
    provider = ImapSmtpProvider()
    imap, smtp = FakeIMAP(), FakeSMTP()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch(
        "core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp
    ):
        asyncio.run(provider.connect(account, credentials))
        with pytest.raises(ValueError):
            asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "x" * 1001, "Body"))
    assert not any(call[0] == "sendmail" for call in smtp.calls)
