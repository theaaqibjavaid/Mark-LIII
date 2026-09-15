"""Production-grade behavioral tests for the generic IMAP/SMTP provider."""
from __future__ import annotations

import asyncio
import smtplib
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.errors import AuthenticationError, AuthorizationError, ConnectionError, InvalidRecipientError, MailboxNotFoundError, MessageNotFoundError, ProviderCapabilityError, TLSConfigurationError, TimeoutError as EmailTimeoutError
from core.email.models import EmailAccount, EmailAddress, EmailAttachment, EmailDraft, EmailMessageRef, EmailSearchQuery, EmailServerConfig
from core.email.providers.imap_smtp import ImapSmtpProvider
from tests.email.test_imap_smtp import FakeIMAP, FakeSMTP


def account(**kw):
    cfg = EmailServerConfig(kw.pop("imap_host", "imap.example.com"), kw.pop("imap_port", 993), kw.pop("smtp_host", "smtp.example.com"), kw.pop("smtp_port", 587), kw.pop("imap_security", "ssl"), kw.pop("smtp_security", "starttls"))
    return EmailAccount("user@example.com", "imap_smtp", primary_address=EmailAddress("user@example.com"), server_config=cfg, **kw)


def creds():
    store = InMemoryCredentialStore(); store.set_password("imap_smtp", "user@example.com", "test-password"); return store


@pytest.fixture
def connected():
    fake = FakeIMAP(); provider = ImapSmtpProvider()
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=fake): asyncio.run(provider.connect(account(), creds()))
    return provider, fake


def test_connect_rejects_non_positive_timeout():
    with pytest.raises(ValueError): asyncio.run(ImapSmtpProvider().connect(account(), creds(), timeout=0))


def test_connect_requires_password():
    with pytest.raises(AuthenticationError): asyncio.run(ImapSmtpProvider().connect(account(), InMemoryCredentialStore()))


def test_connect_maps_login_failure():
    class Bad(FakeIMAP):
        def login(self, user, password): return ("NO", [b"AUTHENTICATIONFAILED"])
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", return_value=Bad()):
        with pytest.raises(AuthenticationError): asyncio.run(ImapSmtpProvider().connect(account(), creds()))


def test_connect_maps_timeout():
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=asyncio.TimeoutError("timed out")):
        with pytest.raises(EmailTimeoutError): asyncio.run(ImapSmtpProvider().connect(account(), creds()))


def test_connect_uses_plain_imap_without_starttls():
    fake = FakeIMAP()
    with patch("core.email.providers.imap_smtp.IMAP4", return_value=fake): asyncio.run(ImapSmtpProvider().connect(account(imap_security="plain"), creds()))
    assert not any(c[0] == "starttls" for c in fake.calls)


def test_connect_uses_imap_starttls():
    fake = FakeIMAP()
    with patch("core.email.providers.imap_smtp.IMAP4", return_value=fake): asyncio.run(ImapSmtpProvider().connect(account(imap_security="starttls"), creds()))
    assert any(c[0] == "starttls" for c in fake.calls)


def test_connect_maps_tls_error():
    import ssl
    with patch("core.email.providers.imap_smtp.IMAP4_SSL", side_effect=ssl.SSLError("bad tls")):
        with pytest.raises(TLSConfigurationError): asyncio.run(ImapSmtpProvider().connect(account(), creds()))


def test_list_folders_maps_failure(connected):
    provider, fake = connected; fake.list = lambda *a, **k: ("NO", [b"failure"])
    with pytest.raises(ConnectionError): asyncio.run(provider.list_folders())


def test_select_folder_changes_current_folder(connected):
    provider, fake = connected; asyncio.run(provider.select_folder("Archive"))
    assert provider._current_folder == "Archive" and ("select", "Archive", False) in fake.calls


def test_select_missing_folder_maps_error(connected):
    provider, fake = connected; fake.folders = ["INBOX"]
    with pytest.raises(MailboxNotFoundError): asyncio.run(provider.select_folder("Archive"))


