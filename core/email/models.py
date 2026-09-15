"""
core/email/models.py — Typed domain models for the Email Engine.

All models are provider-neutral and expose no secrets (passwords, tokens, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .limits import EmailLimits


class EmailAddress:
    """Normalized email address with optional display name.

    Normalization rules (provider-neutral):
    - Surrounding whitespace is stripped
    - Domain portion is lowercased (domains are case-insensitive per RFC 4343)
    - Local part casing is preserved (case-sensitive per RFC 5321 in many contexts)
    """

    def __init__(self, address: str, name: str = "") -> None:
        address = address.strip()
        # Split into local and domain parts
        if "@" in address:
            local, domain = address.rsplit("@", 1)
            # Preserve local part casing, lowercase domain
            self.address = f"{local}@{domain.lower()}"
        else:
            # No @ symbol — treat as-is but still strip
            self.address = address.lower()
        self.name = name.strip() if name else ""

    def __repr__(self) -> str:
        return f"EmailAddress({self.address!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EmailAddress):
            return NotImplemented
        return self.address == other.address

    def __hash__(self) -> int:
        return hash(self.address)

    def format(self) -> str:
        """Return 'Name <address>' or just 'address'."""
        if self.name:
            return f"{self.name} <{self.address}>"
        return self.address


class OperationStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class EmailAccount:
    """Stable account metadata — no secrets stored here."""
    account_id: str
    provider: str  # e.g. "imap_smtp", "gmail_oauth", "microsoft_graph"
    display_name: str = ""
    primary_address: Optional[EmailAddress] = None
    aliases: list[EmailAddress] = field(default_factory=list)
    enabled: bool = True
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.primary_address is not None and not isinstance(
            self.primary_address, EmailAddress
        ):
            self.primary_address = EmailAddress(self.primary_address)
        self.aliases = [
            a if isinstance(a, EmailAddress) else EmailAddress(a)
            for a in self.aliases
        ]


@dataclass
class EmailMessageRef:
    """Immutable reference to a message — uses UID-based identity."""
    account_id: str
    mailbox: str  # provider-native mailbox name (e.g. "INBOX")
    uid: str  # immutable provider UID
    provider_native_id: Optional[str] = None  # optional legacy ID

    def __repr__(self) -> str:
        return (
            f"EmailMessageRef(account={self.account_id!r}, mailbox={self.mailbox!r}, "
            f"uid={self.uid!r})"
        )


@dataclass
class EmailAttachment:
    """Attachment metadata — does NOT embed file contents."""
    attachment_id: str
    filename: str
    content_type: str
    byte_size: int
    disposition: str = "attachment"  # "attachment" or "inline"
    content_id: Optional[str] = None
    # Controlled handle to the content (path or stream reference)
    content_handle: Optional[str] = None

    def __post_init__(self) -> None:
        if self.byte_size < 0:
            raise ValueError("byte_size must be non-negative")


@dataclass
class EmailMessage:
    """Full email message — no secrets, provider-neutral."""
    reference: EmailMessageRef
    sender: EmailAddress
    recipients: list[EmailAddress] = field(default_factory=list)
    reply_to: Optional[EmailAddress] = None
    subject: str = ""
    date: Optional[datetime] = None
    flags: list[str] = field(default_factory=list)  # e.g. ["\\Seen", "\\Flagged"]
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    attachments: list[EmailAttachment] = field(default_factory=list)
    thread_id: Optional[str] = None
    provider_metadata: dict = field(default_factory=dict)

    @property
    def is_read(self) -> bool:
        return "\\Seen" in self.flags or "\\Read" in self.flags

    @property
    def is_flagged(self) -> bool:
        return "\\Flagged" in self.flags


@dataclass
class EmailThread:
    """Thread of related messages."""
    thread_key: str
    messages: list[EmailMessageRef] = field(default_factory=list)
    subject: str = ""
    first_message_date: Optional[datetime] = None
    last_message_date: Optional[datetime] = None
    message_count: int = 0

    def __post_init__(self) -> None:
        self.message_count = len(self.messages)


@dataclass
class EmailFolder:
    """Provider mailbox representation."""
    provider_name: str  # e.g. "INBOX", "Sent", "Drafts"
    display_name: str = ""
    selectable: bool = True
    read_only: bool = False
    special_use: Optional[str] = None  # e.g. "\\Drafts", "\\Sent", "\\Trash"


@dataclass
class EmailDraft:
    """Draft message state."""
    draft_id: Optional[str] = None
    reference: Optional[EmailMessageRef] = None
    recipients: list[EmailAddress] = field(default_factory=list)
    subject: str = ""
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    attachments: list[EmailAttachment] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    state: str = "draft"  # "draft", "sent"

    def __post_init__(self) -> None:
        if self.reference is not None and not isinstance(
            self.reference, EmailMessageRef
        ):
            raise TypeError("reference must be an EmailMessageRef")


@dataclass
class EmailSearchQuery:
    """Structured search criteria — provider-neutral."""
    sender: Optional[str] = None
    recipients: Optional[list[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    folders: Optional[list[str]] = None
    flags: Optional[list[str]] = None
    thread_id: Optional[str] = None
    has_attachment: Optional[bool] = None
    limit: Optional[int] = None  # None = use default, 0 = invalid
    offset: int = 0
    sort_by: str = "date"  # "date", "relevance"
    sort_order: str = "desc"  # "asc", "desc"

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit must be non-negative")
        if self.limit == 0:
            raise ValueError("limit must be positive (use None for default)")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")

    @property
    def resolved_limit(self) -> int:
        """Return the effective limit after applying defaults and caps."""
        if self.limit is None:
            return EmailLimits.DEFAULT_READ_LIMIT
        return min(self.limit, EmailLimits.MAX_SEARCH_RESULTS)


@dataclass
class EmailOperationResult:
    """Result of an email operation."""
    operation_id: str
    status: OperationStatus
    affected_refs: list[EmailMessageRef] = field(default_factory=list)
    provider_metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status == OperationStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        return self.status == OperationStatus.FAILED
