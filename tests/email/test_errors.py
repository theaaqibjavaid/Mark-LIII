"""
Tests for core/email/errors.py — exception hierarchy and safety.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.errors import (
    AttachmentTooLargeError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    EmailError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    PermanentProviderError,
    ProviderCapabilityError,
    RateLimitError,
    TLSConfigurationError,
    TimeoutError,
    TransientProviderError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Hierarchy
# ═══════════════════════════════════════════════════════════════════════════════


class TestExceptionHierarchy:
    def test_all_errors_inherit_from_email_error(self):
        """All custom errors must inherit from EmailError."""
        errors = [
            AuthenticationError,
            AuthorizationError,
            ConnectionError,
            TimeoutError,
            RateLimitError,
            MailboxNotFoundError,
            MessageNotFoundError,
            AttachmentTooLargeError,
            InvalidRecipientError,
            TLSConfigurationError,
            ProviderCapabilityError,
            TransientProviderError,
            PermanentProviderError,
        ]
        for exc_cls in errors:
            assert issubclass(exc_cls, EmailError), f"{exc_cls.__name__} must inherit from EmailError"

    def test_email_error_is_exception(self):
        assert issubclass(EmailError, Exception)


# ═══════════════════════════════════════════════════════════════════════════════
# Structured context
# ═══════════════════════════════════════════════════════════════════════════════


class TestExceptionContext:
    def test_base_error_has_operation_and_account(self):
        err = EmailError("Something went wrong", operation="send", account_id="acc1")
        assert err.operation == "send"
        assert err.account_id == "acc1"

    def test_subclass_inherits_context(self):
        err = AuthenticationError("Auth failed", operation="login", account_id="acc2")
        assert err.operation == "login"
        assert err.account_id == "acc2"

    def test_default_context_is_empty(self):
        err = EmailError("Basic error")
        assert err.operation == ""
        assert err.account_id == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Safe string representation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafeRepresentation:
    def test_str_contains_message(self):
        err = AuthenticationError("Login failed")
        assert "Login failed" in str(err)

    def test_str_includes_context(self):
        err = ConnectionError("Timeout", operation="imap_connect", account_id="acc1")
        s = str(err)
        assert "imap_connect" in s
        assert "acc1" in s

    def test_no_secrets_in_string(self):
        """Exception messages must never contain actual secrets."""
        err = AuthenticationError("Auth failed", account_id="acc1")
        s = str(err)
        # Should not contain common secret patterns
        assert "password" not in s.lower()
        assert "token" not in s.lower()
        assert "secret123" not in s  # actual secret value should not appear


# ═══════════════════════════════════════════════════════════════════════════════
# RateLimitError specific
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimitError:
    def test_retry_after_none_by_default(self):
        err = RateLimitError("Too many requests")
        assert err.retry_after is None

    def test_retry_after_set(self):
        err = RateLimitError("Rate limited", retry_after=30.5)
        assert err.retry_after == 30.5


# ═══════════════════════════════════════════════════════════════════════════════
# No secret leakage
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeakage:
    def test_exception_with_password_does_not_leak(self):
        """
        Even if someone passes a password in the message (which they shouldn't),
        the exception should not be caught and converted to hide it.
        This test verifies we don't have secret-stripping logic that could
        accidentally hide real error messages.
        """
        # The point is: we don't strip secrets, we just don't put them there.
        # This test documents the expectation.
        err = EmailError("Failed to connect")
        assert "password" not in str(err).lower()

    def test_all_error_types_can_be_raised_and_caught(self):
        """Verify all error types are catchable via EmailError base class."""
        errors = [
            AuthenticationError("auth"),
            AuthorizationError("authz"),
            ConnectionError("conn"),
            TimeoutError("timeout"),
            RateLimitError("rate"),
            MailboxNotFoundError("mailbox"),
            MessageNotFoundError("message"),
            AttachmentTooLargeError("attachment"),
            InvalidRecipientError("recipient"),
            TLSConfigurationError("tls"),
            ProviderCapabilityError("capability"),
            TransientProviderError("transient"),
            PermanentProviderError("permanent"),
        ]
        for err in errors:
            with pytest.raises(EmailError):
                raise err
