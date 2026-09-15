"""
core/email/providers/base.py — Provider abstraction interface.

Defines the contract that all email providers must implement.
Provider-neutral: no IMAP/Gmail/Graph/protocol-specific concepts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Iterable, Optional


from ..credentials import CredentialStore
from ..errors import (
    AttachmentTooLargeError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
    RateLimitError,
    TimeoutError,
)
from ..models import (
    EmailAccount,
    EmailAttachment,
    EmailDraft,
    EmailFolder,
    EmailMessage,
    EmailMessageRef,
    EmailOperationResult,
    EmailSearchQuery,
    EmailThread,
)


# ── Connection State ───────────────────────────────────────────────────────────

class ProviderConnectionState(Enum):
    """Represents the current connection state of a provider."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    AUTHENTICATING = auto()
    AUTHENTICATED = auto()
    DISCONNECTING = auto()


# ── Capability Enum ────────────────────────────────────────────────────────────

class Capability(Enum):
    """
    Provider capabilities that can be discovered and queried.

    Each capability represents a category of operations the provider supports.
    Capabilities are provider-neutral and do not encode protocol specifics.
    """
    # Core messaging
    SEARCH = auto()
    FETCH = auto()
    SEND = auto()
    DRAFTS = auto()

    # Message state
    FLAGS = auto()
    READ_STATE = auto()
    THREADS = auto()

    # Mailbox operations
    FOLDERS = auto()
    MOVE = auto()
    COPY = auto()
    DELETE = auto()
    ARCHIVE = auto()

    # Attachments
    ATTACHMENTS = auto()
    ATTACHMENT_UPLOAD = auto()
    ATTACHMENT_DOWNLOAD = auto()

    # Reply/Forward composition
    REPLY = auto()
    REPLY_ALL = auto()
    FORWARD = auto()

    # Advanced features
    BULK_OPERATIONS = auto()
    RATE_LIMITING = auto()
    IDEMPOTENT_SEND = auto()


# ── Provider Metadata ─────────────────────────────────────────────────────────

class ProviderMetadata:
    """
    Non-secret metadata about a provider instance.

    Contains identity, type, capabilities, and connection state.
    Never stores passwords, tokens, or other secrets.
    """

    def __init__(
        self,
        provider_type: str,
        account_id: str,
        capabilities: ProviderCapabilities,
        connection_state: ProviderConnectionState,
        display_name: str = "",
    ) -> None:
        self.provider_type = provider_type
        self.account_id = account_id
        self.capabilities = capabilities
        self.connection_state = connection_state
        self.display_name = display_name

    @property
    def is_connected(self) -> bool:
        """True if the provider is in a connected/authenticated state."""
        return self.connection_state in (
            ProviderConnectionState.CONNECTED,
            ProviderConnectionState.AUTHENTICATED,
        )

    @property
    def is_authenticated(self) -> bool:
        """True if the provider has successfully authenticated."""
        return self.connection_state == ProviderConnectionState.AUTHENTICATED

    def __repr__(self) -> str:
        return (
            f"ProviderMetadata(provider={self.provider_type!r}, "
            f"account={self.account_id!r}, "
            f"connected={self.is_connected}, "
            f"capabilities={len(self.capabilities.supported)})"
        )


# ── Capability Container ──────────────────────────────────────────────────────

class ProviderCapabilities:
    """
    Container for a provider's supported capabilities.

    Supports querying via ``provider.capabilities.supports(Capability.X)``.
    """

    def __init__(self, supported: Optional[Iterable[Capability]] = None) -> None:
        self._supported: set[Capability] = set(supported or [])

    def supports(self, capability: Capability) -> bool:
        """Check if the provider supports a specific capability."""
        return capability in self._supported

    def add(self, capability: Capability) -> None:
        """Add a capability to this provider."""
        self._supported.add(capability)

    def remove(self, capability: Capability) -> None:
        """Remove a capability from this provider."""
        self._supported.discard(capability)

    @property
    def supported(self) -> set[Capability]:
        """Return the set of supported capabilities."""
        return set(self._supported)

    def __contains__(self, capability: Capability) -> bool:
        return self.supports(capability)

    def __len__(self) -> int:
        return len(self._supported)

    def __repr__(self) -> str:
        return f"ProviderCapabilities({self._supported!r})"


# ── Provider Interface ────────────────────────────────────────────────────────

