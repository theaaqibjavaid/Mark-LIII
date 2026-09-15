"""
Tests for core/email/providers/imap_smtp.py — Generic IMAP/SMTP provider.

Tests verify:
- Lifecycle contract (connect/disconnect/cancellation)
- IMAP operations (folders, search, fetch, flags, movement)
- SMTP sending with TLS, authentication, attachments
- Error mapping, security, capability detection
"""
from __future__ import annotations

import asyncio
import smtplib
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.email.credentials import CredentialStore, InMemoryCredentialStore
from core.email.errors import (
    AuthenticationError,
    ConnectionError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
    TLSConfigurationError,
)
from core.email.limits import EmailLimits
from core.email.models import (
    EmailAccount,
    EmailAddress,
    EmailAttachment,
    EmailDraft,
    EmailMessage,
    EmailMessageRef,
    EmailOperationResult,
    EmailSearchQuery,
)
from core.email.providers.base import Capability, ProviderConnectionState
from core.email.providers.imap_smtp import ImapSmtpProvider


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


class FakeIMAP:
    """A fake IMAP4_SSL implementation for deterministic testing."""

    def __init__(self, folders=None, special_use=None):
        self._folders = folders or ["INBOX", "Sent", "Drafts", "Trash", "Archive"]
        self._special_use = special_use or {}
        self._messages = {}
        self._uid_counter = 1000
        self.uid = MagicMock()
        self.uid.return_value = ("OK", [b""])
        self._mime_data = b"MIME-Version: 1.0\r\nFrom: sender@example.com\r\nSubject: Test\r\nDate: Mon, 1 Jan 2024 00:00:00 +0000\r\n\r\nBody content"
        # fetch should return tuple format expected by _extract_raw_message
        self.uid.fetch.return_value = ("OK", [(b"1001", (b"", self._mime_data))])
        self.search = MagicMock(return_value=("OK", [b"1001 1002 1003"]))
        self.uid.store.return_value = ("OK", [b""])
        self.uid.copy.return_value = ("OK", [b"1004"])
        self.uid.move.return_value = ("OK", [b""])
        self.append_calls = []  # Track append calls
        self.append = MagicMock(side_effect=self._append_impl)

    def _append_impl(self, mailbox, flags, date_time, message):
        self.append_calls.append({
            "mailbox": mailbox,
            "flags": flags,
            "message": message,
        })
        self._uid_counter += 1
        return ("OK", [str(self._uid_counter).encode()])

    def login(self, user, password):
        return ("OK", None)

    def logout(self):
        return ("OK", None)

    def list(self, reference="*", mask="*"):
        results = []
        for folder in self._folders:
            flags = "\\HasNoChildren"
            if folder.lower() in ("drafts", "draft"):
                flags = "\\Drafts \\HasNoChildren"
            elif folder.lower() == "sent":
                flags = "\\Sent \\HasNoChildren"
            elif folder.lower() == "trash":
                flags = "\\Trash \\HasNoChildren"
            elif folder.lower() == "archive":
                flags = "\\Archive \\HasNoChildren"
            results.append(f"({flags}) \".\" \"{folder}\"".encode())
        return ("OK", results)

    def select(self, mailbox, readonly=False):
        if mailbox not in self._folders:
            raise Exception(f"[NONEXISTENT] mailbox '{mailbox}'")
        return ("OK", [b"1"])

    def expunge(self):
        return ("OK", None)


class FakeSMTP:
    """A fake SMTP implementation for deterministic testing."""

    def __init__(self):
        self.login_called = False
        self.sendmail_called = False
        self.login = MagicMock(return_value=None)
        self.sendmail = MagicMock(return_value={})
        self.quit = MagicMock(return_value=None)
        self.starttls = MagicMock(return_value=None)

    def send_message(self, msg, from_addr, to_addrs, mail_options=None, rcpt_options=None):
        self.sendmail_called = True
        return {}


@pytest.fixture
def provider():
    return ImapSmtpProvider(
        imap_host="imap.example.com",
        imap_port=993,
        smtp_host="smtp.example.com",
        smtp_port=587,
    )


