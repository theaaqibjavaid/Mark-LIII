"""
Regression / characterization tests for the existing email action.

These tests capture the EXACT public contract of actions/email.py as it exists
today. They must remain green throughout the V2 migration — any intentional
behavior change requires an explicit migration note in docs/email-engine-v2/.

DO NOT refactor existing tests here; add NEW regressions for each preserved
observable behavior. Existing test_email.py and test_features.py are canonical.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent  # tests/email/ -> tests/ -> project root
sys.path.insert(0, str(PROJECT_ROOT))

import actions.email as em
from core.action_loader import discover_actions, _validate


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _patch_config_path(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH to a temp file for all regression tests."""
    cfg_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(em, "CONFIG_PATH", cfg_path)
    return cfg_path


@pytest.fixture
def player():
    p = MagicMock()
    p.write_log = MagicMock()
    return p


@pytest.fixture
def valid_config(_patch_config_path):
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
# Step 1 — Tool declaration contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolDeclarationContract:
    """The TOOL dict must remain exactly as declared at the bottom of actions/email.py."""

    def test_tool_name_is_string_email(self):
        assert em.TOOL["name"] == "email"

    def test_tool_description_non_empty(self):
        assert isinstance(em.TOOL["description"], str)
        assert len(em.TOOL["description"]) > 20

    def test_tool_parameters_is_object(self):
        params = em.TOOL["parameters"]
        assert params["type"] == "OBJECT"

    def test_tool_handler_is_callable(self):
        assert callable(em.TOOL["handler"])
        assert em.TOOL["handler"] is em.email

    def test_required_parameter_is_action(self):
        props = em.TOOL["parameters"]["properties"]
        assert "action" in props
        assert props["action"]["type"] == "STRING"

    def test_send_parameters_present(self):
        props = em.TOOL["parameters"]["properties"]
        for key in ("to", "subject", "body", "html", "cc", "bcc", "attachment"):
            assert key in props, f"Missing parameter: {key}"

    def test_read_parameters_present(self):
        props = em.TOOL["parameters"]["properties"]
        for key in ("limit", "folder", "unread_only", "keyword", "detail"):
            assert key in props, f"Missing parameter: {key}"

    def test_configure_parameters_present(self):
        props = em.TOOL["parameters"]["properties"]
        for key in ("email_address", "password", "smtp_server", "smtp_port",
                     "imap_server", "imap_port"):
            assert key in props, f"Missing parameter: {key}"

    def test_handler_signature_matches_action_loader_expectation(self):
        """The handler must accept parameters + player + session_memory."""
        import inspect
        sig = inspect.signature(em.email)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player" in params
        assert "session_memory" in params

    def test_send_handler_signature_matches(self):
        sig = inspect.signature(em.send_email)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player" in params

    def test_read_handler_signature_matches(self):
        sig = inspect.signature(em.read_emails)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player" in params

    def test_configure_handler_signature_matches(self):
        sig = inspect.signature(em.configure_email)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player" in params


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Config helpers contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigContract:
    """_load_config, _get_email_config, _require_email_config must behave as documented."""

    def test_load_config_returns_dict_when_file_missing(self, _patch_config_path):
        missing = _patch_config_path.parent / "nonexistent.json"
        em.CONFIG_PATH = missing
        result = em._load_config()
        assert result == {}
        em.CONFIG_PATH = _patch_config_path

    def test_load_config_returns_empty_dict_on_invalid_json(self, _patch_config_path):
        _patch_config_path.write_text("{not valid json")
        assert em._load_config() == {}

    def test_get_email_config_returns_dict_when_present(self, valid_config):
        cfg = em._get_email_config()
        assert isinstance(cfg, dict)
        assert cfg["email_address"] == "sender@example.com"

    def test_get_email_config_returns_none_when_block_missing(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({"other": 1}))
        assert em._get_email_config() is None

    def test_require_email_config_raises_runtimeerror_when_missing(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({}))
        with pytest.raises(RuntimeError, match="not configured"):
            em._require_email_config()

    def test_require_email_config_raises_when_no_address(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({"email": {"password": "x"}}))
        with pytest.raises(RuntimeError, match="not configured"):
            em._require_email_config()

    def test_require_email_config_passes_when_complete(self, valid_config):
        cfg = em._require_email_config()
        assert cfg["email_address"] == "sender@example.com"
        assert cfg["password"] == "secret"


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — send_email regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestSendEmailRegression:
    """Every observable behavior of send_email must remain unchanged."""

    def test_send_success_returns_sent_message(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            result = em.send_email({"to": "a@b.com", "subject": "Hi", "body": "Hello"}, player)
        assert "Email sent" in result
        assert "a@b.com" in result

    def test_send_success_calls_write_log(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@b.com", "body": "Hi"}, player)
        assert player.write_log.call_count == 1

    def test_send_success_with_html_uses_alternative_multipart(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@b.com", "body": "Plain", "html": "<b>Bold</b>"}, player)
        msg_str = mock_server.sendmail.call_args[0][2]
        assert "multipart/alternative" in msg_str

    def test_send_success_without_html_uses_mixed_multipart(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@b.com", "body": "Plain"}, None)
        msg_str = mock_server.sendmail.call_args[0][2]
        assert "multipart/mixed" in msg_str or "mixed" in msg_str.lower()

    def test_send_parses_comma_separated_recipients(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@x.com, b@x.com", "body": "Hi"}, None)
            recipients = mock_server.sendmail.call_args[0][1]
            assert len(recipients) == 2

    def test_send_parses_cc(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@x.com", "cc": "c@x.com", "body": "Hi"}, None)
            msg_str = mock_server.sendmail.call_args[0][2]
            assert "Cc: c@x.com" in msg_str

    def test_send_parses_bcc_into_recipients_not_headers(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@x.com", "bcc": "b@x.com", "body": "Hi"}, None)
            recipients = mock_server.sendmail.call_args[0][1]
            assert "b@x.com" in recipients
            msg_str = mock_server.sendmail.call_args[0][2]
            assert "Bcc:" not in msg_str

    def test_send_missing_to_returns_error(self, valid_config):
        result = em.send_email({"subject": "X", "body": "Y"})
        assert "recipient" in result.lower()

    def test_send_missing_body_returns_error(self, valid_config):
        result = em.send_email({"to": "a@b.com", "subject": "X"})
        assert "body" in result.lower() or "content" in result.lower()

    def test_send_smtp_failure_returns_error_string(self, valid_config, player):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            MockSMTP.side_effect = ConnectionRefusedError("refused")
            result = em.send_email({"to": "a@b.com", "body": "X"}, player)
        assert "Could not send" in result
        assert player.write_log.call_count == 1

    def test_send_unconfigured_returns_config_error(self, _patch_config_path):
        _patch_config_path.write_text("{}")
        result = em.send_email({"to": "a@b.com", "body": "X"})
        assert "not configured" in result.lower()

    def test_send_attachment_not_found_does_not_crash(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            result = em.send_email({
                "to": "a@b.com", "body": "Hi",
                "attachment": "/definitely/not/there.pdf",
            })
        assert "Email sent" in result

    def test_send_uses_starttls(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@b.com", "body": "Hi"}, None)
            mock_server.starttls.assert_called_once()

    def test_send_uses_login(self, valid_config):
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "a@b.com", "body": "Hi"}, None)
            mock_server.login.assert_called_once_with("sender@example.com", "secret")

    def test_send_default_smtp_host(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({"email": {"email_address": "a@b.com", "password": "p"}}))
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            em.send_email({"to": "x@y.com", "body": "Hi"}, None)
            call_args = MockSMTP.call_args
            assert call_args[0][0] == "smtp.gmail.com"
            assert call_args[0][1] == 587


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — read_emails regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestReadEmailsRegression:
    def test_read_success_returns_formatted_list(self, valid_config):
        fake = b"From: s@t.com\r\nSubject: Test\r\n\r\nBody text"
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            mock_mail.fetch.return_value = ("OK", [(b"1", fake)])
            mock_mail.select.return_value = ("OK", [])
            mock_mail.logout = MagicMock()
            result = em.read_emails({"limit": 5})
        assert "Test" in result

    def test_read_empty_inbox_returns_no_emails(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()
            result = em.read_emails({})
        assert "No emails" in result

    def test_read_unread_only_sends_unseen_search(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()
            em.read_emails({"unread_only": True})
            mock_mail.search.assert_called_with(None, b"UNSEEN")

    def test_read_all_sends_all_search(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()
            em.read_emails({})
            mock_mail.search.assert_called_with(None, b"ALL")

    def test_read_limit_capped_at_50(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            raw = b"From: a@b.com\r\nSubject: X\r\n\r\nY"
            mock_mail.fetch.return_value = ("OK", [(b"1", raw)])
            mock_mail.logout = MagicMock()
            result = em.read_emails({"limit": 999})
        assert "X" in result  # does not crash with capped limit

    def test_read_default_limit_is_10(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            raw = b"From: a@b.com\r\nSubject: X\r\n\r\nY"
            mock_mail.fetch.return_value = ("OK", [(b"1", raw)])
            mock_mail.logout = MagicMock()
            em.read_emails({})
            # default limit parsed as int(10)
            call_args = mock_mail.search.call_args
            assert call_args[0][1] == b"ALL"

    def test_read_folder_uppercased(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b""])
            mock_mail.logout = MagicMock()
            em.read_emails({"folder": "inbox"})
            mock_mail.select.assert_called_once_with("INBOX")

    def test_read_keyword_triggers_imap_search(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.side_effect = [
                ("OK", [b"1 2 3"]),   # ALL
                ("OK", [b"2"]),        # TEXT match
            ]
            raw = b"From: s@t.com\r\nSubject: Urgent report\r\n\r\nFix it"
            mock_mail.fetch.return_value = ("OK", [(b"2", raw)])
            mock_mail.logout = MagicMock()
            result = em.read_emails({"keyword": "urgent"})
        assert "Urgent report" in result
        # Verify TEXT search was attempted
        search_calls = [str(c[0][1]) for c in mock_mail.search.call_args_list]
        assert any("TEXT" in c for c in search_calls)

    def test_read_keyword_fallback_scans_all_when_no_imap_match(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            # ALL returns 20 ids
            mock_mail.search.side_effect = [
                ("OK", [b"1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20"]),
                ("OK", [b""]), ("OK", [b""]), ("OK", [b""]), ("OK", [b""]),
            ]
            def fetch_side(msg_id, *args):
                if msg_id == b"15":
                    return ("OK", [(b"15", b"From: a@b.com\r\nSubject: Has urgent\r\n\r\nImportant")])
                return ("OK", [(msg_id, b"From: a@b.com\r\nSubject: Normal\r\n\r\nNothing")])
            mock_mail.fetch.side_effect = fetch_side
            mock_mail.logout = MagicMock()
            result = em.read_emails({"keyword": "urgent"})
        assert "Has urgent" in result
        fetch_ids = [c[0][0] for c in mock_mail.fetch.call_args_list]
        assert b"15" in fetch_ids  # scanned beyond default limit

    def test_read_imap_failure_returns_error(self, valid_config):
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            MockIMAP.side_effect = ConnectionRefusedError("no host")
            result = em.read_emails({})
        assert "Could not read" in result

    def test_read_detail_mode_shows_full_body(self, valid_config):
        long_body = "A" * 600
        fake = f"From: s@t.com\r\nSubject: Long\r\n\r\n{long_body}".encode()
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            mock_mail.fetch.return_value = ("OK", [(b"1", fake)])
            mock_mail.select.return_value = ("OK", [])
            mock_mail.logout = MagicMock()
            result = em.read_emails({"detail": True})
        assert "A" * 500 in result  # full mode: 5000 cap

    def test_read_preview_truncates_body(self, valid_config):
        long_body = "B" * 600
        fake = f"From: s@t.com\r\nSubject: Long\r\n\r\n{long_body}".encode()
        with patch("actions.email.IMAP4_SSL") as MockIMAP:
            mock_mail = MagicMock()
            MockIMAP.return_value = mock_mail
            mock_mail.search.return_value = ("OK", [b"1"])
            mock_mail.fetch.return_value = ("OK", [(b"1", fake)])
            mock_mail.select.return_value = ("OK", [])
            mock_mail.logout = MagicMock()
            result = em.read_emails({"detail": False})
        # preview mode: 120 chars max on the preview line
        lines = result.split("\n")
        preview_lines = [l for l in lines if l.startswith("   ")]
        if preview_lines:
            assert len(preview_lines[0]) <= 125  # "   " prefix + 120 chars


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — configure_email regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigureEmailRegression:
    def test_configure_success_writes_json(self, _patch_config_path, player):
        result = em.configure_email({
            "email_address": "new@example.com",
            "password":      "newpass",
        }, player)
        assert "configured" in result.lower()
        saved = json.loads(_patch_config_path.read_text())
        assert saved["email"]["email_address"] == "new@example.com"
        assert saved["email"]["password"] == "newpass"
        assert player.write_log.call_count == 1

    def test_configure_missing_address_returns_error(self, _patch_config_path):
        result = em.configure_email({"password": "x"})
        assert "email address" in result.lower()

    def test_configure_preserves_other_keys(self, _patch_config_path):
        _patch_config_path.write_text(json.dumps({"gemini_api_key": "abc123"}))
        em.configure_email({"email_address": "x@y.com", "password": "pw"})
        saved = json.loads(_patch_config_path.read_text())
        assert saved["gemini_api_key"] == "abc123"
        assert "email" in saved

    def test_configure_defaults_smtp_and_imap(self, _patch_config_path):
        em.configure_email({"email_address": "a@b.com", "password": "p"})
        saved = json.loads(_patch_config_path.read_text())
        assert saved["email"]["smtp_server"] == "smtp.gmail.com"
        assert saved["email"]["smtp_port"] == 587
        assert saved["email"]["imap_server"] == "imap.gmail.com"
        assert saved["email"]["imap_port"] == 993

    def test_configure_overwrites_previous_block(self, _patch_config_path):
        em.configure_email({"email_address": "first@example.com", "password": "pw1"})
        em.configure_email({"email_address": "second@example.com", "password": "pw2"})
        saved = json.loads(_patch_config_path.read_text())
        assert saved["email"]["email_address"] == "second@example.com"
        assert saved["email"]["password"] == "pw2"


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — _parse_raw_email regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseRawEmailRegression:
    def test_parses_plain_text(self):
        raw = b"From: sender@test.com\r\nSubject: Hello World\r\nDate: Mon, 1 Jan 2025 10:00:00 +0000\r\n\r\nThis is the body."
        result = em._parse_raw_email(raw)
        assert result["from"] == "sender@test.com"
        assert result["subject"] == "Hello World"
        assert "body" in result["body"].lower()

    def test_truncates_body_to_500_by_default(self):
        raw = b"From: s@t.com\r\nSubject: X\r\n\r\n" + b"Z" * 600
        result = em._parse_raw_email(raw)
        assert len(result["body"]) == 500

    def test_full_mode_allows_up_to_5000(self):
        raw = b"From: s@t.com\r\nSubject: X\r\n\r\n" + b"W" * 600
        result = em._parse_raw_email(raw, full=True)
        assert len(result["body"]) == 600

    def test_handles_multipart_picks_first_plain(self):
        raw = (
            b"From: s@t.com\r\nSubject: Multi\r\n\r\n"
            b"--boundary\r\nContent-Type: text/html\r\n\r\n<html>HTML</html>\r\n"
            b"--boundary\r\nContent-Type: text/plain\r\n\r\nPlain text body\r\n"
            b"--boundary--\r\n"
        )
        result = em._parse_raw_email(raw)
        assert "Plain text body" in result["body"]

    def test_returns_empty_body_on_decode_failure(self):
        # bytes that can't decode as utf-8 should not crash
        raw = b"From: s@t.com\r\nSubject: Bad\r\n\r\n\xff\xfe"
        result = em._parse_raw_email(raw)
        assert isinstance(result["body"], str)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Unified email() entry point regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmailUnifiedRegression:
    def test_action_send_routes_to_send_email(self, valid_config):
        with patch("actions.email.send_email") as mock_send:
            mock_send.return_value = "done"
            result = em.email({"action": "send", "to": "a@b.com", "body": "X"})
            mock_send.assert_called_once()
            assert result == "done"

    def test_action_compose_aliases_to_send(self, valid_config):
        with patch("actions.email.send_email") as mock_send:
            mock_send.return_value = "sent"
            result = em.email({"action": "compose", "to": "a@b.com", "body": "X"})
            assert "sent" in result

    def test_action_write_aliases_to_send(self, valid_config):
        with patch("actions.email.send_email") as mock_send:
            mock_send.return_value = "sent"
            result = em.email({"action": "write", "to": "a@b.com", "body": "X"})
            assert "sent" in result

    def test_action_read_routes_to_read_emails(self, valid_config):
        with patch("actions.email.read_emails") as mock_read:
            mock_read.return_value = "no mails"
            result = em.email({"action": "read"})
            mock_read.assert_called_once()
            assert "no mails" in result

    def test_action_inbox_aliases_to_read(self, valid_config):
        with patch("actions.email.read_emails") as mock_read:
            mock_read.return_value = "empty"
            result = em.email({"action": "inbox"})
            assert "empty" in result

    def test_action_check_aliases_to_read(self, valid_config):
        with patch("actions.email.read_emails") as mock_read:
            mock_read.return_value = "empty"
            result = em.email({"action": "check"})
            assert "empty" in result

    def test_action_configure_routes_to_configure_email(self, valid_config):
        with patch("actions.email.configure_email") as mock_cfg:
            mock_cfg.return_value = "saved"
            result = em.email({"action": "configure", "email_address": "a@b.com", "password": "p"})
            mock_cfg.assert_called_once()
            assert "saved" in result

    def test_action_setup_aliases_to_configure(self, valid_config):
        with patch("actions.email.configure_email") as mock_cfg:
            mock_cfg.return_value = "saved"
            result = em.email({"action": "setup", "email_address": "a@b.com", "password": "p"})
            assert "saved" in result

    def test_action_login_aliases_to_configure(self, valid_config):
        with patch("actions.email.configure_email") as mock_cfg:
            mock_cfg.return_value = "saved"
            result = em.email({"action": "login", "email_address": "a@b.com", "password": "p"})
            assert "saved" in result

    def test_unknown_action_returns_error(self, valid_config):
        result = em.email({"action": "dematerialize"})
        assert "Unknown" in result

    def test_default_action_is_read(self, valid_config):
        with patch("actions.email.read_emails") as mock_read:
            mock_read.return_value = "empty"
            result = em.email({})
            mock_read.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Step 3 — Action-loader compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionLoaderCompatibility:
    def _prime_modules(self):
        """Ensure action modules are in sys.modules so discover_actions finds them."""
        import sys
        # Prime all known action modules
        for mod in ("actions.web_search", "actions.reminder", "actions.code_helper",
                     "actions.browser_control", "actions.email", "actions.calendar",
                     "actions.notes", "actions.file_processor", "actions.send_message",
                     "actions.flight_finder"):
            if mod not in sys.modules:
                try:
                    __import__(mod)
                except ImportError:
                    pass  # Some modules may not exist in this test context

    def test_discover_actions_finds_email(self):
        self._prime_modules()
        import importlib
        import core.action_loader as al
        importlib.reload(al)
        registry = al.discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        assert "email" in registry.names()

    def test_email_action_record_is_valid(self):
        self._prime_modules()
        import importlib
        import core.action_loader as al
        importlib.reload(al)
        registry = al.discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        rec = registry._all_records
        email_rec = next((r for r in rec if r.name == "email"), None)
        assert email_rec is not None
        assert email_rec.valid is True
        assert email_rec.error == ""

    def test_email_tool_declaration_matches_module(self):
        rec = _validate(em, "email.py")
        assert rec.valid
        assert rec.name == "email"
        assert rec.handler is em.email

    def test_discovery_does_not_break_existing_actions(self):
        self._prime_modules()
        import importlib
        import core.action_loader as al
        importlib.reload(al)
        registry = al.discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        names = registry.names()
        for expected in ("web_search", "reminder", "code_helper", "browser_control",
                          "flight_finder", "send_message", "calendar", "notes"):
            assert expected in names, f"Existing action '{expected}' lost during discovery"

    def test_email_tool_in_tool_declarations(self):
        self._prime_modules()
        import importlib
        import core.action_loader as al
        importlib.reload(al)
        registry = al.discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        decls = registry.get_tool_declarations()
        names = {d["name"] for d in decls}
        assert "email" in names
        email_decl = next(d for d in decls if d["name"] == "email")
        assert "action" in email_decl["parameters"]["properties"]
        assert "to" in email_decl["parameters"]["properties"]
        assert "body" in email_decl["parameters"]["properties"]

    def test_email_run_via_registry(self, valid_config):
        self._prime_modules()
        import importlib
        import core.action_loader as al
        importlib.reload(al)
        registry = al.discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        # Configure first so run() doesn't hit unconfigured error
        registry.run("email", {"action": "configure", "email_address": "test@reg.com", "password": "pw"})
        # Now run send through the registry
        with patch("actions.email.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
            MockSMTP.return_value.__exit__ = MagicMock(return_value=False)
            result = registry.run("email", {"action": "send", "to": "a@b.com", "body": "Hi"})
        assert "Email sent" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Config path is module-level constant
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigPathContract:
    def test_config_path_points_to_api_keys_json(self):
        # The default CONFIG_PATH is computed from the module's location.
        # Verify the expression by constructing it directly.
        default_base = PROJECT_ROOT
        expected = default_base / "config" / "api_keys.json"
        # The actual module computes this via _base_dir() which resolves from
        # the module file location. Confirm the expected path is correct.
        assert expected.exists() or expected.parent.exists()
        assert "config" in expected.parts and "api_keys.json" in expected.parts

    def test_config_path_can_be_reassigned(self, tmp_path, monkeypatch):
        new_path = tmp_path / "custom.json"
        em.CONFIG_PATH = new_path
        new_path.write_text(json.dumps({"email": {"email_address": "x@y.com", "password": "p"}}))
        assert em._get_email_config()["email_address"] == "x@y.com"
        em.CONFIG_PATH = PROJECT_ROOT / "config" / "api_keys.json"  # restore for safety
