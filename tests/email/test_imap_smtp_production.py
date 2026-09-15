"""Production-grade behavioral coverage for the generic IMAP/SMTP provider.

These tests deliberately exercise protocol behavior, failure mapping, lifecycle
invariants, MIME construction, limits, and destructive-operation safeguards.
"""
from __future__ import annotations

import asyncio
import smtplib
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.errors import (
    AuthenticationError,
    ConnectionError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
    TLSConfigurationError,
    TimeoutError as EmailTimeoutError,
)
from core.email.models import (
    EmailAccount,
    EmailAddress,
    EmailAttachment,
    EmailDraft,
    EmailMessageRef,
    EmailSearchQuery,
)
from core.email.providers.imap_smtp import ImapSmtpProvider

from tests.email.test_imap_smtp import FakeIMAP, FakeSMTP


@pytest.fixture
def credentials():
    store = InMemoryCredentialStore()
    store.set_password("imap_smtp", "user@example.com", "test-password")
    return store


@pytest.fixture
def account():
    return EmailAccount(
        "user@example.com",
        "imap_smtp",
        primary_address=EmailAddress("user@example.com"),
        server_config=None,
    )


def configured_account(**kwargs):
    from core.email.models import EmailServerConfig

    config = EmailServerConfig(
        kwargs.pop("imap_host", "imap.example.com"),
        kwargs.pop("imap_port", 993),
        kwargs.pop("smtp_host", "smtp.example.com"),
        kwargs.pop("smtp_port", 587),
        kwargs.pop("imap_security", "ssl"),
        kwargs.pop("smtp_security", "starttls"),
    )
    return EmailAccount(
        "user@example.com",
        "imap_smtp",
        primary_address=EmailAddress("user@example.com"),
        server_config=config,
        **kwargs,
    )


@pytest.fixture
def connected(account, credentials):
    fake = FakeIMAP()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake):
        asyncio.run(provider.connect(configured_account(), credentials))
    return provider, fake


def test_connect_rejects_non_positive_timeout(credentials):
    provider = ImapSmtpProvider()
    with pytest.raises(ValueError, match="timeout"):
        asyncio.run(provider.connect(configured_account(), credentials, timeout=0))


def test_connect_requires_imap_host(credentials):
    provider = ImapSmtpProvider()
    with pytest.raises(ConnectionError, match="IMAP server"):
        asyncio.run(provider.connect(configured_account(imap_host=None), credentials))
    assert not provider.is_connected


def test_connect_requires_password(credentials):
    provider = ImapSmtpProvider()
    empty = InMemoryCredentialStore()
    with pytest.raises(AuthenticationError, match="password"):
        asyncio.run(provider.connect(configured_account(), empty))
    assert not provider.is_connected


def test_connect_maps_login_failure_to_authentication_error(credentials):
    class BadLogin(FakeIMAP):
        def login(self, user, password):
            return ("NO", [b"AUTHENTICATIONFAILED"])

    fake = BadLogin()
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake):
        with pytest.raises(AuthenticationError):
            asyncio.run(provider.connect(configured_account(), credentials))
    assert not provider.is_connected


def test_connect_maps_imap_timeout(credentials):
    provider = ImapSmtpProvider()
    with patch(
        "core.email.providers.imap_smtp.IMAP4_SSL",
        side_effect=__import__("asyncio").TimeoutError("timed out"),
    ):
        with pytest.raises(EmailTimeoutError):
            asyncio.run(provider.connect(configured_account(), credentials))


def test_connect_uses_plain_imap_without_starttls(credentials):
    fake = FakeIMAP()
    provider = ImapSmtpProvider()
    account = configured_account(imap_security="plain")
    with patch("core.email.providers.imap_smtp.IMAP4", return_value=fake):
        asyncio.run(provider.connect(account, credentials))
    assert fake.calls[0][0] == "login"
    assert not any(c[0] == "starttls" for c in fake.calls)


def test_connect_uses_imap_starttls(credentials):
    fake = FakeIMAP()
    provider = ImapSmtpProvider()
    account = configured_account(imap_security="starttls")
    with patch("core.email.providers.imap_smtp.IMAP4", return_value=fake):
        asyncio.run(provider.connect(account, credentials))
    assert any(c[0] == "starttls" for c in fake.calls)


