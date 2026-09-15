"""Action-facing orchestration boundary for the Email Engine."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, Optional

from .errors import EmailError, ProviderCapabilityError
from .idempotency import IdempotencyStore, InMemoryIdempotencyStore
from .models import EmailAccount, EmailMessageRef, EmailOperationResult, EmailSearchQuery, OperationStatus
from .policy import EmailPolicy, OperationCategory
from .providers.base import Capability
from .search import normalize_search_query


_CAPABILITY_BY_OPERATION = {
    "search": Capability.SEARCH,
    "get_message": Capability.FETCH,
    "mark_read": Capability.READ_STATE,
    "mark_unread": Capability.READ_STATE,
    "add_flag": Capability.FLAGS,
    "remove_flag": Capability.FLAGS,
    "move": Capability.MOVE,
    "copy": Capability.COPY,
    "delete": Capability.DELETE,
    "archive": Capability.ARCHIVE,
    "send": Capability.SEND,
    "create_draft": Capability.DRAFTS,
    "update_draft": Capability.DRAFTS,
}


def _fingerprint(value: Any) -> str:
    def default(obj: Any) -> Any:
        if is_dataclass(obj):
            return asdict(obj)
        if hasattr(obj, "value"):
            return obj.value
        if isinstance(obj, set):
            return sorted(obj)
        return repr(obj)
    payload = json.dumps(value, default=default, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmailService:
    """Single action-facing boundary; provider protocol details stay below it."""

    def __init__(self, accounts: Mapping[str, EmailAccount], providers: Mapping[str, Any], *, policy=EmailPolicy, idempotency_store: Optional[IdempotencyStore] = None) -> None:
        self._accounts = dict(accounts)
        self._providers = dict(providers)
        self._policy = policy
        self._idempotency = idempotency_store or InMemoryIdempotencyStore()

    def _provider(self, account_id: str) -> tuple[EmailAccount, Any]:
        account = self._accounts.get(account_id)
        provider = self._providers.get(account_id)
        if account is None or provider is None:
            raise KeyError(f"Unknown email account: {account_id}")
        if not account.enabled:
            raise PermissionError("Email account is disabled")
        return account, provider

    def _require(self, provider: Any, capability: Capability) -> None:
        capabilities = getattr(provider, "metadata", None).capabilities
        if not capabilities.supports(capability):
            raise ProviderCapabilityError(f"Provider does not support {capability.name.lower()}")

    async def search(self, account_id: str, query: EmailSearchQuery):
        _, provider = self._provider(account_id)
        self._require(provider, Capability.SEARCH)
        return await provider.search(normalize_search_query(query))

    async def get_message(self, account_id: str, ref: EmailMessageRef, *, include_body=True, include_attachments=False):
        self._validate_ref(account_id, ref)
        _, provider = self._provider(account_id)
        self._require(provider, Capability.FETCH)
        return await provider.fetch_message(ref, include_body=include_body, include_attachments=include_attachments)

    async def mark_read(self, account_id: str, ref: EmailMessageRef):
        return await self._message_operation(account_id, ref, "mark_read", Capability.READ_STATE, OperationCategory.MARK_READ)

    async def mark_unread(self, account_id: str, ref: EmailMessageRef):
        return await self._message_operation(account_id, ref, "mark_unread", Capability.READ_STATE, OperationCategory.MARK_UNREAD)

    async def add_flag(self, account_id: str, ref: EmailMessageRef, flag: str):
        self._validate_ref(account_id, ref)
        if not flag or not flag.strip(): raise ValueError("flag must not be empty")
        _, provider = self._provider(account_id); self._require(provider, Capability.FLAGS)
        return await provider.add_flag(ref, flag.strip())

    async def remove_flag(self, account_id: str, ref: EmailMessageRef, flag: str):
        self._validate_ref(account_id, ref)
        if not flag or not flag.strip(): raise ValueError("flag must not be empty")
        _, provider = self._provider(account_id); self._require(provider, Capability.FLAGS)
        return await provider.remove_flag(ref, flag.strip())

    async def _message_operation(self, account_id, ref, method, capability, category):
        self._validate_ref(account_id, ref)
        _, provider = self._provider(account_id); self._require(provider, capability)
        return await getattr(provider, method)(ref)

    async def move(self, account_id: str, ref: EmailMessageRef, target_folder: str):
        return await self._movement(account_id, ref, target_folder, "move_message", Capability.MOVE)

    async def copy(self, account_id: str, ref: EmailMessageRef, target_folder: str):
        return await self._movement(account_id, ref, target_folder, "copy_message", Capability.COPY)

    async def archive(self, account_id: str, ref: EmailMessageRef):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.ARCHIVE)
        return await provider.archive_message(ref)

    async def _movement(self, account_id, ref, target_folder, method, capability):
        self._validate_ref(account_id, ref)
        if not target_folder or not target_folder.strip(): raise ValueError("target_folder must not be empty")
        _, provider = self._provider(account_id); self._require(provider, capability)
        return await getattr(provider, method)(ref, target_folder.strip())

    async def delete(self, account_id: str, ref: EmailMessageRef, *, confirmed=False):
        self._validate_ref(account_id, ref); _, provider = self._provider(account_id); self._require(provider, Capability.DELETE)
        if not self._policy.requires_confirmation(OperationCategory.DELETE) or confirmed:
            return await provider.delete_message(ref)
        raise PermissionError("Confirmation required for email deletion")

    async def send(self, account_id: str, message: Any, *, confirmed=False, operation_id: Optional[str] = None):
        _, provider = self._provider(account_id); self._require(provider, Capability.SEND)
        if not confirmed and self._policy.requires_confirmation(OperationCategory.SEND):
            raise PermissionError("Confirmation required before sending email")
        op_id = operation_id or str(uuid.uuid4())
        fingerprint = _fingerprint({"account_id": account_id, "operation": "send", "message": message})
        record = self._idempotency.begin(op_id, fingerprint)
        if record.status == "success":
            return record.result
        try:
            result = await provider.send(message, op_id)
        except EmailError:
            raise
        except Exception as exc:
            # Provider send may be ambiguous; do not turn an exception into a retryable success.
            return EmailOperationResult(op_id, OperationStatus.UNKNOWN, warnings=["Send completion is ambiguous; reconcile before retrying"], error=str(exc), error_code="send_unknown")
        if isinstance(result, EmailOperationResult) and result.status == OperationStatus.UNKNOWN:
            return result
        self._idempotency.complete(op_id, result)
        return result

    async def create_draft(self, account_id: str, message: Any):
        _, provider = self._provider(account_id); self._require(provider, Capability.DRAFTS)
        return await provider.create_draft(message)

    async def update_draft(self, account_id: str, draft: Any, message: Any):
        _, provider = self._provider(account_id); self._require(provider, Capability.DRAFTS)
        return await provider.update_draft(draft, message)

    async def _composed(self, account_id: str, method: str, category: OperationCategory, payload: Any, *, confirmed: bool, operation_id: Optional[str]):
        _, provider = self._provider(account_id)
        capability = {OperationCategory.REPLY: Capability.REPLY, OperationCategory.REPLY_ALL: Capability.REPLY_ALL, OperationCategory.FORWARD: Capability.FORWARD}[category]
        self._require(provider, capability)
        if self._policy.requires_confirmation(category) and not confirmed:
            raise PermissionError(f"Confirmation required before {category.value}")
        op_id = operation_id or str(uuid.uuid4())
        fp = _fingerprint({"account_id": account_id, "operation": category.value, "payload": payload})
        record = self._idempotency.begin(op_id, fp)
        if record.status == "success": return record.result
        result = await getattr(provider, method)(payload, op_id)
        self._idempotency.complete(op_id, result)
        return result

    async def reply(self, account_id, payload, *, confirmed=False, operation_id=None):
        return await self._composed(account_id, "reply", OperationCategory.REPLY, payload, confirmed=confirmed, operation_id=operation_id)

    async def reply_all(self, account_id, payload, *, confirmed=False, operation_id=None):
        return await self._composed(account_id, "reply_all", OperationCategory.REPLY_ALL, payload, confirmed=confirmed, operation_id=operation_id)

    async def forward(self, account_id, payload, *, confirmed=False, operation_id=None):
        return await self._composed(account_id, "forward", OperationCategory.FORWARD, payload, confirmed=confirmed, operation_id=operation_id)

    @staticmethod
    def _validate_ref(account_id: str, ref: EmailMessageRef) -> None:
        if not isinstance(ref, EmailMessageRef): raise TypeError("ref must be an EmailMessageRef")
        if ref.account_id != account_id: raise ValueError("message reference belongs to a different account")
        if not ref.mailbox or not ref.uid: raise ValueError("message reference requires mailbox and uid")
