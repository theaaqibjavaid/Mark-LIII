"""Runtime bootstrap for the provider-neutral Email Engine.

The legacy UI/configuration path predates Email Engine V2. This module bridges
that persisted account configuration into the V2 service boundary without
putting provider calls into LLM-facing actions.
"""
from __future__ import annotations

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


class LegacyImapEmailService:
    """V2 service facade for a legacy IMAP/SMTP account.

    Action handlers are synchronous and currently execute each coroutine in a
    short-lived event loop. A provider connection must therefore not be held
    across calls/loops. This facade creates the provider and connects it inside
    each V2 operation, then disconnects it before returning.
    """

    def __init__(self, account: EmailAccount, credentials: CredentialStore) -> None:
        self._account = account
        self._credentials = credentials
        self._service = EmailService({account.account_id: account}, {})

    def account_metadata(self, account_id: str) -> dict[str, Any]:
        return self._service.account_metadata(account_id)

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        provider = ImapSmtpProvider()
        await provider.connect(self._account, self._credentials)
        self._service._providers[self._account.account_id] = provider
        try:
            return await getattr(self._service, method)(*args, **kwargs)
        finally:
            await provider.disconnect()

    async def list_folders(self, account_id: str):
        return await self._call("list_folders", account_id)

    async def search(self, account_id: str, query: Any):
        return await self._call("search", account_id, query)

    async def get_message(self, account_id: str, ref: Any, **kwargs: Any):
        return await self._call("get_message", account_id, ref, **kwargs)

    async def fetch_attachments(self, account_id: str, ref: Any):
        return await self._call("fetch_attachments", account_id, ref)

    async def mark_read(self, account_id: str, ref: Any):
        return await self._call("mark_read", account_id, ref)

    async def mark_unread(self, account_id: str, ref: Any):
        return await self._call("mark_unread", account_id, ref)

    async def add_flag(self, account_id: str, ref: Any, flag: str):
        return await self._call("add_flag", account_id, ref, flag)

    async def remove_flag(self, account_id: str, ref: Any, flag: str):
        return await self._call("remove_flag", account_id, ref, flag)

    async def move(self, account_id: str, ref: Any, target_folder: str):
        return await self._call("move", account_id, ref, target_folder)

    async def copy(self, account_id: str, ref: Any, target_folder: str):
        return await self._call("copy", account_id, ref, target_folder)

    async def archive(self, account_id: str, ref: Any):
        return await self._call("archive", account_id, ref)

    async def delete(self, account_id: str, ref: Any, **kwargs: Any):
        return await self._call("delete", account_id, ref, **kwargs)

    async def create_draft(self, account_id: str, draft: Any):
        return await self._call("create_draft", account_id, draft)

    async def update_draft(self, account_id: str, ref: Any, draft: Any):
        return await self._call("update_draft", account_id, ref, draft)

    async def send(self, account_id: str, *args: Any, **kwargs: Any):
        return await self._call("send", account_id, *args, **kwargs)

    async def reply(self, account_id: str, ref: Any, **kwargs: Any):
        return await self._call("reply", account_id, ref, **kwargs)

    async def reply_all(self, account_id: str, ref: Any, **kwargs: Any):
        return await self._call("reply_all", account_id, ref, **kwargs)

    async def forward(self, account_id: str, ref: Any, recipients: Any, **kwargs: Any):
        return await self._call("forward", account_id, ref, recipients, **kwargs)


def build_legacy_imap_service(
    config_path: Path,
    *,
    credential_store: CredentialStore | None = None,
) -> LegacyImapEmailService:
    """Build a V2 facade from the persisted legacy account configuration.

    The legacy password is migrated into the configured OS credential store;
    the legacy configuration remains untouched so rollback remains possible.
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
    return LegacyImapEmailService(account, store)
