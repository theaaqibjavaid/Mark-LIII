"""Runtime-neutral dispatch boundary for reversible email migration."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .migration import EmailMigrationPolicy, MigrationMode

T = TypeVar("T")


class EmailMigrationRouter:
    """Select legacy or V2 execution without deleting the legacy path."""

    def __init__(self, policy: EmailMigrationPolicy | None = None) -> None:
        self.policy = policy or EmailMigrationPolicy()

    def dispatch(
        self,
        operation: str,
        legacy_handler: Callable[[], T],
        v2_handler: Callable[[], T] | None = None,
    ) -> T:
        mode = self.policy.route(operation)
        if mode is MigrationMode.LEGACY:
            return legacy_handler()
        if v2_handler is None:
            raise RuntimeError(f"V2 handler is not available for email operation: {operation}")
        return v2_handler()
