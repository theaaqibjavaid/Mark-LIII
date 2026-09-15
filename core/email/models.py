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


@dataclass
class EmailServerConfig:
    """Non-secret IMAP/SMTP connection configuration for an email account."""
    imap_host: str
    imap_port: int = 993
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    imap_security: str = "ssl"
    smtp_security: str = "starttls"

    def __post_init__(self) -> None:
        if not self.imap_host or not self.imap_host.strip():
            raise ValueError("imap_host must not be empty")
        if self.imap_port <= 0 or self.imap_port > 65535:
            raise ValueError("imap_port must be between 1 and 65535")
        if self.smtp_port is not None and (self.smtp_port <= 0 or self.smtp_port > 65535):
            raise ValueError("smtp_port must be between 1 and 65535")
        if self.imap_security not in {"ssl", "starttls", "plain"}:
            raise ValueError("imap_security must be ssl, starttls, or plain")
        if self.smtp_security not in {"ssl", "starttls", "plain"}:
            raise ValueError("smtp_security must be ssl, starttls, or plain")


class EmailAddress:
    """Normalized email address with optional display name."""

    def __init__(self, address: str, name: str = "") -> None:
        address = address.strip()
        if "@" in address:
            local, domain = address.rsplit("@", 1)
            self.address = f"{local}@{domain.lower()}"
        else:
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
    provider: str
    display_name: str = ""
    primary_address: Optional[EmailAddress] = None
    aliases: list[EmailAddress] = field(default_factory=list)
    enabled: bool = True
    capabilities: list[str] = field(default_factory=list)
    server_config: Optional[EmailServerConfig] = None

    def __post_init__(self) -> None:
        if self.primary_address is not None and not isinstance(self.primary_address, EmailAddress):
            self.primary_address = EmailAddress(self.primary_address)
        self.aliases = [a if isinstance(a, EmailAddress) else EmailAddress(a) for a in self.aliases]
        if self.server_config is not None and not isinstance(self.server_config, EmailServerConfig):
            if isinstance(self.server_config, dict):
                self.server_config = EmailServerConfig(**self.server_config)
            else:
                raise TypeError("server_config must be EmailServerConfig or dict")


@dataclass
class EmailMessageRef:
    """Immutable reference to a message — uses UID-based identity."""
    account_id: str
    mailbox: str
    uid: str
    provider_native_id: Optional[str] = None

    def __repr__(self) -> str:
        return f"EmailMessageRef(account={self.account_id!r}, mailbox={self.mailbox!r}, uid={self.uid!r})"


@dataclass
class EmailAttachment:
    """Attachment metadata — does NOT embed file contents."""
    attachment_id: str
    filename: str
    content_type: str
    byte_size: int
    disposition: str = "attachment"
    content_id: Optional[str] = None
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
    flags: list[str] = field(default_factory=list)
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
    provider_name: str
    display_name: str = ""
    selectable: bool = True
    read_only: bool = False
    special_use: Optional[str] = None


@dataclass
class EmailDraft:
    draft_id: Optional[str] = None
    reference: Optional[EmailMessageRef] = None
    recipients: list[EmailAddress] = field(default_factory=list)
    subject: str = ""
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    attachments: list[EmailAttachment] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    state: str = "draft"

    def __post_init__(self) -> None:
        if self.reference is not None and not isinstance(self.reference, EmailMessageRef):
            raise TypeError("reference must be an EmailMessageRef")


@dataclass
class EmailSearchQuery:
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
    limit: Optional[int] = None
    offset: int = 0
    sort_by: str = "date"
    sort_order: str = "desc"

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit must be non-negative")
        if self.limit == 0:
            raise ValueError("limit must be positive (use None for default)")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")

    @property
    def resolved_limit(self) -> int:
        if self.limit is None:
            return EmailLimits.DEFAULT_READ_LIMIT
        return min(self.limit, EmailLimits.MAX_SEARCH_RESULTS)


@dataclass
class EmailOperationResult:
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