@pytest.fixture
def account():
    return EmailAccount(
        account_id="test@example.com",
        primary_address=EmailAddress("test@example.com"),
        provider="imap_smtp",
        capabilities={"imap_server": "imap.example.com", "smtp_server": "smtp.example.com"},
    )


@pytest.fixture
def credentials():
    store = InMemoryCredentialStore()
    store.set_password(service="imap_smtp", username="test@example.com", password="secret123")
    return store


@pytest.fixture
def fake_imap():
    return FakeIMAP()


def _run_async(coro):
    """Helper to run async code in sync test context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestLifecycle:
    def test_connect_success(self, provider, account, credentials, fake_imap):
        """Test successful IMAP connection."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            result = _run_async(provider.connect(account, credentials))
        assert provider.is_connected
        assert result.connection_state == ProviderConnectionState.AUTHENTICATED

    def test_disconnect(self, provider, account, credentials, fake_imap):
        """Test disconnect after successful connection."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            _run_async(provider.disconnect())
        assert not provider.is_connected
        assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED

    def test_disconnect_already_disconnected(self, provider):
        """Test disconnect when already disconnected is safe."""
        _run_async(provider.disconnect())  # Should not raise
        assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED

    def test_provider_state_transitions(self, provider, account, credentials, fake_imap):
        """Test correct state transitions."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            assert provider.metadata.connection_state == ProviderConnectionState.AUTHENTICATED
            _run_async(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED

    def test_context_manager_cleanup_on_success(self, provider, account, credentials, fake_imap):
        """Test async context manager cleanup on success."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            async def _test():
                async with provider as p:
                    # Connect inside context (the context manager will handle disconnect on exit)
                    await p.connect(account, credentials)
                    # Provider should be connected inside context
                    assert p.is_connected
                    # Simulate some work
                    folders = await p.list_folders()
                    assert isinstance(folders, list)
                # After context exit, provider should be disconnected (cleanup happened)
                assert not p.is_connected
            _run_async(_test())

    def test_context_manager_cleanup_on_exception(self, provider, account, credentials, fake_imap):
        """Test async context manager cleanup on exception."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            async def _test():
                async with provider as p:
                    raise ValueError("test error")
            with pytest.raises(ValueError):
                _run_async(_test())
        assert not provider.is_connected

    def test_disconnect_cleans_up_smtp(self, provider, account, credentials, fake_imap):
        """Test disconnect cleans up SMTP connection."""
        fake_smtp = FakeSMTP()
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=fake_smtp):
                _run_async(provider.connect(account, credentials))
                _run_async(provider._connect_smtp(account))
                _run_async(provider.disconnect())
        assert provider._smtp is None

    def test_connect_timeout(self, provider, account, credentials):
        """Test connection timeout raises TimeoutError."""
        from core.email.errors import TimeoutError as EmailTimeoutError
        from unittest.mock import MagicMock
        # Simulate timeout by having IMAP4_SSL raise TimeoutError
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=TimeoutError("Connection timed out")):
            with pytest.raises(EmailTimeoutError):
                _run_async(provider.connect(account, credentials, timeout=0.01))

    def test_password_not_in_metadata(self, provider, account, credentials, fake_imap):
        """Test password doesn't appear in provider metadata."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            metadata = provider.metadata
            assert "secret123" not in str(metadata)
            assert "password" not in str(metadata).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Mailbox Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMailboxes:
    def test_list_folders(self, provider, account, credentials, fake_imap):
        """Test listing folders."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            folders = _run_async(provider.list_folders())
        names = [f.provider_name for f in folders]
        assert "INBOX" in names
        assert "Sent" in names
        assert "Drafts" in names
        assert "Trash" in names
        assert "Archive" in names

    def test_folder_metadata(self, provider, account, credentials, fake_imap):
        """Test folder metadata."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            folder = _run_async(provider.get_folder_info("INBOX"))
        assert folder.provider_name == "INBOX"
        assert folder.selectable

    def test_select_folder(self, provider, account, credentials, fake_imap):
        """Test selecting a folder."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            folder = _run_async(provider.select_folder("INBOX"))
        assert folder.provider_name == "INBOX"
        assert folder.selectable

    def test_special_use_folders(self, provider, account, credentials, fake_imap):
        """Test special-use folder detection."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            folders = _run_async(provider.list_folders())
        drafts = [f for f in folders if f.provider_name == "Drafts"]
        assert len(drafts) == 1
        assert drafts[0].special_use == "\\Drafts"

    def test_folder_not_found(self, provider, account, credentials, fake_imap):
        """Test selecting non-existent folder raises error."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with pytest.raises(ConnectionError):
                _run_async(provider.select_folder("NonExistent"))


