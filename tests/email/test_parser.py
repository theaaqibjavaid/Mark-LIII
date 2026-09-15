from email.message import EmailMessage
from email.policy import SMTP

import pytest

from core.email.models import EmailMessageRef
from core.email.parser import parse_message


REF = EmailMessageRef("acct", "INBOX", "42")


def raw_message(*, plain=None, html=None, attachments=()):
    msg = EmailMessage(policy=SMTP)
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "Bob <bob@example.com>"
    msg["Subject"] = "Résumé — Привет"
    msg["Date"] = "Tue, 15 Sep 2026 10:00:00 +0530"
    msg["Message-ID"] = "<m42@example.com>"
    if plain is not None and html is not None:
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")
    elif html is not None:
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(plain or "")
    for filename, data, ctype in attachments:
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes()


def test_parser_preserves_plain_and_html_bodies():
    result = parse_message(raw_message(plain="plain", html="<p>html</p>"), reference=REF)
    assert result.reference == REF
    assert result.body_plain == "plain\n"
    assert result.body_html == "<p>html</p>\n"


def test_parser_handles_plain_html_only_and_empty_bodies():
    assert parse_message(raw_message(plain="plain"), reference=REF).body_plain == "plain\n"
    assert parse_message(raw_message(html="<p>html</p>"), reference=REF).body_html == "<p>html</p>\n"
    assert parse_message(raw_message(plain=""), reference=REF).body_plain == "\n"


def test_parser_extracts_headers_addresses_reply_metadata_and_date():
    msg = EmailMessage(policy=SMTP)
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "Bob <bob@example.com>"
    msg["Cc"] = "Carol <carol@example.com>"
    msg["Reply-To"] = "reply@example.com"
    msg["Subject"] = "Hello"
    msg["Date"] = "Tue, 15 Sep 2026 10:00:00 +0530"
    msg["Message-ID"] = "<child@example.com>"
    msg["In-Reply-To"] = "<parent@example.com>"
    msg["References"] = "<root@example.com> <parent@example.com>"
    msg.set_content("body")

    result = parse_message(msg.as_bytes(), reference=REF)
    assert result.sender.address == "alice@example.com"
    assert [a.address for a in result.recipients] == ["bob@example.com", "carol@example.com"]
    assert result.reply_to.address == "reply@example.com"
    assert result.subject == "Hello"
    assert result.date is not None and result.date.utcoffset().total_seconds() == 19800
    assert result.provider_metadata["message_id"] == "<child@example.com>"
    assert result.provider_metadata["in_reply_to"] == "<parent@example.com>"
    assert result.provider_metadata["references"] == "<root@example.com> <parent@example.com>"


def test_parser_extracts_multiple_attachments_and_inline_content_id():
    msg = EmailMessage(policy=SMTP)
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg.set_content("body")
    msg.add_attachment(b"one", maintype="application", subtype="octet-stream", filename="one.bin")
    msg.add_attachment(b"two", maintype="text", subtype="plain", filename="two.txt", disposition="inline", cid="cid-2")

    result = parse_message(msg.as_bytes(), reference=REF)
    assert [a.filename for a in result.attachments] == ["one.bin", "two.txt"]
    assert [a.byte_size for a in result.attachments] == [3, 3]
    assert result.attachments[1].content_id == "<cid-2>"
    assert result.attachments[1].disposition == "inline"


def test_parser_sanitizes_path_traversal_filename():
    raw = raw_message(plain="body", attachments=[("../../secret.txt", b"x", "text/plain")])
    result = parse_message(raw, reference=REF)
    assert result.attachments[0].filename == "secret.txt"


def test_parser_handles_encoded_filename_and_header_values():
    raw = raw_message(plain="Café — 你好", attachments=[("résumé — 测试.txt", b"data", "text/plain")])
    result = parse_message(raw, reference=REF)
    assert result.subject == "Résumé — Привет"
    assert result.body_plain == "Café — 你好\n"
    assert result.attachments[0].filename == "résumé — 测试.txt"


def test_parser_rejects_oversized_message_and_attachment():
    with pytest.raises(ValueError, match="Message size"):
        parse_message(b"x" * (50 * 1024 * 1024 + 1), reference=REF)

    huge = EmailMessage(policy=SMTP)
    huge["From"] = "a@example.com"
    huge["To"] = "b@example.com"
    huge.set_content("body")
    huge.add_attachment(b"x" * (25 * 1024 * 1024 + 1), maintype="application", subtype="octet-stream", filename="huge.bin")
    with pytest.raises(ValueError, match="Attachment size"):
        parse_message(huge.as_bytes(), reference=REF)


def test_parser_rejects_more_than_maximum_attachments():
    msg = EmailMessage(policy=SMTP)
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg.set_content("body")
    for i in range(11):
        msg.add_attachment(str(i).encode(), maintype="text", subtype="plain", filename=f"{i}.txt")
    with pytest.raises(ValueError, match="Attachment count"):
        parse_message(msg.as_bytes(), reference=REF)


def test_parser_does_not_execute_payloads_and_treats_malformed_headers_as_data():
    raw = (
        b"From: a@example.com\r\n"
        b"To: b@example.com\r\n"
        b"Subject: =?badcharset?Q?hello?=\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"body\r\n"
    )
    result = parse_message(raw, reference=REF)
    assert result.body_plain == "body\n"
    assert "hello" in result.subject.lower()


def test_parser_uses_safe_default_reference_when_not_supplied():
    result = parse_message(raw_message(plain="body"))
    assert result.reference.account_id == "unknown"
    assert result.reference.mailbox == "unknown"
    assert result.reference.uid == "unknown"
