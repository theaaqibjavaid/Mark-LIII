"""
core/email/policy.py — Email operation policy.

Determines which operations require user confirmation before execution.
This module does NOT invoke any UI — it only answers the question:
"Does this operation require confirmation?"

The actual confirmation mechanism is handled by core/confirm.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class OperationCategory(Enum):
    """Categories of email operations."""
    # Read-only operations — no confirmation needed
    READ = "read"
    SEARCH = "search"
    LIST_FOLDERS = "list_folders"

    # Reversible mailbox operations — no confirmation needed
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    ARCHIVE = "archive"
    MOVE = "move"
    COPY = "copy"
    STAR = "star"
    UNSTAR = "unstar"
    FLAG = "flag"
    UNFLAG = "unflag"
    CREATE_DRAFT = "create_draft"
    UPDATE_DRAFT = "update_draft"

    # Destructive/outbound operations — confirmation required
    SEND = "send"
    REPLY = "reply"
    REPLY_ALL = "reply_all"
    FORWARD = "forward"
    DELETE = "delete"
    BULK_DELETE = "bulk_delete"
    BULK_SEND = "bulk_send"


class EmailPolicy:
    """
    Centralized policy for email operations.

    Returns True if the operation requires explicit user confirmation.
    """

    # Operations that require confirmation
    _CONFIRM_REQUIRED: set[OperationCategory] = {
        OperationCategory.SEND,
        OperationCategory.REPLY,
        OperationCategory.REPLY_ALL,
        OperationCategory.FORWARD,
        OperationCategory.DELETE,
        OperationCategory.BULK_DELETE,
        OperationCategory.BULK_SEND,
    }

    @classmethod
    def requires_confirmation(cls, operation: OperationCategory, **kwargs) -> bool:
        """
        Determine if an operation requires user confirmation.

        Args:
            operation: The operation category.
            **kwargs: Additional context (e.g., recipient_count, is_bulk).

        Returns:
            True if confirmation is required, False otherwise.
        """
        if operation in cls._CONFIRM_REQUIRED:
            return True

        # Special case: draft creation/update can be configured
        if operation in (OperationCategory.CREATE_DRAFT, OperationCategory.UPDATE_DRAFT):
            # Default: no confirmation for drafts (they're reversible)
            return False

        # All other operations are read-only or reversible — no confirmation
        return False

    @classmethod
    def is_destructive(cls, operation: OperationCategory) -> bool:
        """Check if an operation is considered destructive."""
        return operation in {
            OperationCategory.DELETE,
            OperationCategory.BULK_DELETE,
        }

    @classmethod
    def is_outbound(cls, operation: OperationCategory) -> bool:
        """Check if an operation sends email externally."""
        return operation in {
            OperationCategory.SEND,
            OperationCategory.REPLY,
            OperationCategory.REPLY_ALL,
            OperationCategory.FORWARD,
        }

    @classmethod
    def is_bulk(cls, operation: OperationCategory) -> bool:
        """Check if an operation affects multiple messages."""
        return operation in {
            OperationCategory.BULK_DELETE,
            OperationCategory.BULK_SEND,
        }


# Singleton instance for convenience
policy = EmailPolicy()
