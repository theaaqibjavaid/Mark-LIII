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


def test_action_rejects_non_object_and_unknown_parameters_as_structured_errors():
    module = importlib.import_module("actions.email_search")
    assert json.loads(module.TOOL["handler"](None))["error"]["code"] == "invalid_input"
    assert json.loads(module.TOOL["handler"]({"account_id": "a1", "nope": 1}))["error"]["code"] == "invalid_input"


def test_legacy_email_aliases_are_explicit():
    aliases = set()
    for name in MODULES:
        aliases.update(importlib.import_module(name).LEGACY_ALIASES)
    assert {"email", "send_email", "read_emails", "configure_email"}.issubset(aliases)


def test_action_outputs_are_json_safe():
    module = importlib.import_module("actions.email_account")
    class S:
        def account_metadata(self, account_id): return {"account_id": account_id, "enabled": True}
    module.configure(S())
    parsed = json.loads(module.TOOL["handler"]({"operation": "metadata", "account_id": "a1"}))
    assert parsed["ok"] is True and parsed["data"]["account_id"] == "a1"


def test_message_reference_validation_is_strict():
    module = importlib.import_module("actions.email_message")
    result = json.loads(module.TOOL["handler"]({"operation": "get", "account_id": "a1", "mailbox": "INBOX", "uid": ""}))
    assert result["ok"] is False and result["error"]["code"] == "invalid_input"


def test_compose_contract_never_routes_draft_to_send():
    module = importlib.import_module("actions.email_compose")
    calls = []
    class Service:
        async def create_draft(self, account_id, draft): calls.append("create_draft"); return draft
        async def send(self, **kwargs): calls.append("send"); raise AssertionError("draft action must never call send")
    module.configure(Service())
    result = json.loads(module.TOOL["handler"]({"operation": "create_draft", "account_id": "a1", "to": ["bob@example.com"], "subject": "Hi", "body": "Hello"}))
    assert result["ok"] is True and calls == ["create_draft"]


def test_attachment_action_returns_metadata_not_content():
    module = importlib.import_module("actions.email_attachment")
    class Service:
        async def fetch_attachments(self, account_id, ref):
            from core.email.models import EmailAttachment
            return [EmailAttachment("a1", "report.pdf", "application/pdf", 10, content_handle="handle")]
    module.configure(Service())
    result = json.loads(module.TOOL["handler"]({"account_id": "acct", "mailbox": "INBOX", "uid": "42"}))
    assert result["ok"] is True and "content" not in result["data"][0]


def test_provider_modules_are_not_imported_by_actions():
    for name in MODULES:
        source = open(importlib.import_module(name).__file__, encoding="utf-8").read()
        for forbidden in ("imaplib", "smtplib", "googleapiclient", "msgraph"):
            assert forbidden not in source
