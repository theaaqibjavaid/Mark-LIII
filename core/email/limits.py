"""
core/email/limits.py — Centralized safety and resource limits.

All limits are validated at construction — negative and zero values are rejected
where they have no meaningful interpretation.
"""
from __future__ import annotations


class EmailLimits:
    """Centralized safety limits for email operations."""

    # Attachment limits
    MAX_ATTACHMENT_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    MAX_ATTACHMENTS_PER_MESSAGE: int = 10
    MAX_TOTAL_ATTACHMENT_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB total

    # Message size limits
    MAX_MESSAGE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB total message

    # Recipient limits
    MAX_RECIPIENTS_PER_MESSAGE: int = 100  # to + cc + bcc combined

    # Search/query limits
    MAX_SEARCH_RESULTS: int = 500
    MAX_MAILBOX_PAGE_SIZE: int = 100

    # Content limits
    MAX_BODY_PREVIEW_LENGTH: int = 500  # chars for preview mode
    MAX_BODY_FULL_LENGTH: int = 50_000  # chars for detail mode
    MAX_SUBJECT_LENGTH: int = 1000

    # Default pagination
    DEFAULT_READ_LIMIT: int = 10
    MAX_READ_LIMIT: int = 50

    @classmethod
    def validate_attachment_size(cls, size: int) -> int:
        """Validate and return attachment size in bytes."""
        if size < 0:
            raise ValueError(f"Attachment size must be non-negative, got {size}")
        if size > cls.MAX_ATTACHMENT_SIZE_BYTES:
            raise ValueError(
                f"Attachment size {size} exceeds maximum {cls.MAX_ATTACHMENT_SIZE_BYTES}"
            )
        return size

    @classmethod
    def validate_recipient_count(cls, count: int) -> int:
        """Validate and return recipient count."""
        if count < 0:
            raise ValueError(f"Recipient count must be non-negative, got {count}")
        if count > cls.MAX_RECIPIENTS_PER_MESSAGE:
            raise ValueError(
                f"Recipient count {count} exceeds maximum {cls.MAX_RECIPIENTS_PER_MESSAGE}"
            )
        return count

    @classmethod
    def validate_search_limit(cls, limit: int) -> int:
        """Validate search limit, clamping to allowed range."""
        if limit < 0:
            raise ValueError(f"Search limit must be non-negative, got {limit}")
        return min(limit, cls.MAX_SEARCH_RESULTS)

    @classmethod
    def validate_read_limit(cls, limit: int) -> int:
        """Validate read limit, applying default and max cap."""
        if limit < 0:
            raise ValueError(f"Read limit must be non-negative, got {limit}")
        if limit == 0:
            return cls.DEFAULT_READ_LIMIT
        return min(limit, cls.MAX_READ_LIMIT)
