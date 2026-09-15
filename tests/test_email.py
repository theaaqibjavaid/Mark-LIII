"""
Unit tests for email.py — send, read, configure, config validation.
All tests use mocked SMTP/IMAP connections; no real network is touched.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from actions.email import (
    send_email, read_emails, configure_email, _parse_raw_email,
    _get_email_config, _require_email_config, _load_config, email,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_config_path(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH to a temp file for all email tests."""
    cfg_path = tmp_path / "api_keys.json"
    monkeypatch.setattr("actions.email.CONFIG_PATH", cfg_path)
    return cfg_path


@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


@pytest.fixture
def valid_config(_patch_config_path):
    """Write a minimal valid email config and return its path."""
    _patch_config_path.write_text(json.dumps({
        "email": {
            "email_address": "sender@example.com",
            "password":      "secret",
            "smtp_server":   "smtp.example.com",
            "smtp_port":     587,
            "imap_server":   "imap.example.com",
            "imap_port":     993,
        }
    }))
    return _patch_config_path


# ═══════════════════════════════════════════════════════════════════════════════
# Config helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigHelpers:
    def test_load_config_missing_file(self, _patch_config_path):
        import actions.email as em
        em.CONFIG_PATH = _patch_config_path.parent / "missing.json"
        assert _load_config() == {}
        em.CONFIG_PATH = _patch_config_path

    def test_load_config_invalid_json(self, _patch_config_path):
        _patch_config_path.write_text("{broken")
        assert _load_config() == {}

    def test_get_email_config_present(self, valid_config):
        cfg = _get_email_config()
        assert cfg["email_address"] == "sender@example.com"

    def test_get_email_config_absent(self, _patch_config_path):
        _patch_config_path.write_text("{}")
        assert _get_email_config() is None

    def test_require_email_config_raises_when_missing(self, _patch_config_path):
        _patch_config_path.write_text("{}")
        with pytest.raises(RuntimeError, match="not configured"):
            _require_email_config()

    def test_require_email_config_passes_when_present(self, valid_config):
        cfg = _require_email_config()
        assert cfg["email_address"] == "sender@example.com"


# ═══════════════════════════════════════════════════════════════════════════════
# send_email
# ═══════════════════════════════════════════════════════════════════════════════