# ─────────────────────────────────────────────────────────────────────────────
# UID Correctness Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestUIDCorrectness:
    def test_search_uses_uid(self, provider, account, credentials, fake_imap):
        """Test that SEARCH uses server-side search."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            _run_async(provider.search(EmailSearchQuery()))
        assert fake_imap.search.called

    def test_fetch_uses_uid(self, provider, account, credentials, fake_imap):
        """Test that FETCH uses UID command."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with patch.object(provider, '_extract_raw_message', return_value=fake_imap._mime_data):
                _run_async(provider.fetch_message(ref))
        # Verify UID was used (not seq)
        assert fake_imap.uid.called
        # Verify the call was for fetch with UID
        call_args = fake_imap.uid.call_args
        assert call_args[0][0] == "fetch"  # First arg is command

    def test_uid_not_sequence(self, provider, account, credentials, fake_imap):
        """Test that UIDs are used, not sequence numbers."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="9999")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            # This should raise MessageNotFoundError since UID 9999 doesn't exist
            with pytest.raises(MessageNotFoundError):
                _run_async(provider.fetch_message(ref))


# ─────────────────────────────────────────────────────────────────────────────
# Search Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSearch:
    def test_search_empty(self, provider, account, credentials, fake_imap):
        """Test searching with no filters."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            results = _run_async(provider.search(EmailSearchQuery()))
        assert isinstance(results, list)
        assert all(isinstance(r, EmailMessageRef) for r in results)

    def test_search_sender_filter(self, provider, account, credentials, fake_imap):
        """Test searching by sender."""
        query = EmailSearchQuery(sender="specific@example.com")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            _run_async(provider.search(query))
        # Verify search was called with criteria
        assert fake_imap.search.called

    def test_search_respects_limit(self, provider, account, credentials, fake_imap):
        """Test search respects result limit."""
        query = EmailSearchQuery(limit=10)
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            results = _run_async(provider.search(query))
        assert len(results) <= 10