def test_connect_maps_imap_tls_failure(credentials):
    provider = ImapSmtpProvider()
    with patch(
        "core.email.providers.imap_smtp.IMAP4_SSL",
        side_effect=__import__("ssl").SSLError("bad tls"),
    ):
        with pytest.raises(TLSConfigurationError):
            asyncio.run(provider.connect(configured_account(), credentials))


def test_list_folders_maps_non_ok_status(connected):
    provider, fake = connected
    fake.list = lambda *args, **kwargs: ("NO", [b"failure"])
    with pytest.raises(ConnectionError):
        asyncio.run(provider.list_folders())


def test_select_folder_updates_current_folder(connected):
    provider, fake = connected
    asyncio.run(provider.select_folder("Archive"))
    assert provider._current_folder == "Archive"
    assert ("select", "Archive", False) in fake.calls


def test_select_folder_maps_non_ok_status(connected):
    provider, fake = connected
    fake.folders = ["INBOX"]
    with pytest.raises(MailboxNotFoundError):
        asyncio.run(provider.select_folder("Archive"))


def test_get_folder_info_unknown_folder_raises(connected):
    provider, _ = connected
    with pytest.raises(MailboxNotFoundError):
        asyncio.run(provider.get_folder_info("Missing"))


def test_search_applies_offset_and_limit(connected):
    provider, _ = connected
    query = EmailSearchQuery(offset=1, limit=1)
    refs = asyncio.run(provider.search(query))
    assert len(refs) == 1 and refs[0].uid == "1002"


def test_search_descending_reverses_server_result(connected):
    provider, _ = connected
    refs = asyncio.run(provider.search(EmailSearchQuery(sort_order="desc", limit=3)))
    assert [r.uid for r in refs] == ["1003", "1002", "1001"]


def test_search_rejects_non_default_sort_field(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.search(EmailSearchQuery(sort_by="subject")))


def test_search_restores_original_folder_after_multi_folder_search(connected):
    provider, fake = connected
    refs = asyncio.run(provider.search(EmailSearchQuery(folders=["Sent", "Archive"])))
    assert refs and provider._current_folder == "INBOX"
    selects = [c for c in fake.calls if c[0] == "select"]
    assert selects[-1] == ("select", "INBOX", False)


def test_search_maps_non_ok_status(connected):
    provider, fake = connected
    fake.uid_search = lambda charset, criteria: ("NO", [b"failure"])
    with pytest.raises(Exception):
        asyncio.run(provider.search(EmailSearchQuery()))


def test_fetch_without_body_uses_header_peek(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.fetch_message(ref, include_body=False))
    fetch = next(c for c in fake.calls if c[0] == "fetch")
    assert fetch[2] == "BODY.PEEK[HEADER]"
    assert result.body_plain is None and result.body_html is None


def test_fetch_header_only_does_not_mark_message_seen(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    asyncio.run(provider.fetch_message_headers(ref))
    assert not any(c[0] == "store" for c in fake.calls)


def test_fetch_message_requires_matching_account(connected):
    provider, _ = connected
    ref = EmailMessageRef("other@example.com", "INBOX", "1001")
    with pytest.raises(AuthorizationError):
        asyncio.run(provider.fetch_message(ref))


def test_fetch_attachments_delegates_to_full_fetch(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.fetch_attachments(ref))
    fetch = next(c for c in fake.calls if c[0] == "fetch")
    assert isinstance(result, list) and fetch[2] == "BODY.PEEK[]"


def test_mark_unread_uses_negative_seen_flag(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    asyncio.run(provider.mark_unread(ref))
    assert ("store", "1001", "-FLAGS", "(\\Seen)") in fake.calls


def test_add_flag_uses_uid_store(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    asyncio.run(provider.add_flag(ref, "\\Flagged"))
    assert ("store", "1001", "+FLAGS", "(\\Flagged)") in fake.calls


def test_remove_flag_uses_uid_store(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    asyncio.run(provider.remove_flag(ref, "\\Flagged"))
    assert ("store", "1001", "-FLAGS", "(\\Flagged)") in fake.calls


def test_delete_marks_exact_uid_deleted(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.delete_message(ref))
    assert result.is_success
    assert ("store", "1001", "+FLAGS", "(\\Deleted)") in fake.calls


def test_copy_uses_uid_copy(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    result = asyncio.run(provider.copy_message(ref, "Archive"))
    assert result.is_success and ("copy", "1001", "Archive") in fake.calls


def test_copy_failure_maps_to_connection_error(connected):
    provider, fake = connected
    original_uid = fake.uid
    def uid(command, *args):
        if command.lower() == "copy":
            fake.calls.append(("copy",) + args)
            return ("NO", [b"failure"])
        return original_uid(command, *args)
    fake.uid = uid
    with pytest.raises(ConnectionError):
        asyncio.run(provider.copy_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))


def test_move_failure_before_copy_is_not_destructive(connected):
    provider, fake = connected
    original_uid = fake.uid
    def uid(command, *args):
        if command.lower() == "move":
            fake.calls.append(("move",) + args)
            return ("NO", [b"failure"])
        if command.lower() == "copy":
            fake.calls.append(("copy",) + args)
            return ("NO", [b"failure"])
        return original_uid(command, *args)
    fake.uid = uid
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))
    assert not any(c[0] == "expunge" for c in fake.calls)


def test_move_refuses_when_uid_expunge_fails(connected):
    provider, fake = connected
    original_uid = fake.uid
    def uid(command, *args):
        if command.lower() == "move":
            fake.calls.append(("move",) + args)
            return ("NO", [b"failure"])
        if command.lower() == "expunge":
            fake.calls.append(("expunge",) + args)
            return ("NO", [b"unsupported"])
        return original_uid(command, *args)
    fake.uid = uid
    with pytest.raises(ProviderCapabilityError, match="EXPUNGE"):
        asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))


