"""Opt-in real-provider smoke tests for Email Engine V2.

These tests are intentionally skipped unless the corresponding environment
variables are present. Credentials must never be committed to the repository.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from core.email.credentials import InMemoryCredentialStore
from core.email.models import EmailAccount, EmailAddress, EmailDraft, EmailSearchQuery, EmailServerConfig
from core.email.providers.imap_smtp import ImapSmtpProvider


def _required(*names: str) -> dict[str, str]:
    values = {name: os.environ.get(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip("real-provider smoke test requires: " + ", ".join(missing))
    return {name: value for name, value in values.items() if value is not None}


def test_imap_smtp_real_mailbox_smoke() -> None:
    values = _required(
        "MARK_EMAIL_SMTP_HOST", "MARK_EMAIL_SMTP_PORT",
        "MARK_EMAIL_IMAP_HOST", "MARK_EMAIL_IMAP_PORT",
        "MARK_EMAIL_USERNAME", "MARK_EMAIL_PASSWORD",
    )

    async def run() -> None:
        account = EmailAccount(
            account_id="smoke-imap-smtp",
            provider="imap_smtp",
            primary_address=EmailAddress(values["MARK_EMAIL_USERNAME"]),
            server_config=EmailServerConfig(
                imap_host=values["MARK_EMAIL_IMAP_HOST"],
                imap_port=int(values["MARK_EMAIL_IMAP_PORT"]),
                smtp_host=values["MARK_EMAIL_SMTP_HOST"],
                smtp_port=int(values["MARK_EMAIL_SMTP_PORT"]),
                imap_security=os.environ.get("MARK_EMAIL_IMAP_SECURITY", "ssl"),
                smtp_security=os.environ.get("MARK_EMAIL_SMTP_SECURITY", "starttls"),
            ),
        )
        credentials = InMemoryCredentialStore()
        credentials.set_password("imap_smtp", values["MARK_EMAIL_USERNAME"], values["MARK_EMAIL_PASSWORD"])
        provider = ImapSmtpProvider()
        try:
            metadata = await provider.connect(account, credentials, timeout=15)
            assert provider.is_connected
            assert metadata.provider_type == "imap_smtp"
            folders = await provider.list_folders()
            assert folders, "provider connected but advertised no folders"
            refs = await provider.search(EmailSearchQuery(limit=5))
            if refs:
                message = await provider.fetch_message_headers(refs[0])
                assert message.reference == refs[0]

            if os.environ.get("MARK_EMAIL_RUN_DRAFT_SMOKE") == "1":
                draft = EmailDraft(
                    recipients=[EmailAddress(values["MARK_EMAIL_USERNAME"])],
                    subject="Mark-LIII Email Engine V2 smoke test",
                    body_plain="Temporary smoke-test draft; safe to delete.",
                )
                result = await provider.create_draft(draft)
                assert result.is_success
                if result.affected_refs:
                    await provider.delete_draft(result.affected_refs[0])

            if os.environ.get("MARK_EMAIL_RUN_SEND_SMOKE") == "1":
                recipient = os.environ.get("MARK_EMAIL_SMOKE_RECIPIENT")
                if not recipient:
                    pytest.fail("MARK_EMAIL_SMOKE_RECIPIENT is required when send smoke is enabled")
                result = await provider.send(
                    account, [EmailAddress(recipient)],
                    "Mark-LIII Email Engine V2 smoke test",
                    body_plain="Controlled integration smoke test.",
                )
                assert result.is_success
        finally:
            await provider.disconnect()

    asyncio.run(run())


def test_imap_smtp_smoke_is_credential_free_by_default() -> None:
    if any(os.environ.get(name) for name in ("MARK_EMAIL_USERNAME", "MARK_EMAIL_PASSWORD")):
        pytest.skip("credential-free guard is only meaningful without credentials")
    provider = ImapSmtpProvider()
    assert not provider.is_connected


def test_gmail_smoke_contract_is_opt_in() -> None:
    values = _required("MARK_EMAIL_GMAIL_ACCOUNT", "MARK_EMAIL_GMAIL_ACCESS_TOKEN")
    assert values["MARK_EMAIL_GMAIL_ACCOUNT"]
    assert values["MARK_EMAIL_GMAIL_ACCESS_TOKEN"]


def test_microsoft_smoke_contract_is_opt_in() -> None:
    values = _required("MARK_EMAIL_MICROSOFT_ACCOUNT", "MARK_EMAIL_MICROSOFT_ACCESS_TOKEN")
    assert values["MARK_EMAIL_MICROSOFT_ACCOUNT"]
    assert values["MARK_EMAIL_MICROSOFT_ACCESS_TOKEN"]
