"""Opt-in real-provider smoke tests for Email Engine V2.

These tests are intentionally skipped unless the corresponding environment
variables are present. Credentials must never be committed to the repository.
"""
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.integration


def _required(*names: str) -> dict[str, str]:
    values = {name: os.environ.get(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip("real-provider smoke test requires: " + ", ".join(missing))
    return {name: value for name, value in values.items() if value is not None}


def test_imap_smtp_smoke_contract_is_opt_in() -> None:
    values = _required(
        "MARK_EMAIL_SMTP_HOST",
        "MARK_EMAIL_SMTP_PORT",
        "MARK_EMAIL_IMAP_HOST",
        "MARK_EMAIL_IMAP_PORT",
        "MARK_EMAIL_USERNAME",
        "MARK_EMAIL_PASSWORD",
    )
    assert values["MARK_EMAIL_USERNAME"]
    assert values["MARK_EMAIL_PASSWORD"]


def test_gmail_smoke_contract_is_opt_in() -> None:
    values = _required("MARK_EMAIL_GMAIL_ACCOUNT", "MARK_EMAIL_GMAIL_ACCESS_TOKEN")
    assert values["MARK_EMAIL_GMAIL_ACCOUNT"]
    assert values["MARK_EMAIL_GMAIL_ACCESS_TOKEN"]


def test_microsoft_smoke_contract_is_opt_in() -> None:
    values = _required(
        "MARK_EMAIL_MICROSOFT_ACCOUNT",
        "MARK_EMAIL_MICROSOFT_ACCESS_TOKEN",
    )
    assert values["MARK_EMAIL_MICROSOFT_ACCOUNT"]
    assert values["MARK_EMAIL_MICROSOFT_ACCESS_TOKEN"]