def test_archive_moves_to_advertised_archive_folder(connected):
    provider, fake = connected
    result = asyncio.run(provider.archive_message(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert result.is_success
    assert ("move", "1001", "Archive") in fake.calls


def test_thread_search_rejects_without_thread_extension(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.search_threads(EmailSearchQuery()))


def test_thread_get_rejects_without_thread_extension(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError):
        asyncio.run(provider.get_thread("thread-1"))


def test_create_draft_appends_to_special_use_folder(connected):
    provider, fake = connected
    draft = EmailDraft(subject="Draft subject", body_plain="Draft body")
    result = asyncio.run(provider.create_draft(draft))
    assert result.is_success
    append = next(c for c in fake.calls if c[0] == "append")
    assert append[1] == "Drafts" and "\\Draft" in append[2]
    parsed = BytesParser(policy=policy.default).parsebytes(append[3])
    assert parsed["Subject"] == "Draft subject"


def test_create_draft_requires_special_use_folder(connected):
    provider, fake = connected
    fake.folders = ["INBOX", "Sent"]
    with pytest.raises(MailboxNotFoundError):
        asyncio.run(provider.create_draft(EmailDraft(subject="Draft")))


def test_delete_draft_uses_same_uid_delete_path(connected):
    provider, fake = connected
    ref = EmailMessageRef("user@example.com", "Drafts", "1001")
    result = asyncio.run(provider.delete_draft(ref))
    assert result.is_success and ("store", "1001", "+FLAGS", "(\\Deleted)") in fake.calls


def test_update_draft_deletes_then_creates(connected):
    provider, fake = connected
    result = asyncio.run(provider.update_draft(
        EmailMessageRef("user@example.com", "Drafts", "1001"),
        EmailDraft(subject="Updated"),
    ))
    assert result.is_success
    assert any(c[0] == "store" and c[1] == "1001" for c in fake.calls)
    assert any(c[0] == "append" and c[1] == "Drafts" for c in fake.calls)


def test_smtp_missing_host_is_rejected(connected):
    provider, _ = connected
    account = configured_account(smtp_host=None)
    with pytest.raises(ConnectionError, match="SMTP server"):
        asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "Subject", "Body"))


def test_smtp_ssl_mode_uses_ssl_transport(credentials):
    imap, smtp = FakeIMAP(), FakeSMTP()
    provider = ImapSmtpProvider()
    account = configured_account(smtp_security="ssl", smtp_port=465)
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch(
        "core.email.providers.imap_smtp.smtplib.SMTP_SSL", return_value=smtp
    ):
        asyncio.run(provider.connect(account, credentials))
        result = asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and not any(c[0] == "starttls" for c in smtp.calls)


