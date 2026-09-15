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
        """Validate search limit. Zero is invalid (use None for default)."""
        if limit < 0:
            raise ValueError(f"Search limit must be non-negative, got {limit}")
        if limit == 0:
            raise ValueError("Search limit must be positive (use None for default)")
        return min(limit, cls.MAX_SEARCH_RESULTS)

    @classmethod
    def validate_read_limit(cls, limit: int) -> int:
        """Validate read limit. Zero is invalid (use None for default)."""
        if limit < 0:
            raise ValueError(f"Read limit must be non-negative, got {limit}")
        if limit == 0:
            raise ValueError("Read limit must be positive (use None for default)")
        return min(limit, cls.MAX_READ_LIMIT)

    @classmethod
    def validate_attachment_count(cls, count: int) -> int:
        """Validate number of attachments."""
        if count < 0:
            raise ValueError(f"Attachment count must be non-negative, got {count}")
        if count == 0:
            raise ValueError("Attachment count must be positive")
        if count > cls.MAX_ATTACHMENTS_PER_MESSAGE:
            raise ValueError(
                f"Attachment count {count} exceeds maximum {cls.MAX_ATTACHMENTS_PER_MESSAGE}"
            )
        return count

    @classmethod
    def validate_total_attachment_size(cls, size: int) -> int:
        """Validate total attachment size."""
        if size < 0:
            raise ValueError(f"Total attachment size must be non-negative, got {size}")
        if size > cls.MAX_TOTAL_ATTACHMENT_SIZE_BYTES:
            raise ValueError(
                f"Total attachment size {size} exceeds maximum {cls.MAX_TOTAL_ATTACHMENT_SIZE_BYTES}"
            )
        return size

    @classmethod
    def validate_message_size(cls, size: int) -> int:
        """Validate total message size."""
        if size < 0:
            raise ValueError(f"Message size must be non-negative, got {size}")
        if size > cls.MAX_MESSAGE_SIZE_BYTES:
            raise ValueError(
                f"Message size {size} exceeds maximum {cls.MAX_MESSAGE_SIZE_BYTES}"
            )
        return size

    @classmethod
    def validate_mailbox_page_size(cls, size: int) -> int:
        """Validate mailbox page size."""
        if size < 0:
            raise ValueError(f"Mailbox page size must be non-negative, got {size}")
        if size == 0:
            raise ValueError("Mailbox page size must be positive")
        if size > cls.MAX_MAILBOX_PAGE_SIZE:
            raise ValueError(
                f"Mailbox page size {size} exceeds maximum {cls.MAX_MAILBOX_PAGE_SIZE}"
            )
        return size

    @classmethod
    def validate_body_length(cls, length: int, *, full: bool = False) -> int:
        """Validate body content length."""
        max_len = cls.MAX_BODY_FULL_LENGTH if full else cls.MAX_BODY_PREVIEW_LENGTH
        if length < 0:
            raise ValueError(f"Body length must be non-negative, got {length}")
        if length > max_len:
            raise ValueError(
                f"Body length {length} exceeds maximum {max_len}"
            )
        return length

    @classmethod
    def validate_subject_length(cls, length: int) -> int:
        """Validate subject length."""
        if length < 0:
            raise ValueError(f"Subject length must be non-negative, got {length}")
        if length > cls.MAX_SUBJECT_LENGTH:
            raise ValueError(
                f"Subject length {length} exceeds maximum {cls.MAX_SUBJECT_LENGTH}"
            )
        return length
