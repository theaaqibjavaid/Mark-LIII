"""LLM-facing email account metadata action. Secrets never cross this boundary."""
from __future__ import annotations

from .email_common import configure, error, ok, service, validate, nonempty

LEGACY_ALIASES = ("configure_email", "email_config", "email_account")


def _handler(parameters=None, **_):
    try:
        p = validate(parameters, {"operation", "account_id"}, {"operation"})
        operation = nonempty(p["operation"], "operation").lower()
        if operation == "metadata":
            account_id = nonempty(p.get("account_id"), "account_id")
            account = service()._accounts.get(account_id)
            if account is None:
                raise KeyError(account_id)
            return ok({"account_id": account.account_id, "provider": account.provider, "display_name": account.display_name, "primary_address": account.primary_address.format() if account.primary_address else None, "aliases": [a.format() for a in account.aliases], "enabled": account.enabled, "capabilities": list(account.capabilities)})
        raise ValueError("Unsupported account operation")
    except Exception as exc:
        return error(exc)

TOOL = {"name": "email_account", "description": "Read provider-neutral email account metadata without exposing passwords, tokens, or credential values.", "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING", "description": "metadata"}, "account_id": {"type": "STRING"}}, "required": ["operation"]}, "handler": _handler}
