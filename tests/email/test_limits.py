"""
Tests for core/email/limits.py — centralized safety limits.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.limits import EmailLimits


# ═══════════════════════════════════════════════════════════════════════════════
# Default values
# ═══════════════════════════════════════════════════════════════════════════════


class TestDefaultValues:
    def test_max_attachment_size(self):
        assert EmailLimits.MAX_ATTACHMENT_SIZE_BYTES == 25 * 1024 * 1024  # 25 MB

    def test_max_attachments_per_message(self):
        assert EmailLimits.MAX_ATTACHMENTS_PER_MESSAGE == 10

    def test_max_total_attachment_size(self):
        assert EmailLimits.MAX_TOTAL_ATTACHMENT_SIZE_BYTES == 50 * 1024 * 1024  # 50 MB

    def test_max_message_size(self):
        assert EmailLimits.MAX_MESSAGE_SIZE_BYTES == 50 * 1024 * 1024

    def test_max_recipients(self):
        assert EmailLimits.MAX_RECIPIENTS_PER_MESSAGE == 100

    def test_max_search_results(self):
        assert EmailLimits.MAX_SEARCH_RESULTS == 500

    def test_max_mailbox_page_size(self):
        assert EmailLimits.MAX_MAILBOX_PAGE_SIZE == 100

    def test_body_preview_length(self):
        assert EmailLimits.MAX_BODY_PREVIEW_LENGTH == 500

    def test_body_full_length(self):
        assert EmailLimits.MAX_BODY_FULL_LENGTH == 50_000

    def test_default_read_limit(self):
        assert EmailLimits.DEFAULT_READ_LIMIT == 10

    def test_max_read_limit(self):
        assert EmailLimits.MAX_READ_LIMIT == 50


# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAttachmentSize:
    def test_valid_size(self):
        result = EmailLimits.validate_attachment_size(1024)
        assert result == 1024

    def test_zero_size_allowed(self):
        result = EmailLimits.validate_attachment_size(0)
        assert result == 0

    def test_negative_size_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailLimits.validate_attachment_size(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            EmailLimits.validate_attachment_size(EmailLimits.MAX_ATTACHMENT_SIZE_BYTES + 1)

    def test_exact_max_allowed(self):
        result = EmailLimits.validate_attachment_size(EmailLimits.MAX_ATTACHMENT_SIZE_BYTES)
        assert result == EmailLimits.MAX_ATTACHMENT_SIZE_BYTES


class TestValidateRecipientCount:
    def test_valid_count(self):
        result = EmailLimits.validate_recipient_count(5)
        assert result == 5

    def test_zero_allowed(self):
        result = EmailLimits.validate_recipient_count(0)
        assert result == 0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailLimits.validate_recipient_count(-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            EmailLimits.validate_recipient_count(101)

    def test_exact_max_allowed(self):
        result = EmailLimits.validate_recipient_count(100)
        assert result == 100


class TestValidateSearchLimit:
    def test_valid_limit(self):
        result = EmailLimits.validate_search_limit(10)
        assert result == 10

    def test_zero_allowed(self):
        result = EmailLimits.validate_search_limit(0)
        assert result == 0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailLimits.validate_search_limit(-1)

    def test_over_max_clamped(self):
        result = EmailLimits.validate_search_limit(1000)
        assert result == EmailLimits.MAX_SEARCH_RESULTS


class TestValidateReadLimit:
    def test_valid_limit(self):
        result = EmailLimits.validate_read_limit(5)
        assert result == 5

    def test_zero_returns_default(self):
        result = EmailLimits.validate_read_limit(0)
        assert result == EmailLimits.DEFAULT_READ_LIMIT

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            EmailLimits.validate_read_limit(-1)

    def test_over_max_clamped(self):
        result = EmailLimits.validate_read_limit(100)
        assert result == EmailLimits.MAX_READ_LIMIT

    def test_default_limit(self):
        result = EmailLimits.validate_read_limit(10)
        assert result == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Centralized configuration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCentralizedConfiguration:
    def test_limits_are_class_attributes(self):
        """Limits should be defined on the class, not scattered."""
        assert hasattr(EmailLimits, "MAX_ATTACHMENT_SIZE_BYTES")
        assert hasattr(EmailLimits, "MAX_RECIPIENTS_PER_MESSAGE")
        assert hasattr(EmailLimits, "MAX_SEARCH_RESULTS")

    def test_all_limits_are_positive(self):
        """All limit values should be positive integers."""
        for attr in dir(EmailLimits):
            if attr.startswith("MAX_") or attr.startswith("DEFAULT_"):
                value = getattr(EmailLimits, attr)
                assert isinstance(value, int), f"{attr} should be an int"
                assert value > 0, f"{attr} should be positive"
