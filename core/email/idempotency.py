"""Small, provider-neutral idempotency store for high-impact email operations."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class IdempotencyRecord:
    operation_id: str
    fingerprint: str
    status: str = "pending"
    result: Any = None


class IdempotencyStore(Protocol):
    def begin(self, operation_id: str, fingerprint: str) -> IdempotencyRecord: ...
    def get(self, operation_id: str) -> Optional[IdempotencyRecord]: ...
    def complete(self, operation_id: str, result: Any) -> IdempotencyRecord: ...


class InMemoryIdempotencyStore:
    """Process-local reference implementation; durable stores can implement the protocol."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = RLock()

    def begin(self, operation_id: str, fingerprint: str) -> IdempotencyRecord:
        if not operation_id or not operation_id.strip():
            raise ValueError("operation_id must not be empty")
        if not fingerprint:
            raise ValueError("fingerprint must not be empty")
        with self._lock:
            existing = self._records.get(operation_id)
            if existing:
                if existing.fingerprint != fingerprint:
                    raise ValueError("operation_id fingerprint mismatch")
                return existing
            record = IdempotencyRecord(operation_id, fingerprint)
            self._records[operation_id] = record
            return record

    def get(self, operation_id: str) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._records.get(operation_id)

    def complete(self, operation_id: str, result: Any) -> IdempotencyRecord:
        with self._lock:
            existing = self._records.get(operation_id)
            if existing is None:
                raise KeyError(operation_id)
            if existing.status != "pending":
                raise ValueError("operation is already complete")
            updated = IdempotencyRecord(operation_id, existing.fingerprint, "success", result)
            self._records[operation_id] = updated
            return updated
