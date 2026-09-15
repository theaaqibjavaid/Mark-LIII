"""Generic standards-based IMAP/SMTP email provider."""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl
import uuid
from datetime import datetime
from email import policy
from email.header import decode_header
from email.message import EmailMessage as MimeMessage
from email.parser import BytesParser
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime
from imaplib import IMAP4, IMAP4_SSL
from typing import Any, Optional

from ..credentials import CredentialStore
from ..errors import (
    AttachmentTooLargeError, AuthenticationError, AuthorizationError,
    ConnectionError, InvalidRecipientError, MailboxNotFoundError,
    MessageNotFoundError, ProviderCapabilityError, RateLimitError,
    TLSConfigurationError, TimeoutError, TransientProviderError,
)
from ..limits import EmailLimits
from ..models import (
    EmailAccount, EmailAddress, EmailAttachment, EmailDraft, EmailFolder,
    EmailMessage, EmailMessageRef, EmailOperationResult, EmailSearchQuery,
    EmailThread, OperationStatus,
)
from .base import (
    Capability, EmailProvider, ProviderCapabilities, ProviderConnectionState,
    ProviderMetadata,
)

logger = logging.getLogger(__name__)
_DEFAULT_CONNECT_TIMEOUT = 30.0
_DEFAULT_COMMAND_TIMEOUT = 30.0
_DEFAULT_SEND_TIMEOUT = 60.0


async def _run_sync(fn: Any, *args: Any, timeout: float) -> Any:
    """Run a blocking protocol call with an asyncio timeout."""
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, lambda: fn(*args)), timeout=timeout
    )


