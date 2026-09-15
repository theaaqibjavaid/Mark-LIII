"""Shared, provider-neutral helpers for the Email Engine action boundary."""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from core.email.errors import EmailError, ProviderCapabilityError

_SERVICE: Any = None
_BOOTSTRAP_ATTEMPTED = False


def configure(service: Any) -> None:
    global _SERVICE, _BOOTSTRAP_ATTEMPTED
    _SERVICE = service
    _BOOTSTRAP_ATTEMPTED = True


def _bootstrap_default_service() -> Any:
    """Lazily bridge the persisted legacy account into Email Engine V2.

    The legacy UI/configuration path predates V2. This bridge keeps startup
    independent of email availability while allowing V2 actions to use a
    configured account when they are actually invoked.
    """
    global _SERVICE, _BOOTSTRAP_ATTEMPTED
    if _SERVICE is not None:
        return _SERVICE
    if _BOOTSTRAP_ATTEMPTED:
        raise RuntimeError("Email service is not configured")
    _BOOTSTRAP_ATTEMPTED = True
    try:
        from core.email.runtime import build_legacy_imap_service
        base_dir = Path(__file__).resolve().parent.parent
        _SERVICE = build_legacy_imap_service(base_dir / "config" / "api_keys.json")
        return _SERVICE
    except Exception as exc:
        _SERVICE = None
        raise RuntimeError(f"Email service is not configured: {exc}") from exc


def service() -> Any:
    if _SERVICE is None:
        return _bootstrap_default_service()
    return _SERVICE


def validate(parameters: Any, allowed: set[str], required: set[str] = set()) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"Unknown parameter: {sorted(unknown)[0]}")
    missing = required - set(parameters)
    if missing:
        raise ValueError(f"Missing required parameter: {sorted(missing)[0]}")
    return dict(parameters)


def nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def list_of_strings(value: Any, name: str, *, max_items: int = 100, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{name} must be a non-empty list")
    if len(value) > max_items:
        raise ValueError(f"{name} exceeds maximum of {max_items}")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{name} must contain non-empty strings")
        result.append(item.strip())
    return result


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "__dict__") and value.__class__.__module__.startswith("core.email"):
        return {k: jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": jsonable(data)}, ensure_ascii=False, separators=(",", ":"))


def error(exc: Exception, *, default_code: str = "email_error") -> str:
    if isinstance(exc, ProviderCapabilityError): code = "provider_capability"
    elif isinstance(exc, PermissionError): code = "permission_denied"
    elif isinstance(exc, KeyError): code = "unknown_account"
    elif isinstance(exc, (ValueError, TypeError)): code = "invalid_input"
    elif isinstance(exc, EmailError): code = "email_error"
    else: code = default_code
    message = str(exc) if isinstance(exc, (EmailError, ValueError, TypeError, PermissionError, KeyError)) else "Email operation failed"
    return json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False, separators=(",", ":"))


def run(coro: Any) -> Any:
    if inspect.iscoroutine(coro):
        return asyncio.run(coro)
    return coro


def safe_call(fn: Callable[[], Any]) -> str:
    try:
        return ok(run(fn()))
    except Exception as exc:
        return error(exc)