def test_folder_info_does_not_select(connected):
    provider, fake = connected; asyncio.run(provider.get_folder_info("Archive"))
    assert provider._current_folder == "INBOX" and not any(c[0] == "select" for c in fake.calls)


def test_folder_info_missing_maps_error(connected):
    with pytest.raises(MailboxNotFoundError): asyncio.run(connected[0].get_folder_info("Missing"))


def test_search_uses_uid_server_side(connected):
    provider, fake = connected; refs = asyncio.run(provider.search(EmailSearchQuery(sender="sender@example.com")))
    call = next(c for c in fake.calls if c[0] == "uid_search")
    assert refs and not any(c[0] == "search" for c in fake.calls) and "FROM" in call[2] and "sender@example.com" in call[2]


def test_search_applies_offset_and_limit(connected):
    refs = asyncio.run(connected[0].search(EmailSearchQuery(offset=1, limit=1)))
    assert [r.uid for r in refs] == ["1002"]


def test_search_descending_order(connected):
    refs = asyncio.run(connected[0].search(EmailSearchQuery(sort_order="desc", limit=3)))
    assert [r.uid for r in refs] == ["1003", "1002", "1001"]


def test_search_rejects_unsupported_filters(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search(EmailSearchQuery(thread_id="t")))
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search(EmailSearchQuery(has_attachment=True)))
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search(EmailSearchQuery(sort_by="subject")))


def test_search_restores_original_folder(connected):
    provider, _ = connected; refs = asyncio.run(provider.search(EmailSearchQuery(folders=["Sent", "Archive"])))
    assert refs and provider._current_folder == "INBOX"


def test_search_failure_maps_transient_error(connected):
    provider, fake = connected; fake.uid_search = lambda charset, criteria: ("NO", [b"failure"])
    with pytest.raises(Exception): asyncio.run(provider.search(EmailSearchQuery()))


def test_fetch_full_message_uses_uid_peek(connected):
    provider, fake = connected; result = asyncio.run(provider.fetch_message(EmailMessageRef("user@example.com", "INBOX", "1001")))
    call = next(c for c in fake.calls if c[0] == "fetch")
    assert result.reference.uid == "1001" and call[2] == "BODY.PEEK[]"


def test_fetch_headers_uses_header_peek(connected):
    provider, fake = connected; result = asyncio.run(provider.fetch_message_headers(EmailMessageRef("user@example.com", "INBOX", "1001")))
    call = next(c for c in fake.calls if c[0] == "fetch")
    assert call[2] == "BODY.PEEK[HEADER]" and result.attachments == []


