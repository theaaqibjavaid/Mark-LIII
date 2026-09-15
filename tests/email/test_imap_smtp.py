"""Protocol-accurate tests for the generic IMAP/SMTP provider."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.errors import InvalidRecipientError, MailboxNotFoundError, MessageNotFoundError, ProviderCapabilityError
from core.email.models import EmailAccount, EmailAddress, EmailDraft, EmailMessageRef, EmailSearchQuery, EmailServerConfig, OperationStatus
from core.email.providers.base import Capability
from core.email.providers.imap_smtp import ImapSmtpProvider


class FakeIMAP:
    """Deterministic IMAP double using the real imaplib.uid call shape."""
    def __init__(self, folders=None):
        self.folders = folders or ["INBOX", "Sent", "Drafts", "Trash", "Archive"]
        self.selected = "INBOX"
        self.calls: list[tuple] = []
        self.move_status = "OK"
        self.fetch_status = "OK"
        self.capabilities = (b"IMAP4REV1", b"UIDPLUS", b"MOVE")
        self.append_uid = 2000
        self.message = (
            b"MIME-Version: 1.0\r\nFrom: sender@example.com\r\n"
            b"To: recipient@example.com\r\nSubject: Test\r\n"
            b"Date: Mon, 1 Jan 2024 00:00:00 +0000\r\n"
            b"Message-ID: <m1@example.com>\r\n\r\nBody content"
        )

    def login(self, user, password): self.calls.append(("login", user, password)); return ("OK", [b"LOGIN"])
    def logout(self): self.calls.append(("logout",)); return ("OK", [b"BYE"])
    def starttls(self, **kwargs): self.calls.append(("starttls",)); return ("OK", [b"STARTTLS"])

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
        if mailbox not in self.folders: return ("NO", [b"[NONEXISTENT]"])
        self.selected = mailbox; return ("OK", [b"1"])

    def uid(self, command, *args):
        self.calls.append((command.lower(),) + args)
        command = command.lower()
        if command == "fetch":
            return (self.fetch_status, [] if self.fetch_status != "OK" else [(str(args[0]).encode(), (b"FLAGS (\\Seen)", self.message))])
        if command == "move": return (self.move_status, [b""])
        if command == "copy": return ("OK", [b"2001"])
        if command in {"store", "expunge"}: return ("OK", [b""])
        return ("OK", [b""])

    def uid_search(self, charset, criteria):
        self.calls.append(("uid_search", charset, criteria)); return ("OK", [b"1001 1002 1003"])

    def append(self, mailbox, flags, date_time, message):
        self.append_uid += 1; self.calls.append(("append", mailbox, flags, message)); return ("OK", [str(self.append_uid).encode()])


class FakeSMTP:
    def __init__(self): self.calls: list[tuple] = []
    def starttls(self, **kwargs): self.calls.append(("starttls",)); return (220, b"ready")
    def login(self, user, password): self.calls.append(("login", user, password)); return (235, b"ok")
    def sendmail(self, sender, recipients, message): self.calls.append(("sendmail", sender, recipients, message)); return {}
    def quit(self): self.calls.append(("quit",)); return (221, b"bye")


@pytest.fixture
def credentials():
    store = InMemoryCredentialStore(); store.set_password("imap_smtp", "user@example.com", "test-password"); return store

@pytest.fixture
def account():
    return EmailAccount("user@example.com", "imap_smtp", primary_address=EmailAddress("user@example.com"), server_config=EmailServerConfig("imap.example.com", 993, "smtp.example.com", 587, "ssl", "starttls"))

@pytest.fixture
def connected(account, credentials):
    fake = FakeIMAP(); provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake): asyncio.run(provider.connect(account, credentials))
    return provider, fake


def test_account_capabilities_are_not_server_configuration():
    account = EmailAccount("id", "imap_smtp", capabilities=["SEARCH"], server_config=EmailServerConfig("imap.example.com"))
    assert account.capabilities == ["SEARCH"]; assert account.server_config.imap_host == "imap.example.com"; assert not isinstance(account.capabilities, dict)


def test_legacy_server_configuration_is_normalized():
    account = EmailAccount("id", "imap_smtp", capabilities={"imap_server": "imap.example.com", "imap_port": 993, "smtp_server": "smtp.example.com"})
    assert account.capabilities == []; assert account.server_config.smtp_host == "smtp.example.com"


def test_connect_uses_credential_store(connected):
    provider, fake = connected
    assert provider.is_connected and provider.metadata.capabilities.supports(Capability.SEARCH)
    assert fake.calls[0] == ("login", "user@example.com", "test-password")


def test_uid_search_is_server_side(connected):
    provider, fake = connected
    refs = asyncio.run(provider.search(EmailSearchQuery(sender="sender@example.com")))
    assert refs and not any(c[0] == "search" for c in fake.calls)
    call = next(c for c in fake.calls if c[0] == "uid_search"); assert "FROM" in call[2]


def test_unsupported_search_fields_are_rejected(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search(EmailSearchQuery(thread_id="t1")))
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search(EmailSearchQuery(has_attachment=True)))


def test_fetch_uses_uid_peek(connected):
    provider, fake = connected; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.fetch_message(ref)); call = next(c for c in fake.calls if c[0] == "fetch")
    assert result.reference.uid == "1001" and call[1:] == ("1001", "BODY.PEEK[]")


def test_headers_are_header_only(connected):
    provider, fake = connected; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.fetch_message_headers(ref)); call = next(c for c in fake.calls if c[0] == "fetch")
    assert call[2] == "BODY.PEEK[HEADER]" and result.body_plain is None and result.body_html is None and result.attachments == []


def test_not_found_maps_from_imap_status(connected):
    provider, fake = connected; fake.fetch_status = "NO"
    with pytest.raises(MessageNotFoundError): asyncio.run(provider.fetch_message(EmailMessageRef("user@example.com", "INBOX", "1001")))


def test_read_state_uses_uid_store(connected):
    provider, fake = connected; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    assert asyncio.run(provider.mark_read(ref)).status is OperationStatus.SUCCESS
    assert ("store", "1001", "+FLAGS", "(\\Seen)") in fake.calls


def test_move_uses_uid_move(connected):
    provider, fake = connected; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    assert asyncio.run(provider.move_message(ref, "Archive")).is_success
    assert ("move", "1001", "Archive") in fake.calls


def test_move_fallback_is_safe(connected):
    provider, fake = connected; fake.move_status = "NO"; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.move_message(ref, "Archive"))
    assert result.is_success and ("copy", "1001", "Archive") in fake.calls and ("expunge", "1001") in fake.calls


def test_archive_requires_special_use_folder(connected):
    provider, fake = connected; fake.folders = ["INBOX", "Sent"]
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.archive_message(EmailMessageRef("user@example.com", "INBOX", "1001")))


def test_folder_info_has_no_select_side_effect(connected):
    provider, fake = connected; asyncio.run(provider.get_folder_info("Archive")); assert provider._current_folder == "INBOX"; assert not any(c[0] == "select" for c in fake.calls)


def test_drafts_require_advertised_drafts_folder(connected):
    provider, fake = connected; fake.folders = ["INBOX", "Sent"]
    with pytest.raises(MailboxNotFoundError): asyncio.run(provider.create_draft(EmailDraft(subject="draft")))


def test_send_uses_smtp_starttls_and_credentials(account, credentials):
    imap, smtp = FakeIMAP(), FakeSMTP(); provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp):
        asyncio.run(provider.connect(account, credentials)); result = asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and any(c[0] == "starttls" for c in smtp.calls) and any(c[0] == "login" for c in smtp.calls) and any(c[0] == "sendmail" for c in smtp.calls)


def test_invalid_recipient_is_rejected_before_transport(connected, account):
    provider, _ = connected
    with pytest.raises(InvalidRecipientError): asyncio.run(provider.send(account, [EmailAddress("invalid")], "Subject", "Body"))


def test_disconnect_is_idempotent(connected):
    provider, fake = connected; asyncio.run(provider.disconnect()); asyncio.run(provider.disconnect())
    assert not provider.is_connected and provider._credentials is None and provider._account is None and any(c[0] == "logout" for c in fake.calls)


def test_async_context_manager_cleans_up(connected):
    provider, fake = connected
    async def exercise():
        async with provider as entered: assert entered is provider and provider.is_connected
    asyncio.run(exercise()); assert not provider.is_connected and any(c[0] == "logout" for c in fake.calls)
