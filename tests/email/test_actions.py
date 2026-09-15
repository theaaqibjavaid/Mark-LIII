import asyncio
import importlib
import json
import pytest

MODULES = ["actions.email_account", "actions.email_search", "actions.email_message", "actions.email_compose", "actions.email_mailbox", "actions.email_attachment"]


def test_all_email_action_modules_are_discoverable():
    for name in MODULES:
        module = importlib.import_module(name)
        tool = module.TOOL
        assert tool["name"].startswith("email_")
        assert tool["description"].strip()
        assert tool["parameters"]["type"] == "OBJECT"
        assert callable(tool["handler"])


def test_action_rejects_non_object_and_unknown_parameters():
    module = importlib.import_module("actions.email_search")
    with pytest.raises(ValueError):
        module.TOOL["handler"](None)
    with pytest.raises(ValueError, match="Unknown parameter"):
        module.TOOL["handler"]({"account_id": "a1", "nope": 1})


def test_legacy_email_aliases_are_explicit():
    aliases = set()
    for name in MODULES:
        aliases.update(importlib.import_module(name).LEGACY_ALIASES)
    assert {"email", "send_email", "read_emails", "configure_email"}.issubset(aliases)


def test_action_outputs_are_json_safe():
    module = importlib.import_module("actions.email_account")
    result = module.TOOL["handler"]({"operation": "metadata", "account_id": "a1"})
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert set(parsed) == {"ok", "data"} or set(parsed) == {"ok", "error"}


def test_message_reference_validation_is_strict():
    module = importlib.import_module("actions.email_message")
    result = json.loads(module.TOOL["handler"]({"operation": "get", "account_id": "a1", "mailbox": "INBOX", "uid": ""}))
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_compose_contract_never_routes_draft_to_send():
    module = importlib.import_module("actions.email_compose")
    calls = []
    class Service:
        async def create_draft(self, account_id, draft):
            calls.append("create_draft")
            return draft
        async def send(self, **kwargs):
            calls.append("send")
            raise AssertionError("draft action must never call send")
    module.configure(Service())
    result = json.loads(module.TOOL["handler"]({"operation": "create_draft", "account_id": "a1", "to": ["bob@example.com"], "subject": "Hi", "body": "Hello"}))
    assert result["ok"] is True
    assert calls == ["create_draft"]


def test_attachment_action_returns_metadata_not_content():
    module = importlib.import_module("actions.email_attachment")
    class Service:
        async def fetch_attachments(self, account_id, ref):
            from core.email.models import EmailAttachment
            return [EmailAttachment("a1", "report.pdf", "application/pdf", 10, content_handle="handle")]
    module.configure(Service())
    result = json.loads(module.TOOL["handler"]({"account_id": "acct", "mailbox": "INBOX", "uid": "42"}))
    assert result["ok"] is True
    assert "content" not in result["data"][0]
    assert result["data"][0]["content_handle"] == "handle"


def test_provider_modules_are_not_imported_by_actions():
    for name in MODULES:
        source = importlib.import_module(name).__file__
        text = open(source, encoding="utf-8").read()
        assert "imaplib" not in text
        assert "smtplib" not in text
        assert "googleapiclient" not in text
        assert "msgraph" not in text