def test_fetch_headers_does_not_store_seen(connected):
    provider, fake = connected; asyncio.run(provider.fetch_message_headers(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert not any(c[0] == "store" for c in fake.calls)


def test_fetch_missing_message_maps_error(connected):
    provider, fake = connected; fake.fetch_status = "NO"
    with pytest.raises(MessageNotFoundError): asyncio.run(provider.fetch_message(EmailMessageRef("user@example.com", "INBOX", "1001")))


def test_fetch_wrong_account_is_rejected(connected):
    with pytest.raises(AuthorizationError): asyncio.run(connected[0].fetch_message(EmailMessageRef("other@example.com", "INBOX", "1001")))


def test_fetch_attachments_uses_full_fetch(connected):
    provider, fake = connected; result = asyncio.run(provider.fetch_attachments(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert isinstance(result, list) and next(c for c in fake.calls if c[0] == "fetch")[2] == "BODY.PEEK[]"


def test_mark_read_uses_uid_store(connected):
    provider, fake = connected; asyncio.run(provider.mark_read(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert ("store", "1001", "+FLAGS", "(\\Seen)") in fake.calls


def test_mark_unread_uses_uid_store(connected):
    provider, fake = connected; asyncio.run(provider.mark_unread(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert ("store", "1001", "-FLAGS", "(\\Seen)") in fake.calls


def test_flag_add_and_remove_use_uid_store(connected):
    provider, fake = connected; ref = EmailMessageRef("user@example.com", "INBOX", "1001")
    asyncio.run(provider.add_flag(ref, "\\Flagged")); asyncio.run(provider.remove_flag(ref, "\\Flagged"))
    assert ("store", "1001", "+FLAGS", "(\\Flagged)") in fake.calls and ("store", "1001", "-FLAGS", "(\\Flagged)") in fake.calls


def test_delete_marks_exact_uid(connected):
    provider, fake = connected; result = asyncio.run(provider.delete_message(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert result.is_success and ("store", "1001", "+FLAGS", "(\\Deleted)") in fake.calls


def test_copy_uses_uid_copy(connected):
    provider, fake = connected; result = asyncio.run(provider.copy_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))
    assert result.is_success and ("copy", "1001", "Archive") in fake.calls


def test_move_uses_uid_move(connected):
    provider, fake = connected; result = asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))
    assert result.is_success and ("move", "1001", "Archive") in fake.calls


def test_move_fallback_copies_then_expunge(connected):
    provider, fake = connected; fake.move_status = "NO"
    result = asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))
    assert result.is_success and ("copy", "1001", "Archive") in fake.calls and ("expunge", "1001") in fake.calls


def test_move_fallback_never_expunge_if_copy_fails(connected):
    provider, fake = connected; fake.move_status = "NO"; original = fake.uid
    def uid(command, *args):
        if command.lower() == "copy": fake.calls.append(("copy",) + args); return ("NO", [b"failure"])
        return original(command, *args)
    fake.uid = uid
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))
    assert not any(c[0] == "expunge" for c in fake.calls)


def test_move_fallback_refuses_failed_expunge(connected):
    provider, fake = connected; fake.move_status = "NO"; original = fake.uid
    def uid(command, *args):
        if command.lower() == "expunge": fake.calls.append(("expunge",) + args); return ("NO", [b"unsupported"])
        return original(command, *args)
    fake.uid = uid
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.move_message(EmailMessageRef("user@example.com", "INBOX", "1001"), "Archive"))


def test_archive_uses_advertised_special_use_folder(connected):
    provider, fake = connected; result = asyncio.run(provider.archive_message(EmailMessageRef("user@example.com", "INBOX", "1001")))
    assert result.is_success and ("move", "1001", "Archive") in fake.calls


def test_archive_rejects_missing_special_use_folder(connected):
    provider, fake = connected; fake.folders = ["INBOX", "Sent"]
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.archive_message(EmailMessageRef("user@example.com", "INBOX", "1001")))


def test_thread_operations_require_extension(connected):
    provider, _ = connected
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.search_threads(EmailSearchQuery()))
    with pytest.raises(ProviderCapabilityError): asyncio.run(provider.get_thread("thread"))


def test_draft_uses_special_use_folder(connected):
    provider, fake = connected; result = asyncio.run(provider.create_draft(EmailDraft(subject="Draft", body_plain="Body")))
    append = next(c for c in fake.calls if c[0] == "append")
    msg = BytesParser(policy=policy.default).parsebytes(append[3])
    assert result.is_success and append[1] == "Drafts" and "\\Draft" in append[2] and msg["Subject"] == "Draft"


def test_draft_requires_special_use_folder(connected):
    provider, fake = connected; fake.folders = ["INBOX", "Sent"]
    with pytest.raises(MailboxNotFoundError): asyncio.run(provider.create_draft(EmailDraft(subject="Draft")))


def test_update_draft_replaces_draft(connected):
    provider, fake = connected; result = asyncio.run(provider.update_draft(EmailMessageRef("user@example.com", "Drafts", "1001"), EmailDraft(subject="Updated")))
    assert result.is_success and any(c[0] == "store" for c in fake.calls) and any(c[0] == "append" for c in fake.calls)


def test_disconnect_is_idempotent_and_clears_credentials(connected):
    provider, fake = connected; asyncio.run(provider.disconnect()); asyncio.run(provider.disconnect())
    assert not provider.is_connected and provider._credentials is None and provider._account is None and any(c[0] == "logout" for c in fake.calls)


def test_async_context_manager_cleans_up(connected):
    provider, fake = connected
    async def run():
        async with provider as entered: assert entered is provider
    asyncio.run(run()); assert not provider.is_connected and any(c[0] == "logout" for c in fake.calls)


