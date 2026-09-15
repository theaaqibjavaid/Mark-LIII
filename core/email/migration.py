"""Controlled, fail-closed routing policy for the Email Engine migration."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MigrationMode(str, Enum):
    LEGACY = "legacy"
    STAGED = "staged"
    V2 = "v2"


_LOW_RISK = frozenset({"account", "search", "read", "draft", "mailbox", "attachment"})
_HIGH_IMPACT = frozenset({"send", "reply", "reply_all", "forward", "delete"})
_ALL_OPERATIONS = _LOW_RISK | _HIGH_IMPACT


@dataclass(frozen=True)
class EmailMigrationPolicy:
    """Explicit rollout policy; rollback is always available in-memory."""

    mode: MigrationMode = MigrationMode.LEGACY
    high_impact_enabled: bool = False

    def route(self, operation: str) -> MigrationMode:
        if operation not in _ALL_OPERATIONS:
            raise ValueError(f"Unknown email migration operation: {operation}")

        if self.mode is MigrationMode.LEGACY:
            return MigrationMode.LEGACY

        if operation in _LOW_RISK:
            return MigrationMode.V2

        if self.mode is MigrationMode.V2 and self.high_impact_enabled:
            return MigrationMode.V2

        return MigrationMode.LEGACY

    def rollback(self) -> "EmailMigrationPolicy":
        return EmailMigrationPolicy(mode=MigrationMode.LEGACY)
