"""
core/email — Email Engine domain layer.

This package provides typed domain models, errors, limits, credentials,
and policy for the Email Engine v2. It is intentionally provider-neutral
and does not depend on IMAP/SMTP implementations.
"""
from __future__ import annotations

from .errors import (
    EmailError,
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
)
from .limits import EmailLimits
from .models import (
    EmailAccount,
    EmailAddress,
    EmailMessageRef,
    EmailAttachment,
    EmailMessage,
    EmailThread,
    EmailFolder,
    EmailDraft,
    EmailSearchQuery,
    EmailOperationResult,
    OperationStatus,
)
from .policy import EmailPolicy, OperationCategory, policy

__all__ = [
    # Models
    "EmailAccount",
    "EmailAddress",
    "EmailMessageRef",
    "EmailAttachment",
    "EmailMessage",
    "EmailThread",
    "EmailFolder",
    "EmailDraft",
    "EmailSearchQuery",
    "EmailOperationResult",
    "OperationStatus",
    # Errors
    "EmailError",
    "AuthenticationError",
    "AuthorizationError",
    "ConnectionError",
    "TimeoutError",
    "RateLimitError",
    "MailboxNotFoundError",
    "MessageNotFoundError",
    "AttachmentTooLargeError",
    "InvalidRecipientError",
    "TLSConfigurationError",
    "ProviderCapabilityError",
    "TransientProviderError",
    "PermanentProviderError",
    # Limits
    "EmailLimits",
    # Policy
    "EmailPolicy",
    "OperationCategory",
    "policy",
]
