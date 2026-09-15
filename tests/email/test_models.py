"""
Tests for core/email/models.py — domain model contracts.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.models import (
    EmailAccount,
    EmailAddress,
    EmailAttachment,
    EmailDraft,
    EmailFolder,
    EmailMessage,
    EmailMessageRef,
    EmailOperationResult,
    EmailSearchQuery,
    EmailThread,
    OperationStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
# EmailAddress
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailAddress:
    def test_basic_construction(self):
        addr = EmailAddress("user@example.com")
        assert addr.address == "user@example.com"
        assert addr.name == ""

    def test_with_name(self):
        addr = EmailAddress("user@example.com", "John Doe")
        assert addr.name == "John Doe"

    def test_normalizes_domain_case(self):
        addr = EmailAddress("User@Example.COM")
        # Local part preserved, domain lowercased
        assert addr.address == "User@example.com"

    def test_preserves_local_part_casing(self):
        addr = EmailAddress("John.Doe@Example.COM")
        assert addr.address == "John.Doe@example.com"

    def test_mixed_case_local_part(self):
        addr = EmailAddress("First.Last@Domain.COM")
        assert addr.address == "First.Last@domain.com"

    def test_trims_whitespace(self):
        addr = EmailAddress("  user@example.com  ")
        assert addr.address == "user@example.com"

    def test_format_without_name(self):
        addr = EmailAddress("user@example.com")
        assert addr.format() == "user@example.com"

    def test_format_with_name(self):
        addr = EmailAddress("user@example.com", "John Doe")
        assert addr.format() == "John Doe <user@example.com>"

    def test_equality(self):
        a = EmailAddress("user@example.com")
        b = EmailAddress("user@example.com")
        assert a == b

    def test_hash(self):
        a = EmailAddress("user@example.com")
        b = EmailAddress("user@example.com")
        assert hash(a) == hash(b)


# ═══════════════════════════════════════════════════════════════════════════════
# EmailMessageRef
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailMessageRef:
    def test_basic_construction(self):
        ref = EmailMessageRef(
            account_id="acc1",
            mailbox="INBOX",
            uid="msg-123",
        )
        assert ref.account_id == "acc1"
        assert ref.mailbox == "INBOX"
        assert ref.uid == "msg-123"
        assert ref.provider_native_id is None

    def test_with_provider_native_id(self):
        ref = EmailMessageRef(
            account_id="acc1",
            mailbox="Sent",
            uid="uid-456",
            provider_native_id="legacy-789",
        )
        assert ref.provider_native_id == "legacy-789"

    def test_uid_is_required(self):
        # uid is a required field in the dataclass
        with pytest.raises(TypeError):
            EmailMessageRef(account_id="acc1", mailbox="INBOX")  # missing uid

    def test_repr(self):
        ref = EmailMessageRef(account_id="a", mailbox="M", uid="u")
        r = repr(ref)
        assert "account='a'" in r
        assert "mailbox='M'" in r
        assert "uid='u'" in r


# ═══════════════════════════════════════════════════════════════════════════════
# EmailAttachment
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailAttachment:
    def test_basic_construction(self):
        att = EmailAttachment(
            attachment_id="att1",
            filename="report.pdf",
            content_type="application/pdf",
            byte_size=1024,
        )
        assert att.filename == "report.pdf"
        assert att.disposition == "attachment"
        assert att.content_id is None

    def test_inline_attachment(self):
        att = EmailAttachment(
            attachment_id="att1",
            filename="logo.png",
            content_type="image/png",
            byte_size=512,
            disposition="inline",
            content_id="logo123",
        )
        assert att.disposition == "inline"
        assert att.content_id == "logo123"

    def test_negative_size_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailAttachment(
                attachment_id="att1",
                filename="x.txt",
                content_type="text/plain",
                byte_size=-1,
            )

    def test_content_handle_optional(self):
        att = EmailAttachment(
            attachment_id="att1",
            filename="x.txt",
            content_type="text/plain",
            byte_size=100,
        )
        assert att.content_handle is None


# ═══════════════════════════════════════════════════════════════════════════════
# EmailMessage
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailMessage:
    def test_minimal_construction(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        sender = EmailAddress("from@example.com")
        msg = EmailMessage(reference=ref, sender=sender)
        assert msg.subject == ""
        assert msg.recipients == []
        assert msg.attachments == []

    def test_with_all_fields(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        sender = EmailAddress("from@example.com", "From Person")
        recipient = EmailAddress("to@example.com", "To Person")
        now = datetime(2024, 1, 15, 10, 30, 0)
        msg = EmailMessage(
            reference=ref,
            sender=sender,
            recipients=[recipient],
            subject="Test Subject",
            date=now,
            flags=["\\Seen", "\\Flagged"],
            body_plain="Hello world",
            body_html="<p>Hello world</p>",
        )
        assert msg.subject == "Test Subject"
        assert len(msg.recipients) == 1
        assert msg.is_read is True
        assert msg.is_flagged is True

    def test_unread_message(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        msg = EmailMessage(reference=ref, sender=EmailAddress("a@b.com"))
        assert msg.is_read is False
        assert msg.is_flagged is False

    def test_read_flag_variants(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        msg = EmailMessage(
            reference=ref,
            sender=EmailAddress("a@b.com"),
            flags=["\\Read"],
        )
        assert msg.is_read is True

    def test_reply_to_optional(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        msg = EmailMessage(
            reference=ref,
            sender=EmailAddress("a@b.com"),
            reply_to=EmailAddress("reply@example.com"),
        )
        assert msg.reply_to.address == "reply@example.com"


# ═══════════════════════════════════════════════════════════════════════════════
# EmailThread
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailThread:
    def test_minimal_construction(self):
        thread = EmailThread(thread_key="thread-1")
        assert thread.messages == []
        assert thread.message_count == 0

    def test_with_messages(self):
        ref1 = EmailMessageRef(account_id="a", mailbox="INBOX", uid="1")
        ref2 = EmailMessageRef(account_id="a", mailbox="INBOX", uid="2")
        now = datetime(2024, 1, 15, 10, 0, 0)
        later = datetime(2024, 1, 15, 11, 0, 0)
        thread = EmailThread(
            thread_key="thread-1",
            messages=[ref1, ref2],
            subject="Re: Test",
            first_message_date=now,
            last_message_date=later,
        )
        assert thread.message_count == 2
        assert thread.subject == "Re: Test"


# ═══════════════════════════════════════════════════════════════════════════════
# EmailFolder
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailFolder:
    def test_basic_construction(self):
        folder = EmailFolder(provider_name="INBOX")
        assert folder.selectable is True
        assert folder.read_only is False
        assert folder.special_use is None

    def test_special_use_folder(self):
        folder = EmailFolder(
            provider_name="Drafts",
            display_name="Drafts",
            special_use="\\Drafts",
        )
        assert folder.special_use == "\\Drafts"

    def test_read_only_folder(self):
        folder = EmailFolder(
            provider_name="Archive",
            read_only=True,
        )
        assert folder.read_only is True


# ═══════════════════════════════════════════════════════════════════════════════
# EmailDraft
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailDraft:
    def test_minimal_construction(self):
        draft = EmailDraft()
        assert draft.state == "draft"
        assert draft.recipients == []

    def test_with_reference(self):
        ref = EmailMessageRef(account_id="a", mailbox="Drafts", uid="d1")
        draft = EmailDraft(reference=ref, subject="Draft Subject")
        assert draft.reference == ref

    def test_invalid_reference_type(self):
        with pytest.raises(TypeError):
            EmailDraft(reference="not-a-ref")  # type: ignore

    def test_sent_state(self):
        draft = EmailDraft(state="sent")
        assert draft.state == "sent"


# ═══════════════════════════════════════════════════════════════════════════════
# EmailSearchQuery
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailSearchQuery:
    def test_defaults(self):
        query = EmailSearchQuery()
        assert query.limit is None
        assert query.offset == 0
        assert query.sort_by == "date"
        assert query.sort_order == "desc"

    def test_resolved_limit_with_none(self):
        from core.email.limits import EmailLimits
        query = EmailSearchQuery()
        assert query.resolved_limit == EmailLimits.DEFAULT_READ_LIMIT

    def test_resolved_limit_with_value(self):
        from core.email.limits import EmailLimits
        query = EmailSearchQuery(limit=20)
        assert query.resolved_limit == 20

    def test_resolved_limit_clamped(self):
        from core.email.limits import EmailLimits
        query = EmailSearchQuery(limit=1000)
        assert query.resolved_limit == EmailLimits.MAX_SEARCH_RESULTS

    def test_negative_limit_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailSearchQuery(limit=-1)

    def test_zero_limit_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            EmailSearchQuery(limit=0)

    def test_negative_offset_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailSearchQuery(offset=-1)

    def test_full_query(self):
        query = EmailSearchQuery(
            sender="boss@example.com",
            recipients=["me@example.com"],
            subject="Quarterly",
            date_from=datetime(2024, 1, 1),
            date_to=datetime(2024, 12, 31),
            folders=["INBOX", "Archive"],
            has_attachment=True,
            limit=100,
        )
        assert query.sender == "boss@example.com"
        assert query.has_attachment is True


# ═══════════════════════════════════════════════════════════════════════════════
# EmailOperationResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailOperationResult:
    def test_success(self):
        result = EmailOperationResult(
            operation_id="op-1",
            status=OperationStatus.SUCCESS,
        )
        assert result.is_success is True
        assert result.is_failure is False

    def test_failure(self):
        result = EmailOperationResult(
            operation_id="op-1",
            status=OperationStatus.FAILED,
            error="Connection lost",
            error_code="CONN_ERR",
        )
        assert result.is_failure is True
        assert result.error == "Connection lost"

    def test_with_affected_refs(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="1")
        result = EmailOperationResult(
            operation_id="op-1",
            status=OperationStatus.SUCCESS,
            affected_refs=[ref],
        )
        assert len(result.affected_refs) == 1

    def test_with_warnings(self):
        result = EmailOperationResult(
            operation_id="op-1",
            status=OperationStatus.SUCCESS,
            warnings=["Recipient not found: spam@nowhere"],
        )
        assert len(result.warnings) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# EmailAccount
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailAccount:
    def test_minimal_construction(self):
        account = EmailAccount(account_id="acc1", provider="imap_smtp")
        assert account.enabled is True
        assert account.display_name == ""
        assert account.primary_address is None

    def test_with_all_fields(self):
        primary = EmailAddress("user@example.com", "User Name")
        alias = EmailAddress("alt@example.com")
        account = EmailAccount(
            account_id="acc1",
            provider="gmail_oauth",
            display_name="User Name",
            primary_address=primary,
            aliases=[alias],
            enabled=True,
            capabilities=["oauth", "imap", "smtp"],
        )
        assert account.primary_address.address == "user@example.com"
        assert len(account.aliases) == 1
        assert "oauth" in account.capabilities

    def test_aliases_normalized(self):
        account = EmailAccount(
            account_id="acc1",
            provider="imap_smtp",
            aliases=["user2@example.com"],
        )
        assert isinstance(account.aliases[0], EmailAddress)
        assert account.aliases[0].address == "user2@example.com"


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization / Secret Safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestSerialization:
    def test_message_ref_serializable(self):
        ref = EmailMessageRef(account_id="a", mailbox="INBOX", uid="u")
        data = {
            "account_id": ref.account_id,
            "mailbox": ref.mailbox,
            "uid": ref.uid,
            "provider_native_id": ref.provider_native_id,
        }
        json_str = json.dumps(data)
        loaded = json.loads(json_str)
        assert loaded["uid"] == "u"

    def test_operation_result_serializable(self):
        result = EmailOperationResult(
            operation_id="op-1",
            status=OperationStatus.SUCCESS,
            warnings=["warn1"],
        )
        data = {
            "operation_id": result.operation_id,
            "status": result.status.value,
            "warnings": result.warnings,
        }
        json_str = json.dumps(data)
        loaded = json.loads(json_str)
        assert loaded["status"] == "success"