class EmailProvider(ABC):
    """
    Abstract interface for email providers.

    All concrete providers (IMAP/SMTP, Gmail API, Microsoft Graph) must
    implement this interface. The interface is provider-neutral: it does not
    expose IMAP commands, Gmail labels, Graph endpoints, or any protocol-
    specific concepts.

    Security requirements:
    - Never store passwords, tokens, or secrets in provider objects.
    - Use CredentialStore for authentication data.
    - Error messages must not leak credentials.
    """

    # ── Lifecycle ──────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self, account: EmailAccount, credentials: CredentialStore) -> ProviderMetadata:
        """
        Establish connection and authenticate with the email provider.

        Args:
            account: Account metadata (no secrets).
            credentials: Secure credential store for authentication data.

        Returns:
            ProviderMetadata with connection state and capabilities.

        Raises:
            AuthenticationError: Invalid or expired credentials.
            AuthorizationError: Credentials valid but insufficient permissions.
            ConnectionError: Network or server unreachable.
            TimeoutError: Connection attempt exceeded time limit.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection and clean up resources.

        Must be idempotent: safe to call multiple times or when disconnected.
        Must not raise if already disconnected.
        """
        ...

    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Current provider metadata including capabilities and state."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if provider is connected and authenticated."""
        ...

    # ── Mailbox Operations ─────────────────────────────────────────────────

    @abstractmethod
    async def list_folders(self) -> list[EmailFolder]:
        """
        List available mailboxes/folders.

        Requires: Capability.FOLDERS

        Raises:
            ProviderCapabilityError: If FOLDERS capability not supported.
            ConnectionError: If not connected.
        """
        ...

    @abstractmethod
    async def get_folder_info(self, folder_name: str) -> EmailFolder:
        """
        Get information about a specific mailbox/folder.

        Requires: Capability.FOLDERS

        Raises:
            MailboxNotFoundError: If folder does not exist.
            ProviderCapabilityError: If FOLDERS capability not supported.
        """
        ...

    @abstractmethod
    async def select_folder(self, folder_name: str) -> EmailFolder:
        """
        Select and access a mailbox for subsequent operations.

        Requires: Capability.FOLDERS

        Raises:
            MailboxNotFoundError: If folder does not exist.
            ProviderCapabilityError: If FOLDERS capability not supported.
        """
        ...

    # ── Search ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def search(self, query: EmailSearchQuery) -> list[EmailMessageRef]:
        """
        Search messages using provider-neutral query criteria.

        Accepts EmailSearchQuery (not IMAP SEARCH syntax, Gmail query strings,
        or Graph $filter expressions). Translation to provider-specific syntax
        is the implementation's responsibility.

        Requires: Capability.SEARCH

        Raises:
            ProviderCapabilityError: If SEARCH capability not supported.
            ConnectionError: If not connected.
            TimeoutError: If search exceeds time limit.
        """
        ...

    # ── Message Retrieval ──────────────────────────────────────────────────

    @abstractmethod
    async def fetch_message(
        self,
        ref: EmailMessageRef,
        include_body: bool = True,
        include_attachments: bool = False,
    ) -> EmailMessage:
        """
        Fetch a complete message by its reference.

        Uses UID-based identity (EmailMessageRef.uid), not sequence numbers.

        Args:
            ref: Message reference containing account_id, mailbox, and uid.
            include_body: Whether to fetch message body content.
            include_attachments: Whether to fetch attachment metadata.

        Requires: Capability.FETCH

        Raises:
            MessageNotFoundError: If message does not exist.
            ProviderCapabilityError: If FETCH capability not supported.
        """
        ...

    @abstractmethod
    async def fetch_message_headers(
        self, ref: EmailMessageRef
    ) -> EmailMessage:
        """
        Fetch only message headers/metadata (lightweight).

        Returns minimal EmailMessage with headers, flags, and attachment
        metadata but no body content.

        Requires: Capability.FETCH

        Raises:
            MessageNotFoundError: If message does not exist.
        """
        ...

    @abstractmethod
    async def fetch_attachments(
        self, ref: EmailMessageRef
    ) -> list[EmailAttachment]:
        """
        Fetch attachment metadata for a message.

        Does NOT download attachment content — only metadata.

        Requires: Capability.ATTACHMENTS

        Raises:
            MessageNotFoundError: If message does not exist.
            ProviderCapabilityError: If ATTACHMENTS capability not supported.
        """
        ...

    # ── Message Operations ─────────────────────────────────────────────────

    @abstractmethod
    async def mark_read(self, ref: EmailMessageRef) -> EmailOperationResult:
        """
        Mark a message as read.

        Requires: Capability.READ_STATE or Capability.FLAGS

        Raises:
            MessageNotFoundError: If message does not exist.
            ProviderCapabilityError: If READ_STATE/FLAGS not supported.
        """
        ...

    @abstractmethod
    async def mark_unread(self, ref: EmailMessageRef) -> EmailOperationResult:
        """
        Mark a message as unread.

        Requires: Capability.READ_STATE or Capability.FLAGS
        """
        ...

    @abstractmethod
    async def add_flag(
        self, ref: EmailMessageRef, flag: str
    ) -> EmailOperationResult:
        """
        Add a flag to a message (e.g., \"\\Flagged\", \"\\Starred\").

        Requires: Capability.FLAGS
        """
        ...

    @abstractmethod
    async def remove_flag(
        self, ref: EmailMessageRef, flag: str
    ) -> EmailOperationResult:
        """
        Remove a flag from a message.

        Requires: Capability.FLAGS
        """
        ...

    @abstractmethod
    async def delete_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        """
        Delete a message (permanently or move to trash, provider-dependent).

        Requires: Capability.DELETE

        Raises:
            ProviderCapabilityError: If DELETE capability not supported.
        """
        ...

    # ── Message Movement ───────────────────────────────────────────────────

    @abstractmethod
    async def move_message(
        self, ref: EmailMessageRef, target_folder: str
    ) -> EmailOperationResult:
        """
        Move a message to a different folder.

        Requires: Capability.MOVE

        Raises:
            MailboxNotFoundError: If target folder does not exist.
            ProviderCapabilityError: If MOVE capability not supported.
        """
        ...

    @abstractmethod
    async def copy_message(
        self, ref: EmailMessageRef, target_folder: str
    ) -> EmailOperationResult:
        """
        Copy a message to a different folder (leaves original).

        Requires: Capability.COPY

        Raises:
            MailboxNotFoundError: If target folder does not exist.
            ProviderCapabilityError: If COPY capability not supported.
        """
        ...

    @abstractmethod
    async def archive_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        """
        Archive a message (provider-specific semantics).

        Requires: Capability.ARCHIVE

        Raises:
            ProviderCapabilityError: If ARCHIVE capability not supported.
        """
        ...

    # ── Thread Operations ──────────────────────────────────────────────────

    @abstractmethod
    async def search_threads(
        self, query: EmailSearchQuery
    ) -> list[EmailThread]:
        """
        Search for message threads.

        Requires: Capability.THREADS

        Raises:
            ProviderCapabilityError: If THREADS capability not supported.
        """
        ...

    @abstractmethod
    async def get_thread(self, thread_key: str) -> EmailThread:
        """
        Get a complete thread by its stable thread key.

        Requires: Capability.THREADS
        """
        ...

    # ── Draft Operations ───────────────────────────────────────────────────

    @abstractmethod
    async def create_draft(self, draft: EmailDraft) -> EmailOperationResult:
        """
        Create a new draft message.

        Requires: Capability.DRAFTS

        Raises:
            ProviderCapabilityError: If DRAFTS capability not supported.
        """
        ...

    @abstractmethod
    async def update_draft(
        self, ref: EmailMessageRef, draft: EmailDraft
    ) -> EmailOperationResult:
        """
        Update an existing draft.

        Requires: Capability.DRAFTS
        """
        ...

    @abstractmethod
    async def delete_draft(self, ref: EmailMessageRef) -> EmailOperationResult:
        """
        Delete a draft.

        Requires: Capability.DRAFTS
        """
        ...

    # ── Send ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def send(
        self,
        account: EmailAccount,
        recipients: list[str],
        subject: str,
        body_plain: Optional[str] = None,
        body_html: Optional[str] = None,
        attachments: Optional[list[EmailAttachment]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> EmailOperationResult:
        """
        Send an email message.

        Validates recipients using InvalidRecipientError for malformed addresses.
        Validates attachment sizes using AttachmentTooLargeError.

        Requires: Capability.SEND

        Raises:
            InvalidRecipientError: For malformed recipient addresses.
            AttachmentTooLargeError: If attachments exceed size limits.
            ProviderCapabilityError: If SEND capability not supported.
            AuthenticationError: If send requires authentication and not authenticated.
        """
        ...

    # ── Capability Query ───────────────────────────────────────────────────

    def supports(self, capability: Capability) -> bool:
        """
        Check if this provider supports a specific capability.

        Default implementation delegates to metadata. Subclasses may override
        for dynamic capability detection.

        Args:
            capability: The capability to check.

        Returns:
            True if the capability is supported.
        """
        return self.metadata.capabilities.supports(capability)
