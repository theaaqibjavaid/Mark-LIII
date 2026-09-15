"""Standards-compliant MIME construction for outbound email."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, make_msgid
from typing import Iterable, Optional

from .limits import EmailLimits
from .models import EmailAddress


@dataclass(frozen=True)
class OutboundAttachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    disposition: str = "attachment"
    content_id: Optional[str] = None
    declared_size: Optional[int] = None


def _safe_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "_", name)
    if name in {"", ".", ".."}:
        return "attachment"
    return name


def _validate_address(address: EmailAddress) -> None:
    if not address.address or "@" not in address.address:
        raise ValueError(f"Invalid recipient address: {address.address!r}")
    local, domain = address.address.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise ValueError(f"Invalid recipient address: {address.address!r}")


def _set_date(msg: EmailMessage, date: datetime | str | None) -> None:
    if isinstance(date, str):
        msg["Date"] = date
    elif isinstance(date, datetime):
        msg["Date"] = format_datetime(date)
    else:
        msg["Date"] = format_datetime(datetime.now(timezone.utc))


def _build_body(
    body_plain: Optional[str], body_html: Optional[str], *, inline: list[OutboundAttachment]
) -> EmailMessage:
    body = EmailMessage(policy=SMTP)
    if body_plain is not None and body_html is not None:
        body.set_content(body_plain)
        body.add_alternative(body_html, subtype="html")
    elif body_html is not None:
        body.set_content(body_html, subtype="html")
    else:
        body.set_content(body_plain or "")

    if inline:
        body.make_related()
        for attachment in inline:
            maintype, subtype = attachment.content_type.split("/", 1) if "/" in attachment.content_type else ("application", "octet-stream")
            kwargs = {"filename": _safe_filename(attachment.filename), "disposition": "inline"}
            if attachment.content_id:
                kwargs["cid"] = attachment.content_id.strip("<>")
            body.add_attachment(attachment.content, maintype=maintype, subtype=subtype, **kwargs)
    return body


def build_outbound_message(
    *,
    sender: EmailAddress,
    recipients: Iterable[EmailAddress],
    subject: str,
    body_plain: Optional[str] = None,
    body_html: Optional[str] = None,
    attachments: Optional[Iterable[OutboundAttachment]] = None,
    cc: Optional[Iterable[EmailAddress]] = None,
    bcc: Optional[Iterable[EmailAddress]] = None,
    reply_to: Optional[EmailAddress] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[Iterable[str]] = None,
    date: Optional[datetime | str] = None,
    message_id: Optional[str] = None,
) -> bytes:
    """Build an RFC-compatible message and return serialized bytes."""
    if body_plain is None and body_html is None:
        raise ValueError("At least one email body (plain or html) is required")
    EmailLimits.validate_subject_length(len(subject))

    to = list(recipients)
    cc_list = list(cc or [])
    bcc_list = list(bcc or [])
    all_recipients = to + cc_list + bcc_list
    if not all_recipients:
        raise ValueError("At least one recipient is required")
    EmailLimits.validate_recipient_count(len(all_recipients))
    _validate_address(sender)
    for address in all_recipients:
        _validate_address(address)
    if reply_to:
        _validate_address(reply_to)

    parts = list(attachments or [])
    if len(parts) > EmailLimits.MAX_ATTACHMENTS_PER_MESSAGE:
        raise ValueError("Attachment count exceeds configured limit")
    total = 0
    for attachment in parts:
        if not isinstance(attachment.content, bytes):
            raise TypeError("Attachment content must be bytes")
        size = attachment.declared_size if attachment.declared_size is not None else len(attachment.content)
        EmailLimits.validate_attachment_size(size)
        total += size
    EmailLimits.validate_total_attachment_size(total)

    inline = [a for a in parts if a.disposition.lower() == "inline"]
    regular = [a for a in parts if a.disposition.lower() != "inline"]
    body = _build_body(body_plain, body_html, inline=inline)

    msg = EmailMessage(policy=SMTP)
    msg["From"] = sender.format()
    msg["To"] = ", ".join(a.format() for a in to)
    if cc_list:
        msg["Cc"] = ", ".join(a.format() for a in cc_list)
    if bcc_list:
        msg["Bcc"] = ", ".join(a.format() for a in bcc_list)
    msg["Subject"] = subject
    _set_date(msg, date)
    msg["Message-ID"] = message_id or make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to.format()
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)

    # Transfer the prepared body tree into the root. make_* preserves the
    # body structure and lets the stdlib choose correct MIME boundaries.
    msg.set_payload(body)
    if body.is_multipart():
        msg.set_type(body.get_content_type())
        msg.set_boundary(body.get_boundary())
        msg.set_payload(body.get_payload())
        for key in ("Content-Type", "Content-Transfer-Encoding", "MIME-Version"):
            if key in body and key != "Content-Type":
                msg[key] = body[key]
        if body.get_content_type() == "multipart/related":
            msg.set_payload(body.get_payload())
            msg["MIME-Version"] = "1.0"
    else:
        msg.set_content(body.get_content(), subtype=body.get_content_subtype(), charset="utf-8")

    if regular:
        # Rebuild the root as multipart/mixed around the complete body tree.
        headers = [(k, msg[k]) for k in ("From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID", "Reply-To", "In-Reply-To", "References") if msg.get(k) is not None]
        mixed = EmailMessage(policy=SMTP)
        for key, value in headers:
            mixed[key] = value
        mixed.make_mixed()
        mixed.attach(body)
        for attachment in regular:
            maintype, subtype = attachment.content_type.split("/", 1) if "/" in attachment.content_type else ("application", "octet-stream")
            kwargs = {"filename": _safe_filename(attachment.filename), "disposition": "attachment"}
            if attachment.content_id:
                kwargs["cid"] = attachment.content_id.strip("<>")
            mixed.add_attachment(attachment.content, maintype=maintype, subtype=subtype, **kwargs)
        msg = mixed

    raw = msg.as_bytes(policy=SMTP)
    EmailLimits.validate_message_size(len(raw))
    return raw
