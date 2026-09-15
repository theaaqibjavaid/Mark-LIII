from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

import pytest

from core.email.mime import OutboundAttachment, build_outbound_message
from core.email.models import EmailAddress

SENDER = EmailAddress("Alice <Alice@Example.COM>")
TO = [EmailAddress("Bob <bob@example.com>")]


def parse(raw: bytes):
    return BytesParser(policy=policy.default).parsebytes(raw)


def test_build_plain_text_message_is_standards_compliant():
    raw = build_outbound_message(sender=SENDER, recipients=TO, subject="Hello", body_plain="Plain body", date="Tue, 15 Sep 2026 10:00:00 +0530", message_id="<test-plain@example.com>")
    msg = parse(raw)
    assert msg["From"] == "Alice <Alice@example.com>"
    assert parseaddr(msg["To"])[1] == "bob@example.com"
    assert msg["Subject"] == "Hello"
    assert msg["Message-ID"] == "<test-plain@example.com>"
    assert msg.get_content_type() == "text/plain"
    assert msg.get_content().replace("\r\n", "\n") == "Plain body\n"


def test_build_html_only_message_preserves_html():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="HTML", body_html="<html><body><strong>Hello</strong></body></html>"))
    assert msg.get_content_type() == "text/html"
    assert "<strong>Hello</strong>" in msg.get_content()


def test_build_plain_and_html_uses_multipart_alternative():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Alternative", body_plain="Plain", body_html="<p>HTML</p>"))
    assert msg.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in msg.iter_parts()] == ["text/plain", "text/html"]


def test_build_attachments_wrap_alternative_inside_mixed():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Files", body_plain="See attached", body_html="<p>See attached</p>", attachments=[OutboundAttachment("report.txt", b"report", "text/plain")]))
    parts = list(msg.iter_parts())
    assert msg.get_content_type() == "multipart/mixed"
    assert parts[0].get_content_type() == "multipart/alternative"
    assert parts[1].get_filename() == "report.txt"
    assert parts[1].get_payload(decode=True) == b"report"


def test_build_inline_image_is_nested_related():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Inline", body_html='<img src="cid:logo@example.com">', attachments=[OutboundAttachment("logo.png", b"PNGDATA", "image/png", disposition="inline", content_id="<logo@example.com>")]))
    assert msg.get_content_type() == "multipart/related"
    image = next(part for part in msg.walk() if part.get_content_type() == "image/png")
    assert image["Content-ID"] == "<logo@example.com>"
    assert image.get_content_disposition() == "inline"


def test_build_multiple_attachments_preserves_order_and_bytes():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Multiple", body_plain="body", attachments=[OutboundAttachment("a.bin", b"A"), OutboundAttachment("b.bin", b"BB")]))
    attachments = list(msg.iter_attachments())
    assert [p.get_filename() for p in attachments] == ["a.bin", "b.bin"]
    assert [p.get_payload(decode=True) for p in attachments] == [b"A", b"BB"]


def test_build_encoded_filename_and_non_ascii_headers_round_trip():
    msg = parse(build_outbound_message(sender=EmailAddress("Jöhn Döe <john@example.com>"), recipients=[EmailAddress("李明 <li@example.com>")], subject="Résumé — Привет", body_plain="Café — Привет — 你好", attachments=[OutboundAttachment("résumé — 测试.txt", "данные".encode(), "text/plain")]))
    assert msg["Subject"] == "Résumé — Привет"
    assert msg["From"] == "Jöhn Döe <john@example.com>"
    body = next(p for p in msg.walk() if p.get_content_type() == "text/plain" and p.get_content_disposition() != "attachment")
    assert body.get_content().replace("\r\n", "\n") == "Café — Привет — 你好\n"
    assert next(p for p in msg.iter_attachments()).get_filename() == "résumé — 测试.txt"


def test_build_reply_metadata_is_correct():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Re: Thread", body_plain="Reply", in_reply_to="<parent@example.com>", references=["<root@example.com>", "<parent@example.com>"], reply_to=EmailAddress("reply@example.com")))
    assert msg["In-Reply-To"] == "<parent@example.com>"
    assert msg["References"] == "<root@example.com> <parent@example.com>"
    assert msg["Reply-To"] == "reply@example.com"


def test_builder_generates_message_id_and_date_when_omitted():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Generated", body_plain="body"))
    assert msg["Message-ID"] and msg["Date"]


def test_builder_rejects_missing_body():
    with pytest.raises(ValueError, match="body"):
        build_outbound_message(sender=SENDER, recipients=TO, subject="Empty")


def test_builder_rejects_invalid_recipient():
    with pytest.raises(ValueError, match="recipient"):
        build_outbound_message(sender=SENDER, recipients=[EmailAddress("not-an-email")], subject="Bad", body_plain="body")


def test_builder_enforces_attachment_count_and_size_limits():
    with pytest.raises(ValueError, match="Attachment"):
        build_outbound_message(sender=SENDER, recipients=TO, subject="Too many", body_plain="body", attachments=[OutboundAttachment(f"{i}.txt", b"x", "text/plain") for i in range(11)])
    with pytest.raises(ValueError, match="Attachment"):
        build_outbound_message(sender=SENDER, recipients=TO, subject="Too large", body_plain="body", attachments=[OutboundAttachment("huge.bin", b"x", declared_size=26 * 1024 * 1024)])


def test_builder_sanitizes_path_traversal_filename():
    msg = parse(build_outbound_message(sender=SENDER, recipients=TO, subject="Safe", body_plain="body", attachments=[OutboundAttachment("../../secret.txt", b"safe", "text/plain")]))
    assert next(p for p in msg.iter_attachments()).get_filename() == "secret.txt"