class _AsyncIMAPWrapper:
    def __init__(self, imap: Any) -> None:
        self._imap = imap

    async def list(self) -> tuple[str, list]:
        return await _run_sync(self._imap.list, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def select(self, folder: str, readonly: bool = False) -> tuple[str, list]:
        return await _run_sync(self._imap.select, folder, readonly, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def uid(self, command: str, *args: Any) -> tuple[str, list]:
        return await _run_sync(self._imap.uid, command, *args, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def uid_search(self, charset: Optional[str], criteria: str) -> tuple[str, list]:
        return await _run_sync(self._imap.uid, "search", charset, criteria, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def append(self, mailbox: str, flags: str, date: Any, message: bytes) -> tuple[str, list]:
        return await _run_sync(self._imap.append, mailbox, flags, date, message, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def logout(self) -> Any:
        return await _run_sync(self._imap.logout, timeout=_DEFAULT_COMMAND_TIMEOUT)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._imap, name)


class _AsyncSMTPWrapper:
    def __init__(self, smtp: Any) -> None:
        self._smtp = smtp

    async def login(self, user: str, password: str) -> Any:
        return await _run_sync(self._smtp.login, user, password, timeout=_DEFAULT_COMMAND_TIMEOUT)

    async def sendmail(self, from_addr: str, to_addrs: list[str], msg: str) -> dict:
        return await _run_sync(self._smtp.sendmail, from_addr, to_addrs, msg, timeout=_DEFAULT_SEND_TIMEOUT)

    async def quit(self) -> Any:
        return await _run_sync(self._smtp.quit, timeout=_DEFAULT_COMMAND_TIMEOUT)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._smtp, name)


class ImapSmtpProvider(EmailProvider):
    """Provider using IMAP for mailbox operations and SMTP for sending."""

    def __init__(
        self,
        imap_host: Optional[str] = None,
        imap_port: Optional[int] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        use_tls: bool = True,
    ) -> None:
        self._state = ProviderConnectionState.DISCONNECTED
        self._account: Optional[EmailAccount] = None
        self._imap: Optional[_AsyncIMAPWrapper] = None
        self._smtp: Optional[_AsyncSMTPWrapper] = None
        self._capabilities = ProviderCapabilities()
        self._current_folder = "INBOX"
        self._folder_info_cache: dict[str, EmailFolder] = {}
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._use_tls = use_tls
        self._credentials: Optional[CredentialStore] = None

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type="imap_smtp",
            account_id=self._account.account_id if self._account else "",
            capabilities=self._capabilities,
            connection_state=self._state,
            display_name=self._account.display_name if self._account else "",
        )

    @property
    def is_connected(self) -> bool:
        return self._state in (ProviderConnectionState.CONNECTED, ProviderConnectionState.AUTHENTICATED)

    async def connect(self, account: EmailAccount, credentials: CredentialStore, timeout: Optional[float] = None) -> ProviderMetadata:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        self._state = ProviderConnectionState.CONNECTING
        self._account = account
        self._credentials = credentials
        cfg = account.server_config
        imap_host = self._imap_host or (cfg.imap_host if cfg else None)
        imap_port = self._imap_port or (cfg.imap_port if cfg else 993)
        smtp_host = self._smtp_host or (cfg.smtp_host if cfg else None)
        smtp_port = self._smtp_port or (cfg.smtp_port if cfg and cfg.smtp_port else (587 if self._use_tls else 465))
        if not imap_host:
            await self._cleanup()
            raise ConnectionError("IMAP server is not configured")
        connect_timeout = timeout or _DEFAULT_CONNECT_TIMEOUT
        try:
            password = credentials.get_password(
                service=account.provider,
                username=account.primary_address.address if account.primary_address else account.account_id,
            )
            if password is None:
                raise AuthenticationError("No password found in credential store")
            if cfg and cfg.imap_security == "starttls":
                imap_obj = await _run_sync(IMAP4, imap_host, imap_port, timeout=connect_timeout)
                await _run_sync(imap_obj.starttls, ssl_context=ssl.create_default_context(), timeout=connect_timeout)
            elif cfg and cfg.imap_security == "plain":
                imap_obj = await _run_sync(IMAP4, imap_host, imap_port, timeout=connect_timeout)
            else:
                imap_obj = await _run_sync(IMAP4_SSL, imap_host, imap_port, timeout=connect_timeout)
            self._imap = _AsyncIMAPWrapper(imap_obj)
            status, _ = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, lambda: imap_obj.login(account.account_id, password)),
                timeout=connect_timeout,
            )
            if status != "OK":
                raise AuthenticationError("IMAP authentication failed")
            self._discover_capabilities(imap_obj)
            self._state = ProviderConnectionState.AUTHENTICATED
            return self.metadata
        except asyncio.CancelledError:
            await self._cleanup()
            raise
        except AuthenticationError:
            await self._cleanup()
            raise
        except (ssl.SSLError, ValueError) as exc:
            await self._cleanup()
            if isinstance(exc, ssl.SSLError):
                raise TLSConfigurationError("IMAP TLS configuration failed") from exc
            raise
        except asyncio.TimeoutError as exc:
            await self._cleanup()
            raise TimeoutError("IMAP connection/authentication timed out") from exc
        except Exception as exc:
            await self._cleanup()
            text = str(exc).lower()
            if "auth" in text or "login" in text:
                raise AuthenticationError("IMAP authentication failed") from exc
            raise ConnectionError("IMAP connection failed") from exc

    async def disconnect(self) -> None:
        if self._state == ProviderConnectionState.DISCONNECTED:
            return
        self._state = ProviderConnectionState.DISCONNECTING
        try:
            if self._smtp:
                try:
                    await self._smtp.quit()
                except Exception:
                    pass
                self._smtp = None
            if self._imap:
                try:
                    await self._imap.logout()
                except Exception:
                    pass
                self._imap = None
        finally:
            self._state = ProviderConnectionState.DISCONNECTED
            self._account = None
            self._credentials = None
            self._current_folder = "INBOX"
            self._folder_info_cache.clear()

    async def list_folders(self) -> list[EmailFolder]:
        self._require_connected(); self._require_capability(Capability.FOLDERS)
        try:
            status, rows = await self._imap.list()
            if status != "OK": raise ConnectionError("Failed to list folders")
            result = []
            for row in rows or []:
                if isinstance(row, bytes): row = row.decode("utf-8", "replace")
                folder = self._parse_folder_line(row)
                if folder:
                    result.append(folder); self._folder_info_cache[folder.provider_name] = folder
            return result
        except (ConnectionError, ProviderCapabilityError):
            raise
        except Exception as exc:
            raise ConnectionError("Failed to list folders") from exc

    async def get_folder_info(self, folder_name: str) -> EmailFolder:
        self._require_connected(); self._require_capability(Capability.FOLDERS)
        if folder_name in self._folder_info_cache: return self._folder_info_cache[folder_name]
        for folder in await self.list_folders():
            if folder.provider_name == folder_name: return folder
        raise MailboxNotFoundError(f"Folder '{folder_name}' not found")

    async def select_folder(self, folder_name: str) -> EmailFolder:
        self._require_connected(); self._require_capability(Capability.FOLDERS)
        try:
            status, _ = await self._imap.select(folder_name, readonly=False)
            if status != "OK": raise MailboxNotFoundError(f"Cannot select folder: {folder_name}")
            self._current_folder = folder_name
            return self._folder_info_cache.get(folder_name, EmailFolder(folder_name))
        except MailboxNotFoundError: raise
        except Exception as exc: raise MailboxNotFoundError(f"Folder '{folder_name}' not found") from exc

    async def search(self, query: EmailSearchQuery) -> list[EmailMessageRef]:
        self._require_connected(); self._require_capability(Capability.SEARCH)
        unsupported = []
        if query.thread_id: unsupported.append("thread_id")
        if query.has_attachment is not None: unsupported.append("has_attachment")
        if query.sort_by not in ("date",): unsupported.append("sort_by")
        if query.sort_order not in ("asc", "desc"): unsupported.append("sort_order")
        if unsupported: raise ProviderCapabilityError("IMAP search does not support: " + ", ".join(unsupported))
        try:
            folders = query.folders or [self._current_folder]
            refs: list[EmailMessageRef] = []
            original = self._current_folder
            for folder in folders:
                if folder != self._current_folder: await self.select_folder(folder)
                criteria = self._build_search_criteria(query)
                status, data = await self._imap.uid_search(None, criteria)
                if status != "OK": raise TransientProviderError("IMAP search failed")
                raw = data[0] if data else b""
                if isinstance(raw, bytes): raw = raw.decode("ascii", "ignore")
                for uid in str(raw).split():
                    refs.append(EmailMessageRef(self._account.account_id, folder, uid))
            if original != self._current_folder: await self.select_folder(original)
            if query.sort_order == "desc": refs.reverse()
            start = query.offset
            return refs[start:start + query.resolved_limit]
        except ProviderCapabilityError: raise
        except Exception as exc:
            if isinstance(exc, TransientProviderError): raise
            raise ConnectionError("Search failed") from exc

    async def fetch_message(self, ref: EmailMessageRef, include_body: bool = True, include_attachments: bool = False) -> EmailMessage:
        self._require_connected(); self._require_capability(Capability.FETCH)
        self._validate_ref(ref)
        try:
            command = "BODY.PEEK[]" if include_body else "BODY.PEEK[HEADER]"
            status, data = await self._imap.uid("fetch", ref.uid, command)
            if status != "OK": raise MessageNotFoundError(f"Message {ref.uid} not found")
            raw = self._extract_raw_message(data)
            if raw is None: raise MessageNotFoundError(f"Message {ref.uid} not found")
            message = self._parse_message(raw, ref, data)
            if not include_attachments: message.attachments = []
            return message
        except MessageNotFoundError: raise
        except Exception as exc: raise MessageNotFoundError(f"Failed to fetch message {ref.uid}") from exc

    async def fetch_message_headers(self, ref: EmailMessageRef) -> EmailMessage:
        self._require_connected(); self._require_capability(Capability.FETCH); self._validate_ref(ref)
        try:
            status, data = await self._imap.uid("fetch", ref.uid, "BODY.PEEK[HEADER]")
            if status != "OK": raise MessageNotFoundError(f"Message {ref.uid} not found")
            raw = self._extract_raw_message(data)
            if raw is None: raise MessageNotFoundError(f"Message {ref.uid} not found")
            return self._parse_message_headers_only(raw, ref, data)
        except MessageNotFoundError: raise
        except Exception as exc: raise MessageNotFoundError(f"Failed to fetch headers {ref.uid}") from exc

    async def fetch_attachments(self, ref: EmailMessageRef) -> list[EmailAttachment]:
        self._require_connected(); self._require_capability(Capability.ATTACHMENTS)
        message = await self.fetch_message(ref, include_body=True, include_attachments=True)
        return message.attachments

    async def mark_read(self, ref: EmailMessageRef) -> EmailOperationResult: return await self._set_flag(ref, "\\Seen")
    async def mark_unread(self, ref: EmailMessageRef) -> EmailOperationResult: return await self._unset_flag(ref, "\\Seen")
    async def add_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult: return await self._set_flag(ref, flag)
    async def remove_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult: return await self._unset_flag(ref, flag)

    async def delete_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.DELETE); self._validate_ref(ref)
        status, _ = await self._imap.uid("store", ref.uid, "+FLAGS", "(\\Deleted)")
        if status != "OK": raise ConnectionError("Delete failed")
        return self._result("delete", ref)

    async def move_message(self, ref: EmailMessageRef, target_folder: str) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.MOVE); self._validate_ref(ref)
        if not (await self.get_folder_info(target_folder)).selectable: raise MailboxNotFoundError(target_folder)
        status, _ = await self._imap.uid("move", ref.uid, target_folder)
        if status == "OK": return self._result("move", ref, target_folder=target_folder)
        copy_status, _ = await self._imap.uid("copy", ref.uid, target_folder)
        if copy_status != "OK": raise ProviderCapabilityError("MOVE is unavailable and COPY fallback failed")
        expunge_status, _ = await self._imap.uid("expunge", ref.uid)
        if expunge_status != "OK":
            raise ProviderCapabilityError("MOVE unavailable; safe UID EXPUNGE is not supported")
        return self._result("move", ref, target_folder=target_folder)

    async def copy_message(self, ref: EmailMessageRef, target_folder: str) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.COPY); self._validate_ref(ref)
        await self.get_folder_info(target_folder)
        status, _ = await self._imap.uid("copy", ref.uid, target_folder)
        if status != "OK": raise ConnectionError("Copy failed")
        return self._result("copy", ref, target_folder=target_folder)

    async def archive_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.ARCHIVE)
        folder = next((f.provider_name for f in await self.list_folders() if f.special_use == "\\Archive"), None)
        if not folder: raise ProviderCapabilityError("No IMAP \\Archive folder is advertised")
        return await self.move_message(ref, folder)

    async def search_threads(self, query: EmailSearchQuery) -> list[EmailThread]:
        self._require_connected(); self._require_capability(Capability.THREADS)
        raise ProviderCapabilityError("IMAP THREAD support was not advertised")

    async def get_thread(self, thread_key: str) -> EmailThread:
        self._require_connected(); self._require_capability(Capability.THREADS)
        raise ProviderCapabilityError("IMAP THREAD support was not advertised")

    async def create_draft(self, draft: EmailDraft) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.DRAFTS)
        folder = next((f.provider_name for f in await self.list_folders() if f.special_use == "\\Drafts"), None)
        if not folder: raise MailboxNotFoundError("No IMAP \\Drafts folder found")
        message = self._compose_draft_message(draft)
        status, data = await self._imap.append(folder, "(\\Draft)", None, message.as_bytes(policy=policy.default))
        if status != "OK": raise ConnectionError("Failed to append draft")
        uid = self._extract_append_uid(data) or uuid.uuid4().hex
        return self._result("draft-create", EmailMessageRef(self._account.account_id, folder, uid))

    async def update_draft(self, ref: EmailMessageRef, draft: EmailDraft) -> EmailOperationResult:
        await self.delete_draft(ref); return await self.create_draft(draft)

    async def delete_draft(self, ref: EmailMessageRef) -> EmailOperationResult:
        self._require_capability(Capability.DRAFTS); return await self.delete_message(ref)

    async def send(self, account: EmailAccount, to: list[EmailAddress], subject: str, body_plain: Optional[str] = None, body_html: Optional[str] = None, attachments: Optional[list[EmailAttachment]] = None, cc: Optional[list[EmailAddress]] = None, bcc: Optional[list[EmailAddress]] = None, reply_to: Optional[EmailAddress] = None) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.SEND)
        recipients = list(to) + list(cc or []) + list(bcc or [])
        if not recipients: raise InvalidRecipientError("No recipients specified")
        if any("@" not in r.address or r.address.startswith("@") or r.address.endswith("@") for r in recipients):
            raise InvalidRecipientError("Invalid recipient address")
        attachments = attachments or []
        if len(attachments) > EmailLimits.MAX_ATTACHMENT_COUNT: raise AttachmentTooLargeError("Attachment count exceeds limit")
        if any(a.byte_size > EmailLimits.MAX_ATTACHMENT_SIZE_BYTES for a in attachments): raise AttachmentTooLargeError("Attachment exceeds size limit")
        if sum(a.byte_size for a in attachments) > EmailLimits.MAX_TOTAL_ATTACHMENT_SIZE_BYTES: raise AttachmentTooLargeError("Total attachment size exceeds limit")
        await self._connect_smtp(account)
        operation_id = f"send-{uuid.uuid4().hex}"
        message = self._compose_message(account, to, subject, body_plain, body_html, attachments, cc, bcc, reply_to)
        sender = account.primary_address.address if account.primary_address else account.account_id
        addresses = [r.address for r in recipients]
        try:
            await self._smtp.sendmail(sender, addresses, message.as_string())
            return EmailOperationResult(operation_id, OperationStatus.SUCCESS)
        except smtplib.SMTPRecipientsRefused as exc:
            raise InvalidRecipientError("One or more recipients were refused") from exc
        except smtplib.SMTPAuthenticationError as exc:
            raise AuthenticationError("SMTP authentication failed") from exc
        except asyncio.TimeoutError as exc:
            return EmailOperationResult(operation_id, OperationStatus.UNKNOWN, error="SMTP send timed out", error_code="SEND_UNKNOWN")
        except smtplib.SMTPException as exc:
            raise ConnectionError("SMTP send failed") from exc

    def _discover_capabilities(self, imap_obj: Any) -> None:
        caps = self._capabilities
        for capability in (Capability.SEARCH, Capability.FETCH, Capability.FOLDERS, Capability.FLAGS, Capability.READ_STATE, Capability.COPY, Capability.DELETE, Capability.DRAFTS, Capability.ATTACHMENTS, Capability.SEND):
            caps.add(capability)
        raw = getattr(imap_obj, "capabilities", ()) or ()
        normalized = {x.decode().upper() if isinstance(x, bytes) else str(x).upper() for x in raw}
        if "MOVE" in normalized or "UIDPLUS" in normalized: caps.add(Capability.MOVE)
        if "THREAD=REFERENCES" in normalized or "THREAD=ORDEREDSUBJECT" in normalized: caps.add(Capability.THREADS)
        if "UIDPLUS" in normalized: caps.add(Capability.IDEMPOTENT_SEND)
        if any(x in normalized for x in {"STARTTLS", "LOGINDISABLED"}): pass

    def _require_connected(self) -> None:
        if not self.is_connected: raise ConnectionError("Provider not connected")

    def _require_capability(self, capability: Capability) -> None:
        if not self._capabilities.supports(capability): raise ProviderCapabilityError(f"Capability {capability.name} not supported")

    def _validate_ref(self, ref: EmailMessageRef) -> None:
        if not self._account or ref.account_id != self._account.account_id: raise AuthorizationError("Message does not belong to the active account")
        if not ref.uid or not re.fullmatch(r"[0-9]+", str(ref.uid)): raise MessageNotFoundError("Invalid message UID")
        if ref.mailbox != self._current_folder: raise MessageNotFoundError("Message mailbox is not selected")

    async def _set_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.FLAGS); self._validate_ref(ref)
        status, _ = await self._imap.uid("store", ref.uid, "+FLAGS", f"({flag})")
        if status != "OK": raise ConnectionError("Flag operation failed")
        return self._result("flag-set", ref)

    async def _unset_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        self._require_connected(); self._require_capability(Capability.FLAGS); self._validate_ref(ref)
        status, _ = await self._imap.uid("store", ref.uid, "-FLAGS", f"({flag})")
        if status != "OK": raise ConnectionError("Flag operation failed")
        return self._result("flag-remove", ref)

    async def _connect_smtp(self, account: EmailAccount) -> None:
        cfg = account.server_config
        host = self._smtp_host or (cfg.smtp_host if cfg else None)
        port = self._smtp_port or (cfg.smtp_port if cfg and cfg.smtp_port else (587 if self._use_tls else 465))
        if not host: raise ConnectionError("SMTP server is not configured")
        password = self._credentials.get_password(account.provider, account.primary_address.address if account.primary_address else account.account_id) if self._credentials else None
        try:
            security = cfg.smtp_security if cfg else ("starttls" if self._use_tls else "ssl")
            if security == "ssl":
                smtp_obj = await _run_sync(smtplib.SMTP_SSL, host, port, timeout=_DEFAULT_CONNECT_TIMEOUT)
            else:
                smtp_obj = await _run_sync(smtplib.SMTP, host, port, timeout=_DEFAULT_CONNECT_TIMEOUT)
                if security == "starttls":
                    await _run_sync(smtp_obj.starttls, context=ssl.create_default_context(), timeout=_DEFAULT_CONNECT_TIMEOUT)
            self._smtp = _AsyncSMTPWrapper(smtp_obj)
            if password is not None: await self._smtp.login(account.account_id, password)
        except smtplib.SMTPAuthenticationError as exc: self._smtp = None; raise AuthenticationError("SMTP authentication failed") from exc
        except smtplib.SMTPConnectError as exc: self._smtp = None; raise ConnectionError("SMTP connection failed") from exc
        except ssl.SSLError as exc: self._smtp = None; raise TLSConfigurationError("SMTP TLS configuration failed") from exc
        except asyncio.TimeoutError as exc: self._smtp = None; raise TimeoutError("SMTP connection timed out") from exc
        except Exception as exc: self._smtp = None; raise ConnectionError("SMTP connection failed") from exc

    async def _cleanup(self) -> None:
        try:
            if self._smtp: await self._smtp.quit()
        except Exception: pass
        try:
            if self._imap: await self._imap.logout()
        except Exception: pass
        self._smtp = None; self._imap = None; self._state = ProviderConnectionState.DISCONNECTED; self._account = None; self._credentials = None

    def _parse_folder_line(self, line: str) -> Optional[EmailFolder]:
        match = re.search(r"\(([^)]*)\)\s+\"([^\"]*)\"\s+\"(.*)\"$", line)
        if not match: return None
        flags = match.group(1); name = match.group(3)
        special = next((f for f in ("\\Archive", "\\Drafts", "\\Sent", "\\Trash", "\\Junk", "\\Flagged", "\\All") if f in flags), None)
        return EmailFolder(name, name, "\\Noselect" not in flags, "\\ReadOnly" in flags, special)

    def _build_search_criteria(self, query: EmailSearchQuery) -> str:
        criteria = []
        if query.sender: criteria.append(f'FROM "{self._quote_search(query.sender)}"')
        for recipient in query.recipients or []: criteria.append(f'TO "{self._quote_search(recipient)}"')
        if query.subject: criteria.append(f'SUBJECT "{self._quote_search(query.subject)}"')
        if query.body: criteria.append(f'TEXT "{self._quote_search(query.body)}"')
        if query.date_from: criteria.append(f"SINCE {query.date_from.strftime('%d-%b-%Y')}")
        if query.date_to: criteria.append(f"BEFORE {query.date_to.strftime('%d-%b-%Y')}")
        for flag in query.flags or []:
            if flag == "\\Seen": criteria.append("SEEN")
            elif flag == "\\Flagged": criteria.append("FLAGGED")
            elif flag == "\\Answered": criteria.append("ANSWERED")
            elif flag == "\\Deleted": criteria.append("DELETED")
            elif flag == "\\Draft": criteria.append("DRAFT")
            else: raise ProviderCapabilityError(f"Unsupported IMAP flag search: {flag}")
        return " ".join(criteria) or "ALL"

    @staticmethod
    def _quote_search(value: str) -> str: return value.replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def _extract_raw_message(data: list) -> Optional[bytes]:
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                payload = item[1]
                if isinstance(payload, bytes): return payload
                if isinstance(payload, tuple) and len(payload) >= 2 and isinstance(payload[1], bytes): return payload[1]
        return None

    @staticmethod
    def _parse_flags_from_response(data: list) -> list[str]:
        text = " ".join((x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x)) for x in (data or []))
        match = re.search(r"FLAGS\s*\(([^)]*)\)", text, re.I)
        return match.group(1).split() if match else []

    def _parse_message(self, raw: bytes, ref: EmailMessageRef, flags: Optional[list] = None) -> EmailMessage:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        sender_name, sender_addr = parseaddr(msg.get("From", ""))
        recipients = [EmailAddress(addr, name) for name, addr in (parseaddr(x.strip()) for x in msg.get("To", "").split(",")) if addr]
        reply_name, reply_addr = parseaddr(msg.get("Reply-To", ""))
        attachments = self._extract_attachments(msg)
        date = None
        try: date = parsedate_to_datetime(msg.get("Date", "")) if msg.get("Date") else None
        except (TypeError, ValueError): pass
        return EmailMessage(ref, EmailAddress(sender_addr, sender_name), recipients, EmailAddress(reply_addr, reply_name) if reply_addr else None, self._decode_header(msg.get("Subject", "")), date, self._parse_flags_from_response(flags), self._extract_body(msg, "plain"), self._extract_body(msg, "html"), attachments, msg.get("Message-ID"), {"message_id": msg.get("Message-ID", "")})

    def _parse_message_headers_only(self, raw: bytes, ref: EmailMessageRef, flags: Optional[list] = None) -> EmailMessage:
        message = self._parse_message(raw, ref, flags)
        message.body_plain = None; message.body_html = None; return message

    def _extract_attachments(self, msg: Any) -> list[EmailAttachment]:
        result = []
        for part in msg.walk() if msg.is_multipart() else [msg]:
            if part.get_content_disposition() != "attachment": continue
            filename = part.get_filename()
            if not filename: continue
            payload = part.get_payload(decode=True) or b""
            if len(payload) > EmailLimits.MAX_ATTACHMENT_SIZE_BYTES: raise AttachmentTooLargeError(f"Attachment '{filename}' exceeds size limit")
            result.append(EmailAttachment(f"att_{len(result)}", filename, part.get_content_type(), len(payload), "attachment", part.get("Content-ID")))
        if len(result) > EmailLimits.MAX_ATTACHMENT_COUNT: raise AttachmentTooLargeError("Attachment count exceeds limit")
        if sum(x.byte_size for x in result) > EmailLimits.MAX_TOTAL_ATTACHMENT_SIZE_BYTES: raise AttachmentTooLargeError("Total attachment size exceeds limit")
        return result

    @staticmethod
    def _extract_body(msg: Any, content_type: str) -> Optional[str]:
        parts = msg.walk() if msg.is_multipart() else [msg]
        for part in parts:
            if part.get_content_type() != f"text/{content_type}": continue
            payload = part.get_payload(decode=True)
            if payload is None: continue
            return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return None

    @staticmethod
    def _decode_header(value: str) -> str:
        return "".join(p.decode(enc or "utf-8", "replace") if isinstance(p, bytes) else p for p, enc in decode_header(value or ""))

    def _compose_message(self, account: EmailAccount, to: list[EmailAddress], subject: str, body_plain: Optional[str], body_html: Optional[str], attachments: list[EmailAttachment], cc: Optional[list[EmailAddress]], bcc: Optional[list[EmailAddress]], reply_to: Optional[EmailAddress]) -> MimeMessage:
        msg = MimeMessage(policy=policy.default)
        msg["From"] = account.primary_address.format() if account.primary_address else account.account_id
        msg["To"] = ", ".join(x.format() for x in to)
        if cc: msg["Cc"] = ", ".join(x.format() for x in cc)
        if bcc: msg["Bcc"] = ", ".join(x.format() for x in bcc)
        msg["Subject"] = subject; msg["Date"] = formatdate(localtime=True); msg["Message-ID"] = make_msgid()
        if reply_to: msg["Reply-To"] = reply_to.format()
        if body_plain and body_html: msg.set_content(body_plain); msg.add_alternative(body_html, subtype="html")
        elif body_html: msg.add_alternative(body_html, subtype="html")
        else: msg.set_content(body_plain or "")
        for att in attachments:
            if not att.content_handle: raise AttachmentTooLargeError(f"Attachment content is unavailable: {att.filename}")
            with open(att.content_handle, "rb") as handle: data = handle.read()
            if len(data) > EmailLimits.MAX_ATTACHMENT_SIZE_BYTES: raise AttachmentTooLargeError(f"Attachment '{att.filename}' exceeds size limit")
            maintype, _, subtype = att.content_type.partition("/")
            msg.add_attachment(data, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=att.filename)
        return msg

    def _compose_draft_message(self, draft: EmailDraft) -> MimeMessage:
        account = self._account
        return self._compose_message(account, draft.recipients, draft.subject, draft.body_plain, draft.body_html, draft.attachments, None, None, None)

    @staticmethod
    def _extract_append_uid(data: list) -> Optional[str]:
        text = " ".join(x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x) for x in data or [])
        match = re.search(r"(?:APPENDUID\s+\d+\s+)?(\d+)", text)
        return match.group(1) if match else None

    @staticmethod
    def _result(operation: str, ref: EmailMessageRef, **metadata: Any) -> EmailOperationResult:
        return EmailOperationResult(f"{operation}-{uuid.uuid4().hex}", OperationStatus.SUCCESS, [ref], metadata)
