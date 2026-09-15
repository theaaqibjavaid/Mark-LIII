"""Typed provider-neutral models for the Email Engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from email.utils import parseaddr
from .limits import EmailLimits

@dataclass
class EmailServerConfig:
    imap_host: str; imap_port: int = 993; smtp_host: Optional[str] = None; smtp_port: Optional[int] = None
    imap_security: str = "ssl"; smtp_security: str = "starttls"
    def __post_init__(self):
        if not self.imap_host or not self.imap_host.strip(): raise ValueError("imap_host must not be empty")
        if not 0 < self.imap_port <= 65535: raise ValueError("imap_port must be between 1 and 65535")
        if self.smtp_port is not None and not 0 < self.smtp_port <= 65535: raise ValueError("smtp_port must be between 1 and 65535")
        if self.imap_security not in {"ssl","starttls","plain"}: raise ValueError("imap_security must be ssl, starttls, or plain")
        if self.smtp_security not in {"ssl","starttls","plain"}: raise ValueError("smtp_security must be ssl, starttls, or plain")

class EmailAddress:
    def __init__(self, address: str, name: str = ""):
        if not isinstance(address, str): raise TypeError("address must be a string")
        raw = address.strip()
        if any(ch in raw for ch in "\r\n") or not raw:
            raise ValueError("Invalid email address")
        parsed_name, parsed_address = parseaddr(raw)
        if not parsed_address or "@" not in parsed_address:
            raise ValueError("Invalid email address")
        if parsed_address != raw and not ("<" in raw and ">" in raw):
            raise ValueError("Invalid email address")
        local, domain = parsed_address.rsplit("@", 1)
        if not local or not domain or "." not in domain or any(ch.isspace() for ch in parsed_address):
            raise ValueError("Invalid email address")
        display_name = name.strip() if name else parsed_name.strip()
        if any(ch in display_name for ch in "\r\n"):
            raise ValueError("Invalid email display name")
        self.address = local + "@" + domain.lower()
        self.name = display_name
    def __repr__(self): return f"EmailAddress({self.address!r})"
    def __eq__(self, other): return isinstance(other, EmailAddress) and self.address == other.address
    def __hash__(self): return hash(self.address)
    def format(self): return f"{self.name} <{self.address}>" if self.name else self.address

class OperationStatus(Enum):
    PENDING="pending"; SUCCESS="success"; FAILED="failed"; UNKNOWN="unknown"

@dataclass
class EmailAccount:
    account_id: str; provider: str; display_name: str = ""; primary_address: Optional[EmailAddress] = None
    aliases: list[EmailAddress] = field(default_factory=list); enabled: bool = True
    capabilities: list[str] = field(default_factory=list); server_config: Optional[EmailServerConfig] = None
    oauth_config: dict = field(default_factory=dict)
    def __post_init__(self):
        if self.primary_address is not None and not isinstance(self.primary_address, EmailAddress): self.primary_address=EmailAddress(self.primary_address)
        self.aliases=[a if isinstance(a,EmailAddress) else EmailAddress(a) for a in self.aliases]
        if isinstance(self.capabilities, dict):
            legacy=dict(self.capabilities); self.capabilities=[str(v) for v in legacy.get("capabilities", [])]
            if self.server_config is None:
                self.server_config=EmailServerConfig(imap_host=legacy.get("imap_server") or legacy.get("imap_host") or "", imap_port=int(legacy.get("imap_port",993)), smtp_host=legacy.get("smtp_server") or legacy.get("smtp_host"), smtp_port=(int(legacy["smtp_port"]) if legacy.get("smtp_port") is not None else None), imap_security=legacy.get("imap_security","ssl"), smtp_security=legacy.get("smtp_security","starttls"))

@dataclass
class EmailMessageRef:
    account_id:str; mailbox:str; uid:str; provider_native_id:Optional[str]=None
    def __repr__(self): return f"EmailMessageRef(account={self.account_id!r}, mailbox={self.mailbox!r}, uid={self.uid!r})"
@dataclass
class EmailAttachment:
    attachment_id:str; filename:str; content_type:str; byte_size:int; disposition:str="attachment"; content_id:Optional[str]=None; content_handle:Optional[str]=None
    def __post_init__(self):
        if self.byte_size<0: raise ValueError("byte_size must be non-negative")
@dataclass
class EmailMessage:
    reference:EmailMessageRef; sender:EmailAddress; recipients:list[EmailAddress]=field(default_factory=list); reply_to:Optional[EmailAddress]=None; subject:str=""; date:Optional[datetime]=None; flags:list[str]=field(default_factory=list); body_plain:Optional[str]=None; body_html:Optional[str]=None; attachments:list[EmailAttachment]=field(default_factory=list); thread_id:Optional[str]=None; provider_metadata:dict=field(default_factory=dict)
    @property
    def is_read(self): return "\\Seen" in self.flags or "\\Read" in self.flags
    @property
    def is_flagged(self): return "\\Flagged" in self.flags
@dataclass
class EmailThread:
    thread_key:str; messages:list[EmailMessageRef]=field(default_factory=list); subject:str=""; first_message_date:Optional[datetime]=None; last_message_date:Optional[datetime]=None; message_count:int=0
    def __post_init__(self): self.message_count=len(self.messages)
@dataclass
class EmailFolder:
    provider_name:str; display_name:str=""; selectable:bool=True; read_only:bool=False; special_use:Optional[str]=None
@dataclass
class EmailDraft:
    draft_id:Optional[str]=None; reference:Optional[EmailMessageRef]=None; recipients:list[EmailAddress]=field(default_factory=list); subject:str=""; body_plain:Optional[str]=None; body_html:Optional[str]=None; attachments:list[EmailAttachment]=field(default_factory=list); created_at:Optional[datetime]=None; updated_at:Optional[datetime]=None; state:str="draft"
    def __post_init__(self):
        if self.reference is not None and not isinstance(self.reference,EmailMessageRef): raise TypeError("reference must be an EmailMessageRef")
@dataclass
class EmailSearchQuery:
    sender:Optional[str]=None; recipients:Optional[list[str]]=None; subject:Optional[str]=None; body:Optional[str]=None; date_from:Optional[datetime]=None; date_to:Optional[datetime]=None; folders:Optional[list[str]]=None; flags:Optional[list[str]]=None; thread_id:Optional[str]=None; has_attachment:Optional[bool]=None; limit:Optional[int]=None; offset:int=0; sort_by:str="date"; sort_order:str="desc"
    def __post_init__(self):
        if self.limit is not None and self.limit<0: raise ValueError("limit must be non-negative")
        if self.limit==0: raise ValueError("limit must be positive (use None for default)")
        if self.offset<0: raise ValueError("offset must be non-negative")
    @property
    def resolved_limit(self): return EmailLimits.DEFAULT_READ_LIMIT if self.limit is None else min(self.limit,EmailLimits.MAX_SEARCH_RESULTS)
@dataclass
class EmailOperationResult:
    operation_id:str; status:OperationStatus; affected_refs:list[EmailMessageRef]=field(default_factory=list); provider_metadata:dict=field(default_factory=dict); warnings:list[str]=field(default_factory=list); error:Optional[str]=None; error_code:Optional[str]=None
    @property
    def is_success(self): return self.status==OperationStatus.SUCCESS
    @property
    def is_failure(self): return self.status==OperationStatus.FAILED