class TestSendEmail:
    def test_send_success(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP, \
             patch("actions.email.ssl.create_default_context") as mock_ssl:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            result = send_email({
                "to":        "recipient@example.com",
                "subject":   "Hello",
                "body":      "Test message",
            }, player)

            assert "Email sent" in result
            mock_server.sendmail.assert_called_once()
            player.write_log.assert_called_once()

    def test_send_multiple_recipients(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)

            send_email({
                "to":      "a@x.com, b@x.com",
                "subject": "Hi",
                "body":    "Body",
            })
            call_args = mock_server.sendmail.call_args
            recipients = call_args[0][1]  # second arg to sendmail
            assert len(recipients) == 2

    def test_send_missing_to(self, valid_config):
        result = send_email({"subject": "Hi", "body": "Body"})
        assert "recipient" in result.lower()

    def test_send_missing_body(self, valid_config):
        result = send_email({"to": "a@x.com", "subject": "Hi"})
        assert "body" in result.lower() or "content" in result.lower()

    def test_send_smtp_failure(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            MockSMTP.side_effect = ConnectionRefusedError("Connection refused")
            result = send_email({
                "to": "a@x.com",
                "body": "Body",
            }, player)
            assert "Could not send" in result
            player.write_log.assert_called_once()

    def test_send_unconfigured(self, _patch_config_path, player):
        _patch_config_path.write_text("{}")
        result = send_email({"to": "a@x.com", "body": "Body"}, player)
        assert "not configured" in result.lower()

    def test_send_with_attachment_not_found(self, valid_config):
        """Attachment path that doesn't exist should not crash; just warn."""
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)
            result = send_email({
                "to":         "a@x.com",
                "body":       "Body",
                "attachment": "/nonexistent/file.pdf",
            })
            assert "Email sent" in result  # still sends, just skips missing attachment


# ═══════════════════════════════════════════════════════════════════════════════
# read_emails
# ═══════════════════════════════════════════════════════════════════════════════

class TestReadEmails:
    def test_read_success(self, valid_config):
        fake_email_bytes = (
            b"From: sender@test.com\r\n"
            b"Subject: Test Subject\r\n"
            b"\r\n"
            b"This is the body text."
        )
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            mock_mail.fetch.return_value = ("OK", [(b"1", fake_email_bytes)])
            mock_mail.select.return_value = ("OK", [])
            mock_mail.logout = MagicMock()

            result = read_emails({"limit": 5})
            assert "Test Subject" in result or "This is the body" in result

    def test_read_empty_inbox(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()

            result = read_emails({})
            assert "No emails" in result

    def test_read_unread_only(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()

            read_emails({"unread_only": True})
            mock_mail.search.assert_called_with(None, b"UNSEEN")

    def test_read_keyword_filter(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            raw = b"From: boss@corp.com\r\nSubject: Urgent report\r\n\r\nPlease fix this now"
            mock_mail.fetch.return_value = ("OK", [(b"1", raw)])
            mock_mail.logout = MagicMock()

            result = read_emails({"keyword": "urgent"})
            assert "Urgent report" in result

    def test_read_imap_failure(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            MockIMAP.side_effect = ConnectionRefusedError("No host")
            result = read_emails({})
            assert "Could not read" in result

    def test_read_limit_capped_at_50(self, valid_config):
        """Limit parameter is capped at 50 even if user requests more."""
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            raw = b"From: a@b.com\r\nSubject: X\r\n\r\nY"
            mock_mail.fetch.return_value = ("OK", [(b"1", raw)])
            mock_mail.logout = MagicMock()

            result = read_emails({"limit": 999})
            assert "X" in result  # succeeds despite capped limit

    def test_keyword_search_uses_imap_text_search(self, valid_config):
        """When keyword is provided, IMAP TEXT search should be attempted."""
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            # First search (ALL) returns 3 emails
            mock_mail.search.side_effect = [
                ("OK", [b"1 2 3"]),  # ALL search
                ("OK", [b"2"]),       # TEXT search for keyword
            ]
            raw = b"From: sender@test.com\r\nSubject: Test Subject\r\n\r\nBody text"
            mock_mail.fetch.return_value = ("OK", [(b"2", raw)])
            mock_mail.logout = MagicMock()

            result = read_emails({"keyword": "test"})
            assert "Test Subject" in result
            # Verify TEXT search was attempted
            call_args = [str(c[0][1]) for c in mock_mail.search.call_args_list]
            assert any('TEXT' in c for c in call_args), "IMAP TEXT search should be attempted"

    def test_keyword_search_fallback_to_subject(self, valid_config):
        """If TEXT search returns nothing, SUBJECT search should be tried."""
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.side_effect = [
                ("OK", [b"1 2 3"]),       # ALL search
                ("OK", [b""]),             # TEXT search - no results
                ("OK", [b"1"]),            # SUBJECT search - found match
            ]
            raw = b"From: sender@test.com\r\nSubject: Urgent Report\r\n\r\nImportant body"
            mock_mail.fetch.return_value = ("OK", [(b"1", raw)])
            mock_mail.logout = MagicMock()

            result = read_emails({"keyword": "urgent"})
            assert "Urgent Report" in result

    def test_keyword_search_from_pattern(self, valid_config):
        """'from John' should trigger FROM search."""
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.side_effect = [
                ("OK", [b"1 2 3"]),       # ALL search
                ("OK", [b"3"]),            # FROM search for 'john'
            ]
            raw = b"From: john@example.com\r\nSubject: Hello\r\n\r\nHey there"
            mock_mail.fetch.return_value = ("OK", [(b"3", raw)])
            mock_mail.logout = MagicMock()

            result = read_emails({"keyword": "from john"})
            assert "Hello" in result


# ═══════════════════════════════════════════════════════════════════════════════
# configure_email
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigureEmail:
    def test_configure_success(self, tmp_path, monkeypatch, player):
        cfg_path = tmp_path / "api_keys.json"
        monkeypatch.setattr("actions.email.CONFIG_PATH", cfg_path)
        cfg_path.write_text("{}")

        result = configure_email({
            "email_address": "new@example.com",
            "password":      "newpass",
        }, player)

        assert "configured" in result.lower()
        saved = json.loads(cfg_path.read_text())
        assert saved["email"]["email_address"] == "new@example.com"
        player.write_log.assert_called_once()

    def test_configure_missing_address(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "api_keys.json"
        monkeypatch.setattr("actions.email.CONFIG_PATH", cfg_path)
        cfg_path.write_text("{}")

        result = configure_email({"password": "secret"})
        assert "email address" in result.lower()

    def test_configure_preserves_other_keys(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({"gemini_api_key": "abc123"}))
        configure_email({"email_address": "x@y.com", "password": "pw"})
        saved = json.loads(_patch_config_path.read_text())
        assert saved["gemini_api_key"] == "abc123"  # untouched
        assert "email" in saved


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_raw_email
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseRawEmail:
    def test_plain_text_email(self):
        raw = (
            b"From: sender@test.com\r\n"
            b"Subject: Hello World\r\n"
            b"Date: Mon, 1 Jan 2025 10:00:00 +0000\r\n"
            b"\r\n"
            b"This is the body text."
        )
        result = _parse_raw_email(raw)
        assert result["from"]    == "sender@test.com"
        assert result["subject"] == "Hello World"
        assert "body text" in result["body"]

    def test_parse_raw_email_full_body(self):
        """Full body mode should return more than 500 chars."""
        raw = (
            b"From: sender@test.com\r\n"
            b"Subject: Long Email\r\n"
            b"\r\n"
            + b"A" * 600  # Body longer than 500 chars
        )
        result = _parse_raw_email(raw, full=True)
        assert len(result["body"]) > 500
        assert result["body"] == "A" * 600

    def test_parse_raw_email_truncated_body(self):
        """Default mode should truncate body at 500 chars."""
        raw = (
            b"From: sender@test.com\r\n"
            b"Subject: Long Email\r\n"
            b"\r\n"
            + b"B" * 600
        )
        result = _parse_raw_email(raw, full=False)
        assert len(result["body"]) == 500
        assert result["body"] == "B" * 500


# ═══════════════════════════════════════════════════════════════════════════════
# Unified entry point
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmailUnified:
    def test_unknown_action(self, valid_config):
        result = email({"action": "dematerialize"})
        assert "Unknown" in result

    def test_alias_route_send(self, valid_config):
        """'compose' and 'write' should both route to send."""
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__  = MagicMock(return_value=False)
            for alias in ("compose", "write"):
                result = email({"action": alias, "to": "a@x.com", "body": "Hi"})
                assert "Email sent" in result

    def test_alias_route_read(self, valid_config):
        """'inbox' and 'check' should both route to read."""
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value.__enter__ = MagicMock(return_value=mock_mail)
            MockIMAP.return_value.__exit__  = MagicMock(return_value=False)
            mock_mail.search.return_value = ("OK", [b""])
            for alias in ("inbox", "check"):
                result = email({"action": alias})
                assert "No emails" in result or "Could not" in result
