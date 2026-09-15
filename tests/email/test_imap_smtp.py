"""Protocol-accurate tests for the generic IMAP/SMTP provider."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.errors import (
    AuthenticationError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
)
from core.email.models import (
    EmailAccount,
    EmailAddress,
    EmailDraft,
    EmailMessageRef,
    EmailSearchQuery,
    EmailServerConfig,
    OperationStatus,
)
from core.email.providers.base import Capability
from core.email.providers.imap_smtp import ImapSmtpProvider


class FakeIMAP:
    """Small deterministic double implementing the imaplib UID contract."""

    def __init__(self, folders=None):
        self.folders = folders or ["INBOX", "Sent", "Drafts", "Trash", "Archive"]
        self.selected = "INBOX"
        self.calls: list[tuple] = []
        self.move_status = "OK"
        self.fetch_status = "OK"
        self.capabilities = (b"IMAP4REV1", b"UIDPLUS", b"MOVE")
        self.append_uid = 2000
        self.message = (
            b"MIME-Version: 1.0\r\n"
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Test\r\n"
            b"Date: Mon, 1 Jan 2024 00:00:00 +0000\r\n"
            b"Message-ID: <m1@example.com>\r\n\r\n"
            b"Body content"
        )

    def login(self, user, password):
        self.calls.append(("login", user, password))
        return ("OK", [b"LOGIN completed"])

    def logout(self):
        self.calls.append(("logout",))
        return ("OK", [b"BYE"])

    def starttls(self, **kwargs):
        self.calls.append(("starttls",))
        return ("OK", [b"STARTTLS completed"])

    def list(self, reference="*", mask="*"):
        rows = []
        for folder in self.folders:
            flag = "\\HasNoChildren"
            if folder == "Drafts": flag = "\\Drafts \\HasNoChildren"
            elif folder == "Sent": flag = "\\Sent \\HasNoChildren"
            elif folder == "Trash": flag = "\\Trash \\HasNoChildren"
            elif folder == "Archive": flag = "\\Archive \\HasNoChildren"
            rows.append(f'({flag}) "." "{folder}"'.encode())
        return ("OK", rows)

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        if mailbox not in self.folders:
            return ("NO", [b"[NONEXISTENT]"])
        self.selected = mailbox
        return ("OK", [b"1"])

    def uid(self, command, *args):
        self.calls.append((command.lower(),) + args)
        command = command.lower()
        if command == "fetch":
            if self.fetch_status != "OK": return (self.fetch_status, [])
            return ("OK", [(str(args[0]).encode(), (b"FLAGS (\\Seen)", self.message))])
        if command == "move": return (self.move_status, [b""])
        if command == "copy": return ("OK", [b"2001"])
        if command == "expunge": return ("OK", [b""])
        if command == "store": return ("OK", [b"FLAGS (\\Flagged)"])
        return ("OK", [b""])

    def uid_search(self, charset, criteria):
        self.calls.append(("uid_search", charset, criteria))
        return ("OK", [b"1001 1002 1003"])

    def append(self, mailbox, flags, date_time, message):
        self.append_uid += 1
        self.calls.append(("append", mailbox, flags, message))
        return ("OK", [str(self.append_uid).encode()])


class FakeSMTP:
    def __init__(self):
        self.calls: list[tuple] = []

    def starttls(self, **kwargs):
        self.calls.append(("starttls",))
        return (220, b"ready")

    def login(self, user, password):
        self.calls.append(("login", user, password))
        return (235, b"authenticated")

    def sendmail(self, sender, recipients, message):
        self.calls.append(("sendmail", sender, recipients, message))
        return {}

    def quit(self):
        self.calls.append(("quit",))
        return (221, b"bye")


@pytest.fixture
def credentials():
    store = InMemoryCredentialStore()
    store.set_password("imap_smtp", "user@example.com", "test-password")
    return store


@pytest.fixture
def account():
    return EmailAccount(
        account_id="user@example.com",
        provider="imap_smtp",
        primary_address=EmailAddress("user@example.com"),
        server_config=EmailServerConfig(
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=587,
            imap_security="ssl",
            smtp_security="starttls",
        ),
    )


@pytest.fixture
def connected(account, credentials):
    fake = FakeIMAP()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake):
        asyncio.run(provider.connect(account, credentials))
    return provider, fake


def test_account_keeps_capabilities_separate_from_server_config():
    account = EmailAccount(
        "id", "imap_smtp", capabilities=["SEARCH"],
        server_config=EmailServerConfig("imap.example.com", smtp_host="smtp.example.com"),
    )
    assert account.capabilities == ["SEARCH"]
    assert account.server_config.imap_host == "imap.example.com"
    assert not isinstance(account.capabilities, dict)


def test_legacy_config_is_normalized_without_secrets():
    account = EmailAccount(
        "id", "imap_smtp",
        capabilities={"imap_server": "imap.example.com", "imap_port": 993, "smtp_server": "smtp.example.com"},
    )
    assert account.capabilities == []
    assert account.server_config.imap_host == "imap.example.com"
    assert account.server_config.smtp_host == "smtp.example.com"


def test_connect_uses_credential_store_and_never_capabilities_for_password(account, credentials):
    fake = FakeIMAP()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake):
        provider = ImapSmtpProvider()
        metadata = asyncio.run(provider.connect(account, credentials))
    assert provider.is_connected
    assert metadata.provider_type == "imap_smtp"
    assert fake.calls[0][0] == "login"
    assert fake.calls[0][2] == "test-password"
    assert Capability.SEARCH in metadata.capabilities.values


def test_uid_search_is_used_for_server_side_search(connected):
    provider, fake = connected
    refs = asyncio.run(provider.search(EmailSearchQuery(sender="sender@example.com")))
    assert [r.uid for r in refs]
    call = next(c for c in fake.calls if c[0] == "uid_search")
    assert "FROM" in call[2]
    assert not any(c[0] == "search" for c in fake.calls)


def test_unsupported_search_semantics_are_rejected(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.search(EmailSearchQuery(thread_id="thread-1")))
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.search(EmailSearchQuery(has_attachment=True)))


def test_fetch_uses_uid_and_peek(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    message = asyncio.run(provider.fetch_message(ref))
    assert message.reference.uid == "1001"
    call = next(c for c in fake.calls if c[0] == "fetch")
    assert call[1] == "1001"
    assert call[2] == "BODY.PEEK[]"


def test_fetch_headers_is_header_only_and_peek(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    message = asyncio.run(provider.fetch_message_headers(ref))
    call = next(c for c in fake.calls if c[0] == "fetch")
    assert call[2] == "BODY.PEEK[HEADER]"
    assert message.body_plain is None
    assert message.body_html is None


def test_message_not_found_maps_from_provider_status(connected):
    provider, fake = connected
    fake.fetch_status = "NO"
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    with pytest.raises(MessageNotFoundError):
        asyncio.run(provider.fetch_message(ref))


def test_mark_read_uses_uid_store(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.mark_read(ref))
    assert result.status is OperationStatus.SUCCESS
    assert ("store", "1001", "+FLAGS", "(\\Seen)") in fake.calls


def test_move_uses_uid_move(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.move_message(ref, "Archive"))
    assert result.is_success
    assert ("move", "1001", "Archive") in fake.calls


def test_move_fallback_requires_safe_uid_expunge(connected):
    provider, fake = connected
    fake.move_status = "NO"
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.move_message(ref, "Archive"))
    assert result.is_success
    assert ("copy", "1001", "Archive") in fake.calls
    assert ("expunge", "1001") in fake.calls


def test_archive_requires_advertised_archive_folder(connected):
    provider, fake = connected
    fake.folders = ["INBOX", "Sent"]
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.archive_message(ref))


def test_get_folder_info_does_not_change_selected_folder(connected):
    provider, fake = connected
    assert provider._current_folder == "INBOX"
    asyncio.run(provider.get_folder_info("Archive"))
    assert provider._current_folder == "INBOX"
    assert not any(c[0] == "select" for c in fake.calls)


def test_missing_drafts_folder_is_explicit_error(connected):
    provider, fake = connected
    fake.folders = ["INBOX", "Sent"]
    with pytest.raises(MailboxNotFoundError):
        asyncio.run(provider.create_draft(EmailDraft(subject="draft")))


def test_send_uses_smtp_tls_and_credential_store(account, credentials):
    imap = FakeIMAP()
    smtp = FakeSMTP()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), \
         patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp):
        asyncio.run(provider.connect(account, credentials))
        result = asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success
    assert any(c[0] == "starttls" for c in smtp.calls)
    assert any(c[0] == "login" for c in smtp.calls)
    assert any(c[0] == "sendmail" for c in smtp.calls)


def test_invalid_recipient_is_rejected_before_smtp(account, credentials):
    imap = FakeIMAP()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap):
        asyncio.run(provider.connect(account, credentials))
    with pytest.raises(Exception):
        asyncio.run(provider.send(account, [EmailAddress("invalid")], "Subject", "Body"))


def test_disconnect_clears_credentials_and_is_idempotent(connected):
    provider, fake = connected
    asyncio.run(provider.disconnect())
    asyncio.run(provider.disconnect())
    assert not provider.is_connected
    assert provider._credentials is None
    assert provider._account is None
    assert any(c[0] == "logout" for c in fake.calls)


def test_context_manager_cleanup(account, credentials):
    fake = FakeIMAP()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake):
        asyncio.run(provider.__aenter__())
    assert provider._state.value in {"authenticated", "connected"}
