"""Action-facing orchestration boundary for the Email Engine."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, is_dataclass, replace
from typing import Any, Mapping, Optional

from .errors import ProviderCapabilityError
from .idempotency import IdempotencyStore, InMemoryIdempotencyStore
from .models import EmailAccount, EmailAddress, EmailAttachment, EmailDraft, EmailMessageRef, EmailOperationResult, EmailSearchQuery, OperationStatus
from .policy import EmailPolicy, OperationCategory
from .providers.base import Capability
from .search import normalize_search_query


def _fingerprint(value: Any) -> str:
    def default(obj: Any) -> Any:
        if is_dataclass(obj): return asdict(obj)
        if hasattr(obj, "value"): return obj.value
        if isinstance(obj, set): return sorted(obj)
        return repr(obj)
    payload = json.dumps(value, default=default, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmailService:
    """The sole action-facing orchestration boundary for email operations."""

    def __init__(self, accounts: Mapping[str, EmailAccount], providers: Mapping[str, Any], *, policy=EmailPolicy, idempotency_store: Optional[IdempotencyStore] = None) -> None:
        self._accounts = dict(accounts); self._providers = dict(providers); self._policy = policy
        self._idempotency = idempotency_store or InMemoryIdempotencyStore()

    def account_metadata(self, account_id: str) -> dict[str, Any]:
        account = self._accounts.get(account_id)
        if account is None: raise KeyError(f"Unknown email account: {account_id}")
        return {"account_id": account.account_id, "provider": account.provider, "display_name": account.display_name,
                "primary_address": account.primary_address.format() if account.primary_address else None,
                "aliases": [a.format() for a in account.aliases], "enabled": account.enabled,
                "capabilities": list(account.capabilities)}

    async def list_folders(self, account_id: str):
        _, provider = self._provider(account_id); self._require(provider, Capability.FOLDERS)
        return await provider.list_folders()

    def _provider(self, account_id: str) -> tuple[EmailAccount, Any]:
        account = self._accounts.get(account_id); provider = self._providers.get(account_id)
        if account is None or provider is None: raise KeyError(f"Unknown email account: {account_id}")
        if not account.enabled: raise PermissionError("Email account is disabled")
        return account, provider

    @staticmethod
    def _require(provider: Any, capability: Capability) -> None:
        supports = getattr(provider, "supports", None)
        if callable(supports): available = supports(capability)
        else:
            metadata = getattr(provider, "metadata", None); caps = getattr(metadata, "capabilities", None)
            available = caps is not None and caps.supports(capability)
        if not available: raise ProviderCapabilityError(f"Provider does not support {capability.name.lower()}")

    async def search(self, account_id: str, query: EmailSearchQuery) -> list[EmailMessageRef]:
        _, provider = self._provider(account_id); self._require(provider, Capability.SEARCH)
        return await provider.search(normalize_search_query(query))

    async def get_message(self, account_id: str, ref: EmailMessageRef, *, include_body: bool = True, include_attachments: bool = False):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.FETCH)
        return await provider.fetch_message(ref, include_body=include_body, include_attachments=include_attachments)

    async def fetch_attachments(self, account_id: str, ref: EmailMessageRef):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.ATTACHMENTS)
        return await provider.fetch_attachments(ref)

    async def mark_read(self, account_id: str, ref: EmailMessageRef): return await self._message_operation(account_id, ref, "mark_read")
    async def mark_unread(self, account_id: str, ref: EmailMessageRef): return await self._message_operation(account_id, ref, "mark_unread")
    async def _message_operation(self, account_id: str, ref: EmailMessageRef, method: str):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.READ_STATE)
        return await getattr(provider, method)(ref)

    async def add_flag(self, account_id: str, ref: EmailMessageRef, flag: str): return await self._flag(account_id, ref, flag, True)
    async def remove_flag(self, account_id: str, ref: EmailMessageRef, flag: str): return await self._flag(account_id, ref, flag, False)
    async def _flag(self, account_id, ref, flag, enabled):
        self._validate_ref(account_id, ref)
        if not flag or not flag.strip(): raise ValueError("flag must not be empty")
        _, provider = self._provider(account_id); self._require(provider, Capability.FLAGS)
        return await getattr(provider, "add_flag" if enabled else "remove_flag")(ref, flag.strip())

    async def move(self, account_id: str, ref: EmailMessageRef, target_folder: str): return await self._movement(account_id, ref, target_folder, "move_message", Capability.MOVE)
    async def copy(self, account_id: str, ref: EmailMessageRef, target_folder: str): return await self._movement(account_id, ref, target_folder, "copy_message", Capability.COPY)
    async def _movement(self, account_id, ref, target_folder, method, capability):
        self._validate_ref(account_id, ref)
        if not target_folder or not target_folder.strip(): raise ValueError("target_folder must not be empty")
        _, provider = self._provider(account_id); self._require(provider, capability)
        return await getattr(provider, method)(ref, target_folder.strip())

    async def archive(self, account_id: str, ref: EmailMessageRef):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.ARCHIVE)
        return await provider.archive_message(ref)

    async def delete(self, account_id: str, ref: EmailMessageRef, *, confirmed: bool = False):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.DELETE)
        if self._policy.requires_confirmation(OperationCategory.DELETE) and not confirmed: raise PermissionError("Confirmation required for email deletion")
        return await provider.delete_message(ref)

    async def create_draft(self, account_id: str, draft: EmailDraft):
        _, provider = self._provider(account_id); self._require(provider, Capability.DRAFTS); return await provider.create_draft(draft)

    async def update_draft(self, account_id: str, ref: EmailMessageRef, draft: EmailDraft):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.DRAFTS); return await provider.update_draft(ref, draft)

    async def send(self, account_id: str, to: list[EmailAddress], subject: str, *, body_plain: Optional[str] = None, body_html: Optional[str] = None, attachments: Optional[list[EmailAttachment]] = None, cc: Optional[list[EmailAddress]] = None, bcc: Optional[list[EmailAddress]] = None, reply_to: Optional[EmailAddress] = None, confirmed: bool = False, operation_id: Optional[str] = None) -> EmailOperationResult:
        account, provider = self._provider(account_id); self._require(provider, Capability.SEND)
        if self._policy.requires_confirmation(OperationCategory.SEND) and not confirmed: raise PermissionError("Confirmation required before sending email")
        op_id = operation_id or str(uuid.uuid4())
        payload = {"account_id": account_id, "to": to, "cc": cc, "bcc": bcc, "subject": subject, "body_plain": body_plain, "body_html": body_html, "attachments": attachments, "reply_to": reply_to}
        record = self._idempotency.begin(op_id, _fingerprint(payload))
        if record.status in {"success", "unknown"}: return record.result
        try:
            result = await provider.send(account=account, to=list(to), subject=subject, body_plain=body_plain, body_html=body_html, attachments=attachments or [], cc=list(cc or []), bcc=list(bcc or []), reply_to=reply_to)
        except Exception:
            result = EmailOperationResult(op_id, OperationStatus.UNKNOWN, warnings=["Send completion is ambiguous; reconcile before retrying"], error="Email send completion is ambiguous", error_code="send_unknown")
            self._idempotency.mark_unknown(op_id, result); return result
        if isinstance(result, EmailOperationResult):
            if result.operation_id != op_id: result = replace(result, operation_id=op_id)
            if result.status == OperationStatus.UNKNOWN:
                self._idempotency.mark_unknown(op_id, result); return result
        self._idempotency.complete(op_id, result); return result

    async def reply(self, account_id: str, ref: EmailMessageRef, *, body_plain: Optional[str] = None, body_html: Optional[str] = None, confirmed: bool = False, operation_id: Optional[str] = None):
        return await self._unsupported_composed(account_id, ref, OperationCategory.REPLY, Capability.REPLY, confirmed)
    async def reply_all(self, account_id: str, ref: EmailMessageRef, *, body_plain: Optional[str] = None, body_html: Optional[str] = None, confirmed: bool = False, operation_id: Optional[str] = None):
        return await self._unsupported_composed(account_id, ref, OperationCategory.REPLY_ALL, Capability.REPLY_ALL, confirmed)
    async def forward(self, account_id: str, ref: EmailMessageRef, recipients: list[EmailAddress], *, body_plain: Optional[str] = None, body_html: Optional[str] = None, confirmed: bool = False, operation_id: Optional[str] = None):
        self._validate_ref(account_id, ref)
        if not recipients: raise ValueError("forward requires at least one recipient")
        return await self._unsupported_composed(account_id, ref, OperationCategory.FORWARD, Capability.FORWARD, confirmed)
    async def _unsupported_composed(self, account_id, ref, category, capability, confirmed):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, capability)
        if self._policy.requires_confirmation(category) and not confirmed: raise PermissionError(f"Confirmation required before {category.value}")
        raise ProviderCapabilityError(f"{category.value} composition is not supported by the selected provider")

    @staticmethod
    def _validate_ref(account_id: str, ref: EmailMessageRef) -> None:
        if not isinstance(ref, EmailMessageRef): raise TypeError("ref must be an EmailMessageRef")
        if ref.account_id != account_id: raise ValueError("message reference belongs to a different account")
        if not ref.mailbox or not ref.uid: raise ValueError("message reference requires mailbox and uid")
