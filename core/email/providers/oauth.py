"""Internal OAuth provider adapter primitives.

Provider SDK objects never cross this module's public email service boundary.
Concrete providers inject a small client adapter so tests can exercise mapping
without network access.
"""
from __future__ import annotations

import inspect
import time
import uuid
from typing import Any, Optional

from ..credentials import CredentialStore
from ..errors import (
    AuthenticationError, AuthorizationError, ConnectionError, MailboxNotFoundError,
    MessageNotFoundError, ProviderCapabilityError, RateLimitError, TimeoutError,
    TransientProviderError, PermanentProviderError,
)
from ..models import (
    EmailAccount, EmailAddress, EmailAttachment, EmailDraft, EmailFolder,
    EmailMessage, EmailMessageRef, EmailOperationResult, EmailSearchQuery,
    EmailThread, OperationStatus,
)
from .base import Capability, EmailProvider, ProviderCapabilities, ProviderConnectionState, ProviderMetadata


class OAuthProviderBase(EmailProvider):
    """Common lifecycle, capability gating, and adapter invocation logic."""

    provider_type = "oauth"
    capabilities: tuple[Capability, ...] = ()
    credential_service_prefix = "mark-liii.email"

    def __init__(self, client: Any = None) -> None:
        self._client = client
        self._state = ProviderConnectionState.DISCONNECTED
        self._account: Optional[EmailAccount] = None
        self._credentials: Optional[CredentialStore] = None
        self._capabilities = ProviderCapabilities(self.capabilities)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(self.provider_type, self._account.account_id if self._account else "",
                                self._capabilities, self._state,
                                self._account.display_name if self._account else "")

    @property
    def is_connected(self) -> bool:
        return self._state in (ProviderConnectionState.CONNECTED, ProviderConnectionState.AUTHENTICATED)

    def _service(self) -> str:
        return f"{self.credential_service_prefix}/{self.provider_type}/{self._account.account_id}"

    def _require(self, capability: Capability) -> None:
        if not self.supports(capability):
            raise ProviderCapabilityError(f"Provider does not support {capability.name}")
        if not self.is_connected:
            raise ConnectionError("Provider is not connected")

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if self._client is None:
            raise ConnectionError(f"{self.provider_type} client is not configured")
        fn = getattr(self._client, method, None)
        if fn is None:
            raise ProviderCapabilityError(f"Provider adapter does not implement {method}")
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except (AuthenticationError, AuthorizationError, ConnectionError, MailboxNotFoundError,
                MessageNotFoundError, ProviderCapabilityError, RateLimitError, TimeoutError,
                TransientProviderError, PermanentProviderError):
            raise
        except TimeoutError as exc:
            raise TimeoutError(f"{self.provider_type} request timed out") from exc
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 401:
                raise AuthenticationError(f"{self.provider_type} authentication failed") from exc
            if status == 403:
                raise AuthorizationError(f"{self.provider_type} authorization failed") from exc
            if status == 404:
                raise MessageNotFoundError(f"{self.provider_type} resource not found") from exc
            if status == 429:
                raise RateLimitError(f"{self.provider_type} rate limit exceeded",
                                     retry_after=getattr(exc, "retry_after", None)) from exc
            if status and status >= 500:
                raise TransientProviderError(f"{self.provider_type} service temporarily unavailable") from exc
            raise ConnectionError(f"{self.provider_type} request failed") from exc

    @staticmethod
    def _result(operation: str, ref: Optional[EmailMessageRef] = None, *, metadata: Optional[dict] = None) -> EmailOperationResult:
        return EmailOperationResult(str(uuid.uuid4()), OperationStatus.SUCCESS,
                                    [ref] if ref else [], metadata or {})

    @staticmethod
    def _address(value: Any) -> EmailAddress:
        if isinstance(value, EmailAddress):
            return value
        if isinstance(value, dict):
            return EmailAddress(value.get("address", ""), value.get("name", ""))
        return EmailAddress(str(value or ""))

    def _ref(self, value: Any, mailbox: str = "INBOX") -> EmailMessageRef:
        if isinstance(value, EmailMessageRef):
            if value.account_id != self._account.account_id:
                raise AuthorizationError("Message reference belongs to another account")
            return value
        native = str(value.get("id") if isinstance(value, dict) else value)
        return EmailMessageRef(self._account.account_id, mailbox, native, native)

    async def connect(self, account: EmailAccount, credentials: CredentialStore,
                      timeout: Optional[float] = None) -> ProviderMetadata:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        self._state = ProviderConnectionState.CONNECTING
        self._account, self._credentials = account, credentials
        try:
            access = credentials.get_token(self._service(), "access")
            refresh = credentials.get_token(self._service(), "refresh")
            expiry = credentials.get_token_expiry(self._service(), "access")
            config = dict(account.capabilities) if isinstance(account.capabilities, dict) else {}
            if not access and not refresh:
                raise AuthenticationError("No OAuth credentials found")
            if not access or (expiry is not None and expiry <= time.time() + 30):
                refreshed = await self._call("refresh", refresh, config) if refresh else None
                if not refreshed:
                    raise AuthenticationError("OAuth access token is missing or expired")
                access = refreshed.get("access_token") if isinstance(refreshed, dict) else refreshed
                if not access:
                    raise AuthenticationError("OAuth refresh did not return an access token")
                expires_at = refreshed.get("expires_at") if isinstance(refreshed, dict) else None
                credentials.set_token(self._service(), "access", access, expires_at=expires_at)
            await self._call("authenticate", access, refresh, config)
            self._state = ProviderConnectionState.AUTHENTICATED
            return self.metadata
        except asyncio.CancelledError:
            self._state = ProviderConnectionState.DISCONNECTED
            self._account = None; self._credentials = None
            raise
        except Exception:
            self._state = ProviderConnectionState.DISCONNECTED
            self._account = None; self._credentials = None
            raise

    async def disconnect(self) -> None:
        if self._state == ProviderConnectionState.DISCONNECTED:
            return
        self._state = ProviderConnectionState.DISCONNECTING
        try:
            if self._client is not None and hasattr(self._client, "close"):
                result = self._client.close()
                if inspect.isawaitable(result): await result
        finally:
            self._state = ProviderConnectionState.DISCONNECTED
            self._account = None; self._credentials = None

    async def list_folders(self) -> list[EmailFolder]:
        self._require(Capability.FOLDERS)
        return [self._folder(x) for x in (await self._call("list_folders"))]

    def _folder(self, value: Any) -> EmailFolder:
        if isinstance(value, EmailFolder): return value
        return EmailFolder(str(value.get("id", value.get("name", ""))), str(value.get("name", "")),
                           bool(value.get("selectable", True)), bool(value.get("read_only", False)), value.get("special_use"))

    async def get_folder_info(self, folder_name: str) -> EmailFolder:
        self._require(Capability.FOLDERS)
        return self._folder(await self._call("get_folder", folder_name))

    async def select_folder(self, folder_name: str) -> EmailFolder:
        self._require(Capability.FOLDERS)
        return self._folder(await self._call("select_folder", folder_name))

    async def search(self, query: EmailSearchQuery) -> list[EmailMessageRef]:
        self._require(Capability.SEARCH)
        values = await self._call("search", query)
        return [self._ref(v, (v.get("mailbox") if isinstance(v, dict) else "INBOX")) for v in values]

    async def fetch_message(self, ref: EmailMessageRef, include_body=True, include_attachments=False) -> EmailMessage:
        self._require(Capability.FETCH); self._validate_ref(ref)
        value = await self._call("get_message", ref, include_body=include_body, include_attachments=include_attachments)
        return self._message(value, ref)

    async def fetch_message_headers(self, ref: EmailMessageRef) -> EmailMessage:
        self._require(Capability.FETCH); self._validate_ref(ref)
        return self._message(await self._call("get_message", ref, include_body=False, include_attachments=False), ref)

    async def fetch_attachments(self, ref: EmailMessageRef) -> list[EmailAttachment]:
        self._require(Capability.ATTACHMENTS); self._validate_ref(ref)
        return [self._attachment(x) for x in await self._call("get_attachments", ref)]

    def _validate_ref(self, ref: EmailMessageRef) -> None:
        if ref.account_id != self._account.account_id:
            raise AuthorizationError("Message reference belongs to another account")

    def _message(self, value: Any, ref: EmailMessageRef) -> EmailMessage:
        if isinstance(value, EmailMessage): return value
        return EmailMessage(reference=ref, sender=self._address(value.get("sender", "")),
            recipients=[self._address(x) for x in value.get("recipients", [])],
            subject=value.get("subject", ""), date=value.get("date"), flags=list(value.get("flags", [])),
            body_plain=value.get("body_plain"), body_html=value.get("body_html"),
            attachments=[self._attachment(x) for x in value.get("attachments", [])],
            thread_id=value.get("thread_id"), provider_metadata=dict(value.get("provider_metadata", {})))

    @staticmethod
    def _attachment(value: Any) -> EmailAttachment:
        if isinstance(value, EmailAttachment): return value
        return EmailAttachment(str(value.get("id", "")), value.get("filename", ""), value.get("content_type", "application/octet-stream"), int(value.get("byte_size", 0)), value.get("disposition", "attachment"), value.get("content_id"), value.get("content_handle"))

    async def mark_read(self, ref): self._require(Capability.READ_STATE); self._validate_ref(ref); await self._call("mark_read", ref); return self._result("mark_read", ref)
    async def mark_unread(self, ref): self._require(Capability.READ_STATE); self._validate_ref(ref); await self._call("mark_unread", ref); return self._result("mark_unread", ref)
    async def add_flag(self, ref, flag): self._require(Capability.FLAGS); self._validate_ref(ref); await self._call("add_flag", ref, flag); return self._result("add_flag", ref)
    async def remove_flag(self, ref, flag): self._require(Capability.FLAGS); self._validate_ref(ref); await self._call("remove_flag", ref, flag); return self._result("remove_flag", ref)
    async def delete_message(self, ref): self._require(Capability.DELETE); self._validate_ref(ref); await self._call("delete", ref); return self._result("delete", ref)
    async def move_message(self, ref, target_folder): self._require(Capability.MOVE); self._validate_ref(ref); await self._call("move", ref, target_folder); return self._result("move", ref)
    async def copy_message(self, ref, target_folder): self._require(Capability.COPY); self._validate_ref(ref); await self._call("copy", ref, target_folder); return self._result("copy", ref)
    async def archive_message(self, ref): self._require(Capability.ARCHIVE); self._validate_ref(ref); await self._call("archive", ref); return self._result("archive", ref)

    async def search_threads(self, query):
        self._require(Capability.THREADS); values = await self._call("search_threads", query)
        return [v if isinstance(v, EmailThread) else EmailThread(v["thread_key"], [self._ref(x) for x in v.get("messages", [])], v.get("subject", ""), v.get("first_message_date"), v.get("last_message_date")) for v in values]

    async def get_thread(self, thread_key):
        self._require(Capability.THREADS); v = await self._call("get_thread", thread_key)
        return v if isinstance(v, EmailThread) else EmailThread(v["thread_key"], [self._ref(x) for x in v.get("messages", [])], v.get("subject", ""))

    async def create_draft(self, draft): self._require(Capability.DRAFTS); v = await self._call("create_draft", draft); return self._result("create_draft", v if isinstance(v, EmailMessageRef) else None, metadata={"draft_id": v.get("draft_id")} if isinstance(v, dict) else {})
    async def update_draft(self, ref, draft): self._require(Capability.DRAFTS); self._validate_ref(ref); await self._call("update_draft", ref, draft); return self._result("update_draft", ref)
    async def delete_draft(self, ref): self._require(Capability.DRAFTS); self._validate_ref(ref); await self._call("delete_draft", ref); return self._result("delete_draft", ref)

    async def send(self, account, to, subject, body_plain=None, body_html=None, attachments=None, cc=None, bcc=None, reply_to=None):
        self._require(Capability.SEND)
        if account.account_id != self._account.account_id: raise AuthorizationError("Send account does not match connected account")
        await self._call("send", account, to, subject, body_plain, body_html, attachments, cc, bcc, reply_to)
        return self._result("send")

    def supports(self, capability): return self._capabilities.supports(capability)
