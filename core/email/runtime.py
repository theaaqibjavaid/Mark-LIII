"""Runtime bootstrap for the provider-neutral Email Engine.

The legacy UI/configuration path predates Email Engine V2. This module bridges
that persisted account configuration into the V2 service boundary without
putting provider calls into LLM-facing actions.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .credentials import CredentialStore, KeyringCredentialStore
from .models import EmailAccount, EmailAddress, EmailServerConfig
from .providers.imap_smtp import ImapSmtpProvider
from .service import EmailService


def _load_legacy_email_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise RuntimeError("Email account is not configured")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Email configuration could not be read") from exc
    config = data.get("email")
    if not isinstance(config, dict) or not config.get("email_address"):
        raise RuntimeError("Email account is not configured")
    return config


def build_legacy_imap_service(
    config_path: Path,
    *,
    credential_store: CredentialStore | None = None,
) -> EmailService:
    """Build and connect a V2 service from the legacy email account block.

    A legacy password is migrated into the configured credential store for the
    V2 provider. The V2 service never receives the password from an action.
    The legacy config remains untouched so rollback remains possible.
    """
    config = _load_legacy_email_config(config_path)
    address = str(config["email_address"]).strip()
    account_id = address
    server = EmailServerConfig(
        imap_host=str(config.get("imap_server") or "imap.gmail.com"),
        imap_port=int(config.get("imap_port") or 993),
        smtp_host=str(config.get("smtp_server") or "smtp.gmail.com"),
        smtp_port=int(config.get("smtp_port") or 587),
        imap_security="ssl",
        smtp_security="starttls",
    )
    account = EmailAccount(
        account_id=account_id,
        provider="imap_smtp",
        display_name=address,
        primary_address=EmailAddress(address),
        server_config=server,
    )
    store = credential_store or KeyringCredentialStore()
    password = config.get("password")
    if password:
        store.set_password(account.provider, address, str(password))
    if not store.get_password(account.provider, address):
        raise RuntimeError("Email credentials are not available in the credential store")

    provider = ImapSmtpProvider()
    asyncio.run(provider.connect(account, store))
    return EmailService({account_id: account}, {account_id: provider})