def test_smtp_starttls_uses_credential_store(connected):
    provider, _ = connected; smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp): result = asyncio.run(provider.send(account(), [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and any(c[0] == "starttls" for c in smtp.calls) and any(c[0] == "login" and c[2] == "test-password" for c in smtp.calls)


def test_smtp_ssl_mode_avoids_starttls(connected):
    provider, _ = connected; smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP_SSL", return_value=smtp): result = asyncio.run(provider.send(account(smtp_security="ssl", smtp_port=465), [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and not any(c[0] == "starttls" for c in smtp.calls)


def test_smtp_plain_mode_avoids_starttls(connected):
    provider, _ = connected; smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp): result = asyncio.run(provider.send(account(smtp_security="plain"), [EmailAddress("to@example.com")], "Subject", "Body"))
    assert result.is_success and not any(c[0] == "starttls" for c in smtp.calls)


def test_invalid_recipient_is_rejected_before_smtp(connected):
    with pytest.raises(InvalidRecipientError): asyncio.run(connected[0].send(account(), [EmailAddress("invalid")], "Subject", "Body"))


def test_recipient_count_limit_is_rejected_before_smtp(connected):
    recipients = [EmailAddress(f"u{i}@example.com") for i in range(101)]
    with pytest.raises(InvalidRecipientError): asyncio.run(connected[0].send(account(), recipients, "Subject", "Body"))


def test_subject_limit_is_rejected_before_smtp(connected):
    with pytest.raises(ValueError): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "x" * 1001, "Body"))


def test_attachment_count_limit_is_rejected_before_smtp(connected):
    attachments = [EmailAttachment(str(i), f"f{i}.txt", "text/plain", 1) for i in range(11)]
    with pytest.raises(Exception): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body", attachments))


def test_single_attachment_size_limit_is_rejected_before_smtp(connected):
    attachment = EmailAttachment("1", "large.bin", "application/octet-stream", 26 * 1024 * 1024)
    with pytest.raises(Exception): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body", [attachment]))


def test_send_supports_cc_bcc_and_reply_to(connected):
    smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp): result = asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body", cc=[EmailAddress("cc@example.com")], bcc=[EmailAddress("bcc@example.com")], reply_to=EmailAddress("reply@example.com")))
    msg = BytesParser(policy=policy.default).parsebytes(next(c for c in smtp.calls if c[0] == "sendmail")[3].encode())
    assert result.is_success and msg["Cc"] == "cc@example.com" and msg["Reply-To"] == "reply@example.com"


def test_send_html_and_plain_creates_multipart_alternative(connected):
    smtp = FakeSMTP()
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=smtp): result = asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "plain", "<b>html</b>"))
    msg = BytesParser(policy=policy.default).parsebytes(next(c for c in smtp.calls if c[0] == "sendmail")[3].encode())
    assert result.is_success and msg.is_multipart() and msg.get_body(preferencelist=("html",)) is not None


def test_smtp_recipient_refusal_maps_error(connected):
    class Refusing(FakeSMTP):
        def sendmail(self, sender, recipients, message): raise smtplib.SMTPRecipientsRefused({recipients[0]: (550, b"no")})
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=Refusing()):
        with pytest.raises(InvalidRecipientError): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body"))


def test_smtp_auth_failure_maps_error(connected):
    class BadAuth(FakeSMTP):
        def login(self, user, password): raise smtplib.SMTPAuthenticationError(535, b"bad auth")
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=BadAuth()):
        with pytest.raises(AuthenticationError): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body"))


def test_smtp_protocol_failure_maps_connection_error(connected):
    class Broken(FakeSMTP):
        def sendmail(self, sender, recipients, message): raise smtplib.SMTPException("failure")
    with patch("core.email.providers.imap_smtp.smtplib.SMTP", return_value=Broken()):
        with pytest.raises(ConnectionError): asyncio.run(connected[0].send(account(), [EmailAddress("to@example.com")], "Subject", "Body"))