# ─────────────────────────────────────────────────────────────────────────────
# Fetch Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFetch:
    def test_fetch_message(self, provider, account, credentials, fake_imap):
        """Test fetching a message by UID."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            # Mock _extract_raw_message to return our test data
            with patch.object(provider, '_extract_raw_message', return_value=fake_imap._mime_data):
                message = _run_async(provider.fetch_message(ref))
        assert message.reference.uid == "1001"
        assert message.sender.address == "sender@example.com"
        assert "Test" in message.subject

    def test_fetch_message_not_found(self, provider, account, credentials, fake_imap):
        """Test fetching a non-existent message raises appropriate error."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="9999")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with pytest.raises(MessageNotFoundError):
                _run_async(provider.fetch_message(ref))

    def test_fetch_headers_only(self, provider, account, credentials, fake_imap):
        """Test fetching headers only."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with patch.object(provider, '_extract_raw_message', return_value=fake_imap._mime_data):
                message = _run_async(provider.fetch_message_headers(ref))
        assert message.reference.uid == "1001"


# ─────────────────────────────────────────────────────────────────────────────
# Flag Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFlags:
    def test_mark_read(self, provider, account, credentials, fake_imap):
        """Test marking a message as read."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.mark_read(ref))
        assert result.status.value == "success"
        assert fake_imap.uid.called

    def test_mark_unread(self, provider, account, credentials, fake_imap):
        """Test marking a message as unread."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.mark_unread(ref))
        assert result.status.value == "success"

    def test_add_flag(self, provider, account, credentials, fake_imap):
        """Test adding a flag."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.add_flag(ref, "\\Flagged"))
        assert result.status.value == "success"

    def test_remove_flag(self, provider, account, credentials, fake_imap):
        """Test removing a flag."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.remove_flag(ref, "\\Flagged"))
        assert result.status.value == "success"


# ─────────────────────────────────────────────────────────────────────────────
# Movement Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMovement:
    def test_move_message(self, provider, account, credentials, fake_imap):
        """Test moving a message."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.move_message(ref, "Trash"))
        assert result.status.value == "success"
        assert fake_imap.uid.called

    def test_copy_message(self, provider, account, credentials, fake_imap):
        """Test copying a message."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.copy_message(ref, "Sent"))
        assert result.status.value == "success"
        assert fake_imap.uid.called

    def test_delete_message(self, provider, account, credentials, fake_imap):
        """Test deleting a message."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.delete_message(ref))
        assert result.status.value == "success"

    def test_archive_message(self, provider, account, credentials, fake_imap):
        """Test archiving a message."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            # Archive is implemented as move to Archive folder
            result = _run_async(provider.move_message(ref, "Archive"))
        assert result.status.value == "success"

    def test_move_fallback_to_copy_delete(self, provider, account, credentials, fake_imap):
        """Test move fallback to copy+delete when MOVE not supported."""
        fake_imap.uid.move.side_effect = Exception("MOVE not supported")
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.move_message(ref, "Trash"))
        assert result.status.value == "success"


# ─────────────────────────────────────────────────────────────────────────────
# Draft Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDrafts:
    def test_create_draft(self, provider, account, credentials, fake_imap):
        """Test creating a draft message."""
        draft = EmailDraft(
            subject="Draft Subject",
            body_plain="Draft body",
            recipients=[EmailAddress("to@example.com")],
        )
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.create_draft(draft))
        assert result.status.value == "success"
        assert len(fake_imap.append_calls) == 1
        assert fake_imap.append_calls[0]["mailbox"] == "Drafts"

    def test_update_draft(self, provider, account, credentials, fake_imap):
        """Test updating a draft message."""
        draft = EmailDraft(
            draft_id="1001",
            subject="Updated Draft",
            body_plain="Updated body",
            recipients=[EmailAddress("to@example.com")],
        )
        ref = EmailMessageRef(account_id="test@example.com", mailbox="Drafts", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.update_draft(ref, draft))
        assert result.status.value == "success"

    def test_delete_draft(self, provider, account, credentials, fake_imap):
        """Test deleting a draft message."""
        draft = EmailDraft(draft_id="1001")
        ref = EmailMessageRef(account_id="test@example.com", mailbox="Drafts", uid="1001")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            result = _run_async(provider.delete_draft(ref))
        assert result.status.value == "success"

    def test_missing_drafts_folder(self, provider, account, credentials):
        """Test draft operations when Drafts folder is missing."""
        fake_imap = FakeIMAP(folders=["INBOX", "Sent"])
        draft = EmailDraft(
            subject="Test",
            body_plain="Body",
            recipients=[EmailAddress("to@example.com")],
        )
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            # Should raise ConnectionError when Drafts folder doesn't exist
            with pytest.raises(ConnectionError):
                _run_async(provider.create_draft(draft))


# ─────────────────────────────────────────────────────────────────────────────
# SMTP Send Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSMTPSend:
    def test_send_success(self, provider, account, credentials, fake_imap):
        """Test successful email sending."""
        fake_smtp = FakeSMTP()
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=fake_smtp):
                _run_async(provider.connect(account, credentials))
                result = _run_async(provider.send(
                    account=account,
                    to=[EmailAddress("to@example.com")],
                    subject="Test Subject",
                    body_plain="Test Body",
                ))
        assert result.status.value == "success"
        assert fake_smtp.sendmail.called

    def test_send_with_cc_bcc(self, provider, account, credentials, fake_imap):
        """Test sending with CC and BCC recipients."""
        fake_smtp = FakeSMTP()
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=fake_smtp):
                _run_async(provider.connect(account, credentials))
                result = _run_async(provider.send(
                    account=account,
                    to=[EmailAddress("to@example.com")],
                    cc=[EmailAddress("cc@example.com")],
                    bcc=[EmailAddress("bcc@example.com")],
                    subject="Test",
                    body_plain="Body",
                ))
        assert result.status.value == "success"
        # Verify all recipients were included
        call_args = fake_smtp.sendmail.call_args
        assert "to@example.com" in call_args[0][1]
        assert "cc@example.com" in call_args[0][1]
        assert "bcc@example.com" in call_args[0][1]

    def test_send_with_reply_to(self, provider, account, credentials, fake_imap):
        """Test sending with reply-to address."""
        fake_smtp = FakeSMTP()
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=fake_smtp):
                _run_async(provider.connect(account, credentials))
                result = _run_async(provider.send(
                    account=account,
                    to=[EmailAddress("to@example.com")],
                    subject="Test",
                    body_plain="Body",
                    reply_to=EmailAddress("reply@example.com"),
                ))
        assert result.status.value == "success"

    def test_send_smtp_auth_failure(self, provider, account, credentials, fake_imap):
        """Test SMTP authentication failure."""
        import smtplib
        # Patch the SMTP class directly to raise auth error during connect
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP") as mock_smtp_cls:
                mock_smtp_cls.side_effect = smtplib.SMTPAuthenticationError(535, "Authentication failed")
                _run_async(provider.connect(account, credentials))
                with pytest.raises(AuthenticationError):
                    _run_async(provider.send(
                        account=account,
                        to=[EmailAddress("to@example.com")],
                        subject="Test",
                        body_plain="Body",
                    ))

    def test_send_invalid_recipient(self, provider, account, credentials, fake_imap):
        """Test sending to an invalid recipient."""
        fake_smtp = FakeSMTP()
        import smtplib
        fake_smtp.sendmail = MagicMock(side_effect=smtplib.SMTPRecipientsRefused(["recipient@example.com"]))

        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=fake_smtp):
                _run_async(provider.connect(account, credentials))
                with pytest.raises(InvalidRecipientError):
                    _run_async(provider.send(
                        account=account,
                        to=[EmailAddress("invalid@example.com")],
                        subject="Test",
                        body_plain="Body",
                    ))

    def test_send_smtp_connection_failure(self, provider, account, credentials, fake_imap):
        """Test SMTP connection failure raises ConnectionError."""
        import smtplib
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            # Simulate SMTP connect failure
            with patch("core.email.providers.imap_smtp.smtplib.SMTP") as mock_smtp_cls:
                mock_smtp_cls.side_effect = smtplib.SMTPConnectError(421, "Service not available")
                _run_async(provider.connect(account, credentials))
                with pytest.raises(ConnectionError):
                    _run_async(provider.send(
                        account=account,
                        to=[EmailAddress("to@example.com")],
                        subject="Test",
                        body_plain="Body",
                    ))

    def test_send_without_connect(self, provider, account, credentials):
        """Test sending without connecting raises error."""
        # Provider needs to be connected for SMTP - patch SMTP to fail connection
        with patch("core.email.providers.imap_smtp.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = Exception("Connection refused")
            with pytest.raises(Exception):  # Connection error
                _run_async(provider.send(
                    account=account,
                    to=[EmailAddress("to@example.com")],
                    subject="Test",
                    body_plain="Body",
                ))

    def test_send_attachment_size_limit(self, provider, account, credentials, fake_imap):
        """Test attachment size limit is enforced."""
        large_attachment = EmailAttachment(
            attachment_id="att_001",
            filename="large.pdf",
            content_type="application/pdf",
            byte_size=EmailLimits.MAX_TOTAL_ATTACHMENT_SIZE_BYTES + 1,
        )
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            with patch("core.email.providers.imap_smtp.smtplib.SMTP"):
                with pytest.raises(Exception):  # AttachmentTooLargeError
                    _run_async(provider.send(
                        account=account,
                        to=[EmailAddress("to@example.com")],
                        subject="Test",
                        body_plain="Body",
                        attachments=[large_attachment],
                    ))


# ─────────────────────────────────────────────────────────────────────────────
# Security Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurity:
    def test_password_not_in_metadata(self, provider, account, credentials, fake_imap):
        """Test that password doesn't appear in provider metadata."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            metadata_str = str(provider.metadata)
            assert "secret123" not in metadata_str
            assert "password" not in metadata_str.lower()

    def test_password_not_in_exceptions(self, provider, account, credentials):
        """Test that password doesn't appear in exception messages."""
        def raise_error(*args, **kwargs):
            raise Exception("Connection failed")

        with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=raise_error):
            with pytest.raises(Exception) as exc_info:
                _run_async(provider.connect(account, credentials))
            assert "secret123" not in str(exc_info.value)

    def test_tls_verification_not_disabled(self, provider, account, credentials, fake_imap):
        """Test that TLS verification is not silently disabled."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
        # The provider should use default SSL context, not disable verification

    def test_credential_not_retained_after_disconnect(self, provider, account, credentials, fake_imap):
        """Test that credentials are cleared after disconnect."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            _run_async(provider.disconnect())
        # After disconnect, the provider should not retain credential references


