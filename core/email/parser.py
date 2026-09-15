"""Defensive MIME parsing for inbound email."""
from __future__ import annotations

from datetime import datetime
from email import policy
from email.header import decode_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import re
from typing import Optional

from .limits import EmailLimits
from .models import EmailAddress, EmailAttachment, EmailMessage, EmailMessageRef


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(policy.default.header_factory(value))
    except Exception:
        pieces = []
        for chunk, charset in decode_header(value):
            if isinstance(chunk, bytes):
                try:
                    pieces.append(chunk.decode(charset or "ascii", errors="replace"))
                except (LookupError, UnicodeError):
                    pieces.append(chunk.decode("utf-8", errors="replace"))
            else:
                pieces.append(chunk)
        return "".join(pieces)


def _addresses(value: Optional[str]) -> list[EmailAddress]:
    if not value:
        return []
    result = []
    for name, address in getaddresses([value]):
        if address:
            result.append(EmailAddress(address, _decode(name)))
    return result


def _date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _sanitize_filename(filename: Optional[str]) -> str:
    value = _decode(filename).replace("\\", "/").split("/")[-1]
    value = re.sub(r"[\x00-\x1f\x7f]", "_", value).strip()
    return value if value not in {"", ".", ".."} else "attachment"


def parse_message(
    raw_message: bytes,
    limits: type[EmailLimits] = EmailLimits,
    *,
    reference: Optional[EmailMessageRef] = None,
) -> EmailMessage:
    """Parse a complete MIME message without executing or interpreting payloads."""
    if not isinstance(raw_message, bytes):
        raise TypeError("raw_message must be bytes")
    limits.validate_message_size(len(raw_message))
    msg = BytesParser(policy=policy.default).parsebytes(raw_message)

    ref = reference or EmailMessageRef(account_id="unknown", mailbox="unknown", uid="unknown")
    sender = (_addresses(msg.get("From")) or [EmailAddress("")])[0]
    recipients = _addresses(msg.get("To")) + _addresses(msg.get("Cc"))
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    attachments: list[EmailAttachment] = []
    attachment_total = 0

    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True)
        payload = payload or b""

        if disposition in {"attachment", "inline"} or filename:
            if len(attachments) >= limits.MAX_ATTACHMENTS_PER_MESSAGE:
                raise ValueError("Attachment count exceeds configured limit")
            limits.validate_attachment_size(len(payload))
            attachment_total += len(payload)
            limits.validate_total_attachment_size(attachment_total)
            attachments.append(
                EmailAttachment(
                    attachment_id=f"part-{len(attachments) + 1}",
                    filename=_sanitize_filename(filename),
                    content_type=content_type,
                    byte_size=len(payload),
                    disposition=disposition or "attachment",
                    content_id=part.get("Content-ID"),
                )
            )
            continue

        if content_type == "text/plain" and body_plain is None:
            try:
                body_plain = part.get_content()
            except (LookupError, UnicodeError):
                body_plain = payload.decode("utf-8", errors="replace")
        elif content_type == "text/html" and body_html is None:
            try:
                body_html = part.get_content()
            except (LookupError, UnicodeError):
                body_html = payload.decode("utf-8", errors="replace")

    if body_plain is not None:
        limits.validate_body_length(len(body_plain), full=True)
    if body_html is not None:
        limits.validate_body_length(len(body_html), full=True)

    return EmailMessage(
        reference=ref,
        sender=sender,
        recipients=recipients,
        reply_to=(_addresses(msg.get("Reply-To")) or [None])[0],
        subject=_decode(msg.get("Subject")),
        date=_date(msg.get("Date")),
        body_plain=body_plain,
        body_html=body_html,
        attachments=attachments,
        provider_metadata={
            "message_id": msg.get("Message-ID"),
            "in_reply_to": msg.get("In-Reply-To"),
            "references": msg.get("References"),
            "mime_version": msg.get("MIME-Version"),
            "content_type": msg.get_content_type(),
        },
    )
