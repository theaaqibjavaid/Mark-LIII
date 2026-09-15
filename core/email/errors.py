"""
core/email/errors.py — Typed email exception hierarchy.

All exceptions are safe to surface through the action layer — they never
expose credentials, tokens, or other secrets in their messages.
"""
from __future__ import annotations


class EmailError(Exception):
    """Base exception for all email errors."""

    def __init__(self, message: str, *, operation: str = "", account_id: str = "") -> None:
        super().__init__(message)
        self.operation = operation
        self.account_id = account_id

    def __str__(self) -> str:
        base = super().__str__()
        parts = [base]
        if self.operation:
            parts.append(f"[operation={self.operation}]")
        if self.account_id:
            parts.append(f"[account={self.account_id}]")
        return " ".join(parts)


class AuthenticationError(EmailError):
    """Failed to authenticate with the email provider."""


class AuthorizationError(EmailError):
    """Authenticated but not authorized for this operation."""


class ConnectionError(EmailError):
    """Failed to connect to the email server."""


class TimeoutError(EmailError):
    """Operation timed out."""


class RateLimitError(EmailError):
    """Provider rate limit exceeded."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class MailboxNotFoundError(EmailError):
    """Requested mailbox/folder does not exist."""


class MessageNotFoundError(EmailError):
    """Requested message was not found."""


class AttachmentTooLargeError(EmailError):
    """Attachment exceeds size limits."""


class InvalidRecipientError(EmailError):
    """Recipient address is invalid or malformed."""


class TLSConfigurationError(EmailError):
    """TLS/SSL configuration issue."""


class ProviderCapabilityError(EmailError):
    """Operation not supported by this provider."""


class TransientProviderError(EmailError):
    """Temporary provider error — may succeed on retry."""


class PermanentProviderError(EmailError):
    """Permanent provider error — will not succeed on retry."""
