"""core.email — Email Engine v2 domain layer."""
from .errors import (
    EmailError, AuthenticationError, AuthorizationError, ConnectionError,
    TimeoutError, RateLimitError, MailboxNotFoundError, MessageNotFoundError,
    AttachmentTooLargeError, InvalidRecipientError, TLSConfigurationError,
    ProviderCapabilityError, TransientProviderError, PermanentProviderError,
)
from .limits import EmailLimits
from .models import (
    EmailAccount, EmailAddress, EmailServerConfig, EmailMessageRef,
    EmailAttachment, EmailMessage, EmailThread, EmailFolder, EmailDraft,
    EmailSearchQuery, EmailOperationResult, OperationStatus,
)
from .policy import EmailPolicy, OperationCategory, policy

__all__ = [
    "EmailAccount", "EmailAddress", "EmailServerConfig", "EmailMessageRef",
    "EmailAttachment", "EmailMessage", "EmailThread", "EmailFolder", "EmailDraft",
    "EmailSearchQuery", "EmailOperationResult", "OperationStatus",
    "EmailError", "AuthenticationError", "AuthorizationError", "ConnectionError",
    "TimeoutError", "RateLimitError", "MailboxNotFoundError", "MessageNotFoundError",
    "AttachmentTooLargeError", "InvalidRecipientError", "TLSConfigurationError",
    "ProviderCapabilityError", "TransientProviderError", "PermanentProviderError",
    "EmailLimits", "EmailPolicy", "OperationCategory", "policy",
]