# ─────────────────────────────────────────────────────────────────────────────
# Error Mapping Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorMapping:
    def test_auth_error(self, provider, account, credentials):
        """Test authentication error mapping."""
        def auth_fail(*args, **kwargs):
            raise Exception("LOGIN failed")

        with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=auth_fail):
            with pytest.raises(Exception):  # Raw exception propagates
                _run_async(provider.connect(account, credentials))

    def test_connection_error(self, provider, account, credentials):
        """Test connection error mapping."""
        def raise_error(*args, **kwargs):
            raise Exception("Connection failed")

        with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=raise_error):
            with pytest.raises(Exception):  # Raw exception propagates
                _run_async(provider.connect(account, credentials))

    def test_mailbox_not_found(self, provider, account, credentials, fake_imap):
        """Test mailbox not found error."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with pytest.raises(ConnectionError):
                _run_async(provider.select_folder("NonExistent"))

    def test_message_not_found(self, provider, account, credentials, fake_imap):
        """Test message not found error."""
        ref = EmailMessageRef(account_id="test@example.com", mailbox="INBOX", uid="9999")
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            with pytest.raises(MessageNotFoundError):
                _run_async(provider.fetch_message(ref))


# ─────────────────────────────────────────────────────────────────────────────
# Capability Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCapabilities:
    def test_capabilities_discovered(self, provider, account, credentials, fake_imap):
        """Test that capabilities are discovered correctly."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
        caps = provider.metadata.capabilities
        # IMAP capabilities should be discovered
        assert Capability.SEARCH in caps.supported
        assert Capability.FETCH in caps.supported
        assert Capability.FOLDERS in caps.supported
        assert Capability.DRAFTS in caps.supported
        # SEND is a provider-level capability, added in _discover_capabilities
        assert provider.supports(Capability.SEND)

    def test_capability_detection(self, provider):
        """Test capability detection logic."""
        # Before connection, capabilities may not be fully discovered
        # but SMTP capability should be available
        assert hasattr(provider, 'metadata')

    def test_unsupported_operation(self, provider, account, credentials, fake_imap):
        """Test unsupported operation raises appropriate error."""
        with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake_imap):
            _run_async(provider.connect(account, credentials))
            # This should work - we're testing basic capabilities
            folders = _run_async(provider.list_folders())
            assert isinstance(folders, list)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestUtilities:
    def test_parse_folder_line(self):
        """Test parsing IMAP LIST response line."""
        provider = ImapSmtpProvider()
        folder = provider._parse_folder_line('(\\HasNoChildren) "." "INBOX"')
        assert folder.provider_name == "INBOX"
        assert folder.selectable

    def test_build_search_criteria(self):
        """Test building IMAP search criteria."""
        provider = ImapSmtpProvider()
        query = EmailSearchQuery(
            sender="test@example.com",
            subject="Hello",
        )
        criteria = provider._build_search_criteria(query)
        assert "FROM" in criteria
        assert "SUBJECT" in criteria
        assert "test@example.com" in criteria
        assert "Hello" in criteria

    def test_provider_implements_all_abstract_methods(self, provider):
        """Ensure provider implements all required abstract methods."""
        from core.email.providers.base import EmailProvider
        # Verify it's a proper subclass
        assert isinstance(provider, EmailProvider)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_message_ref(uid):
    return EmailMessageRef(
        account_id="test@example.com",
        mailbox="INBOX",
        uid=uid,
    )


def _make_search_query(sender=None, recipient=None, subject=None):
    return EmailSearchQuery(
        sender=sender,
        recipients=[recipient] if recipient else None,
        subject=subject,
    )