def test_smtp_plain_mode_does_not_start_tls(credentials):
    imap, smtp = FakeIMAP(), FakeSMTP()
    provider = ImapSmtpProvider()
    account = configured_account(smtp_security="plain")
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch(
        "core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp
    ):
        asyncio.run(provider.connect(account, credentials))
        result = asyncio.run(provider.send(account, [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and not any(c[0] == "starttls" for c in smtp.calls)


def test_smtp_authentication_failure_is_mapped(credentials):
    imap = FakeIMAP()
    class BadSMTP(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad auth")
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=imap), patch(
        "core.email.providers.imap_smtp.smtplib.SMTP", return_value=BadSMTP()
    ):
        asyncio.run(provider.connect(configured_account(), credentials))
        with pytest.raises(AuthenticationError):
            asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject", "Body"))


def test_smtp_recipient_refusal_is_mapped(connected):
    provider, _ = connected
    class RefusingSMTP(FakeSMTP):
        def sendmail(self, sender, recipients, message):
            raise smtplib.SMTPRecipientsRefused({"to@example.com": (550, b"no")})
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=RefusingSMTP()):
        with pytest.raises(InvalidRecipientError):
            asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject", "Body"))


def test_smtp_generic_failure_is_mapped(connected):
    provider, _ = connected
    class BrokenSMTP(FakeSMTP):
        def sendmail(self, sender, recipients, message):
            raise smtplib.SMTPException("temporary protocol failure")
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=BrokenSMTP()):
        with pytest.raises(ConnectionError):
            asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject", "Body"))


def test_send_supports_cc_bcc_and_reply_to(connected):
    provider, _ = connected
    smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp):
        result = asyncio.run(provider.send(
            configured_account(),
            [EmailAddress("to@example.com")],
            "Subject",
            "Body",
            cc=[EmailAddress("cc@example.com")],
            bcc=[EmailAddress("bcc@example.com")],
            reply_to=EmailAddress("reply@example.com"),
        ))
    assert result.is_success
    send = next(c for c in smtp.calls if c[0] == "sendmail")
    assert send[2] == ["to@example.com", "cc@example.com", "bcc@example.com"]
    mime = BytesParser(policy=policy.default).parsebytes(send[3].encode())
    assert mime["Cc"] == "cc@example.com" and mime["Reply-To"] == "reply@example.com"


def test_send_with_html_body_creates_alternative(connected):
    provider, _ = connected
    smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp):
        result = asyncio.run(provider.send(
            configured_account(), [EmailAddress("to@example.com")], "Subject", "plain", "<b>html</b>"
        ))
    assert result.is_success
    send = next(c for c in smtp.calls if c[0] == "sendmail")
    mime = BytesParser(policy=policy.default).parsebytes(send[3].encode())
    assert mime.is_multipart() and mime.get_body(preferencelist=("html",)) is not None


def test_send_rejects_empty_recipients_before_smtp(connected):
    provider, _ = connected
    with pytest.raises(InvalidRecipientError):
        asyncio.run(provider.send(configured_account(), [], "Subject", "Body"))


def test_send_rejects_missing_body_content_before_smtp(connected):
    provider, _ = connected
    with pytest.raises(ValueError):
        asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject"))


def test_send_rejects_attachment_count_before_smtp(connected):
    provider, _ = connected
    attachments = [EmailAttachment(str(i), f"f{i}.txt", 1, b"x") for i in range(11)]
    with pytest.raises(Exception):
        asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject", "Body", attachments))


def test_send_rejects_single_oversized_attachment_before_smtp(connected):
    provider, _ = connected
    attachment = EmailAttachment("1", "large.bin", 26 * 1024 * 1024, b"x")
    with pytest.raises(Exception):
        asyncio.run(provider.send(configured_account(), [EmailAddress("to@example.com")], "Subject", "Body", [attachment]))


def test_disconnect_cleans_up_after_smtp_quit_failure(connected):
    provider, _ = connected
    class BadSMTP(FakeSMTP):
        def quit(self):
            raise OSError("socket closed")
    smtp = BadSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp):
        asyncio.run(provider._connect_smtp(configured_account()))
    asyncio.run(provider.disconnect())
    assert not provider.is_connected and provider._smtp is None and provider._imap is None


def test_disconnect_cleans_up_after_imap_logout_failure(connected):
    provider, fake = connected
    fake.logout = lambda: (_ for _ in ()).throw(OSError("socket closed"))
    asyncio.run(provider.disconnect())
    assert not provider.is_connected and provider._imap is None


def test_cleanup_clears_credentials_after_failed_connect(credentials):
    provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=OSError("network down")):
        with pytest.raises(ConnectionError):
            asyncio.run(provider.connect(configured_account(), credentials))
    assert provider._credentials is None and provider._account is None
