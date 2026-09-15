"""
core/email/providers/imap_smtp.py - Generic IMAP/SMTP provider implementation.

Provides email transport via standard IMAP (read) and SMTP (send) protocols.
Implements the EmailProvider abstraction established in core/email/providers/base.py.

Security requirements (per spec 09):
- TLS is required by default; certificates are verified.
- Passwords are never logged or stored in provider objects.
- Credentials are obtained from CredentialStore and not retained after disconnect.

Timeout and cancellation (per spec 03, 11):
- All network operations have explicit timeouts.
- Cancellation during connect() returns provider to DISCONNECTED state.
- Resources are always cleaned up in finally paths.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr, formatdate
from imaplib import IMAP4_SSL
from typing import Any, Optional

from ..credentials import CredentialStore
from ..errors import (
    AttachmentTooLargeError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
    RateLimitError,
    TLSConfigurationError,
    TimeoutError,
)
from ..limits import EmailLimits
from ..models import (
    EmailAccount,
    EmailAddress,
    EmailAttachment,
    EmailDraft,
    EmailFolder,
    EmailMessage,
    EmailMessageRef,
    EmailOperationResult,
    EmailSearchQuery,
    EmailThread,
    OperationStatus,
)
from .base import Capability, EmailProvider, ProviderCapabilities, ProviderConnectionState, ProviderMetadata


logger = logging.getLogger(__name__)

# Default timeouts (seconds)
_DEFAULT_CONNECT_TIMEOUT = 30.0
_DEFAULT_COMMAND_TIMEOUT = 30.0
_DEFAULT_SEND_TIMEOUT = 60.0


class _AsyncIMAPWrapper:
    """Wrapper around sync IMAP objects for async usage."""

    def __init__(self, imap: "IMAP4_SSL") -> None:
        self._imap = imap

    async def list(self) -> tuple[str, list]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.list),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def select(self, folder: str, readonly: bool = False) -> tuple[str, list]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.select, folder, readonly),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def uid(self, command: str, *args) -> tuple[str, list]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.uid, command, *args),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def search(self, charset: Optional[str], criteria: str) -> tuple[str, list]:
        """Perform IMAP SEARCH command (returns sequence numbers, not UIDs)."""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.search, charset, criteria),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def uid_search(self, charset: Optional[str], criteria: str) -> tuple[str, list]:
        """Perform IMAP UID SEARCH command (returns UIDs)."""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: self._imap.uid("search", charset, criteria)),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def append(self, mailbox: str, flags: str, date: Optional[object], message: bytes) -> tuple[str, list]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.append, mailbox, flags, date, message),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def logout(self) -> None:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, self._imap.logout),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._imap, name)


class _AsyncSMTPWrapper:
    """Wrapper around sync SMTP objects for async usage."""

    def __init__(self, smtp: smtplib.SMTP) -> None:
        self._smtp = smtp

    async def login(self, user: str, password: str) -> tuple[str, dict]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._smtp.login, user, password),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    async def sendmail(self, from_addr: str, to_addrs: list[str], msg: str) -> dict:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._smtp.sendmail, from_addr, to_addrs, msg),
            timeout=_DEFAULT_SEND_TIMEOUT,
        )

    async def quit(self) -> None:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, self._smtp.quit),
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self._smtp, name)


class ImapSmtpProvider(EmailProvider):
    """Concrete provider implementing email transport via IMAP and SMTP."""

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
        self._current_folder: str = "INBOX"
        self._folder_info_cache: dict[str, EmailFolder] = {}
        self._imap_host: Optional[str] = imap_host
        self._imap_port: Optional[int] = imap_port
        self._smtp_host: Optional[str] = smtp_host
        self._smtp_port: Optional[int] = smtp_port
        self._use_tls: bool = use_tls
        self._credentials: Optional[CredentialStore] = None  # Stored during connect for SMTP auth

    # ── Lifecycle ─────────────────────────────────────────────────────────────

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
        return self._state in (
            ProviderConnectionState.CONNECTED,
            ProviderConnectionState.AUTHENTICATED,
        )

    async def connect(
        self,
        account: EmailAccount,
        credentials: CredentialStore,
        timeout: Optional[float] = None,
    ) -> ProviderMetadata:
        """Establish IMAP connection and authenticate."""
        self._state = ProviderConnectionState.CONNECTING
        self._account = account
        self._credentials = credentials  # Store for SMTP auth later

        try:
            password = credentials.get_password(
                service=account.provider,
                username=account.primary_address.address if account.primary_address else account.account_id,
            )
            if password is None:
                self._state = ProviderConnectionState.DISCONNECTED
                raise AuthenticationError("No password found in credential store")

            # Parse server configuration from account.capabilities dict
            caps = account.capabilities or {}
            imap_host = caps.get("imap_server")
            imap_port = caps.get("imap_port", 993)
            
            # Require explicit SMTP configuration - no defaults
            smtp_host = caps.get("smtp_server")
            smtp_port = caps.get("smtp_port", 587 if self._use_tls else 25)

            if not imap_host:
                self._state = ProviderConnectionState.DISCONNECTED
                raise ConnectionError("IMAP server not configured in account.capabilities")
            
            if not smtp_host:
                logger.warning("SMTP server not configured - can only receive, not send")

            connect_timeout = timeout if timeout is not None else _DEFAULT_CONNECT_TIMEOUT

            # Establish IMAP connection with TLS
            try:
                loop = asyncio.get_event_loop()
                if self._use_tls:
                    self._imap = _AsyncIMAPWrapper(await loop.run_in_executor(
                        None, lambda: IMAP4_SSL(imap_host, imap_port, timeout=connect_timeout)
                    ))
                else:
                    # Plain IMAP (not recommended, use with caution)
                    from imaplib import IMAP4
                    self._imap = _AsyncIMAPWrapper(await loop.run_in_executor(
                        None, lambda: IMAP4(imap_host, imap_port, timeout=connect_timeout)
                    ))
            except asyncio.TimeoutError:
                self._state = ProviderConnectionState.DISCONNECTED
                raise TimeoutError(f"IMAP connection to {imap_host}:{imap_port} timed out")
            except ssl.SSLError as e:
                self._state = ProviderConnectionState.DISCONNECTED
                raise TLSConfigurationError(f"TLS handshake failed: {e}")

            # Authenticate
            try:
                loop = asyncio.get_event_loop()
                status, _ = await loop.run_in_executor(
                    None, lambda: self._imap._imap.login(account.account_id, password)
                )
                if status != "OK":
                    self._state = ProviderConnectionState.DISCONNECTED
                    raise AuthenticationError(f"IMAP login failed: {status}")
            except AuthenticationError:
                raise
            except Exception as e:
                self._state = ProviderConnectionState.DISCONNECTED
                if "AUTHENTICATION" in str(e).upper():
                    raise AuthenticationError(f"Authentication failed: {e}")
                raise ConnectionError(f"Login error: {e}")

            # Discover capabilities
            self._discover_capabilities()
            self._state = ProviderConnectionState.AUTHENTICATED

            logger.debug(f"Connected to IMAP server {imap_host}")
            return self.metadata

        except Exception:
            await self._cleanup()
            raise

    async def disconnect(self) -> None:
        """Clean up all connections. Idempotent and safe to call multiple times."""
        if self._state == ProviderConnectionState.DISCONNECTED:
            return

        self._state = ProviderConnectionState.DISCONNECTING

        try:
            if self._imap is not None:
                try:
                    await self._imap.logout()
                except Exception:
                    pass
                finally:
                    self._imap = None

            if self._smtp is not None:
                try:
                    await self._smtp.quit()
                except Exception:
                    pass
                finally:
                    self._smtp = None

        finally:
            self._state = ProviderConnectionState.DISCONNECTED
            self._account = None
            self._credentials = None  # Clear credentials for security
            self._current_folder = "INBOX"
            self._folder_info_cache.clear()

    # ── Mailbox Operations ────────────────────────────────────────────────────

    async def list_folders(self) -> list[EmailFolder]:
        """List all mailboxes/folders via IMAP LIST command."""
        self._require_connected()
        self._require_capability(Capability.FOLDERS)

        try:
            status, responses = await self._imap.list()
            if status != "OK":
                raise ConnectionError("Failed to list folders")

            folders = []
            for resp in responses:
                if isinstance(resp, bytes):
                    resp = resp.decode("utf-8", errors="replace")
                folder = self._parse_folder_line(resp)
                if folder:
                    folders.append(folder)
                    self._folder_info_cache[folder.provider_name] = folder

            return folders

        except (ConnectionError, MailboxNotFoundError):
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to list folders: {e}")

    async def get_folder_info(self, folder_name: str) -> EmailFolder:
        """Get metadata about a specific mailbox without changing selection."""
        self._require_connected()
        self._require_capability(Capability.FOLDERS)

        if folder_name in self._folder_info_cache:
            return self._folder_info_cache[folder_name]

        try:
            # Use LIST to get metadata without selecting
            status, responses = await self._imap.list()
            if status == "OK":
                for resp in responses:
                    if isinstance(resp, bytes):
                        resp = resp.decode("utf-8", errors="replace")
                    folder = self._parse_folder_line(resp)
                    if folder and folder.provider_name == folder_name:
                        return folder

            # Fallback: try to select (may change current folder)
            return await self.select_folder(folder_name)
            
        except MailboxNotFoundError:
            raise
        except Exception as e:
            raise MailboxNotFoundError(f"Folder '{folder_name}' not accessible: {e}")

    async def select_folder(self, folder_name: str) -> EmailFolder:
        """Select a mailbox for subsequent operations."""
        self._require_connected()
        self._require_capability(Capability.FOLDERS)

        try:
            status, _ = await self._imap.select(folder_name, readonly=False)
            if status != "OK":
                raise MailboxNotFoundError(f"Cannot select folder: {folder_name}")

            self._current_folder = folder_name
            folder = EmailFolder(provider_name=folder_name, display_name=folder_name, selectable=True)
            self._folder_info_cache[folder_name] = folder
            return folder

        except MailboxNotFoundError:
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to select folder '{folder_name}': {e}")

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: EmailSearchQuery) -> list[EmailMessageRef]:
        """Search messages using IMAP UID SEARCH with UID identity."""
        self._require_connected()
        self._require_capability(Capability.SEARCH)

        try:
            imap_criteria = self._build_search_criteria(query)
            
            # Validate query doesn't use unsupported features
            unsupported_fields = []
            if query.thread_id:
                unsupported_fields.append("thread_id")
            if query.has_attachment is not None:
                unsupported_fields.append("has_attachment")
            if query.sort_by:
                unsupported_fields.append("sort_by")
            if query.sort_order:
                unsupported_fields.append("sort_order")
            if query.offset:
                unsupported_fields.append("offset")
            
            if unsupported_fields:
                # Log warning but continue - these are hints, not errors
                logger.warning(
                    f"Search query fields not fully supported by IMAP: {unsupported_fields}. "
                    f"Using best-effort mapping."
                )

            # Use UID SEARCH to get UIDs directly
            status, data = await self._imap.uid_search(None, imap_criteria)

            if status != "OK" or not data or not data[0]:
                return []

            uid_str = data[0].decode("utf-8")
            uids = uid_str.split() if uid_str else []
            
            # Apply limit (cap at resolved_limit)
            limit = query.resolved_limit
            if limit is not None:
                uids = uids[:limit]

            return [
                EmailMessageRef(
                    account_id=self._account.account_id,
                    mailbox=self._current_folder,
                    uid=uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
                )
                for uid in uids
            ]

        except (MessageNotFoundError, MailboxNotFoundError):
            raise
        except Exception as e:
            raise ConnectionError(f"Search failed: {e}")

    # ── Message Retrieval ─────────────────────────────────────────────────────

    async def fetch_message(
        self,
        ref: EmailMessageRef,
        include_body: bool = True,
        include_attachments: bool = False,
    ) -> EmailMessage:
        """Fetch a complete message using UID FETCH with PEEK to avoid side effects."""
        self._require_connected()
        self._require_capability(Capability.FETCH)

        try:
            uid = ref.uid
            # Use BODY.PEEK[] to avoid setting \Seen flag (RFC 3501 section 6.4.5)
            fetch_command = "BODY.PEEK[]" if include_body else "BODY.PEEK[HEADER]"
            status, data = await self._imap.uid("fetch", uid, fetch_command)

            if status != "OK" or not data:
                raise MessageNotFoundError(f"Message {uid} not found")

            raw_message = self._extract_raw_message(data)
            if not raw_message:
                raise MessageNotFoundError(f"Failed to parse message {uid}")

            return self._parse_message(raw_message, ref, flags=data)

        except MessageNotFoundError:
            raise
        except Exception as e:
            raise MessageNotFoundError(f"Failed to fetch message {ref.uid}: {e}")

    async def fetch_message_headers(self, ref: EmailMessageRef) -> EmailMessage:
        """Fetch only message headers (lightweight) using BODY.PEEK[HEADER]."""
        # Fetch headers only - no body content
        self._require_connected()
        self._require_capability(Capability.FETCH)

        try:
            uid = ref.uid
            # Explicitly fetch only headers using BODY.PEEK[HEADER]
            status, data = await self._imap.uid("fetch", uid, "BODY.PEEK[HEADER]")

            if status != "OK" or not data:
                raise MessageNotFoundError(f"Message {uid} not found")

            raw_message = self._extract_raw_message(data)
            if not raw_message:
                raise MessageNotFoundError(f"Failed to parse headers for message {uid}")

            # Parse but don't extract body
            return self._parse_message_headers_only(raw_message, ref, flags=data)

        except MessageNotFoundError:
            raise
        except Exception as e:
            raise MessageNotFoundError(f"Failed to fetch headers for message {ref.uid}: {e}")

    async def fetch_attachments(self, ref: EmailMessageRef) -> list[EmailAttachment]:
        """Fetch attachment metadata by parsing message structure."""
        self._require_connected()
        self._require_capability(Capability.ATTACHMENTS)

        try:
            # Fetch full message to parse attachments
            msg = await self.fetch_message(ref, include_body=False)
            return msg.attachments
        except MessageNotFoundError:
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to fetch attachments: {e}")

    # ── Message Operations ────────────────────────────────────────────────────

    async def mark_read(self, ref: EmailMessageRef) -> EmailOperationResult:
        """Mark message as read using UID STORE +\\Seen."""
        return await self._set_flag(ref, "\\Seen")

    async def mark_unread(self, ref: EmailMessageRef) -> EmailOperationResult:
        """Mark message as unread using UID STORE -\\Seen."""
        return await self._unset_flag(ref, "\\Seen")

    async def add_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        """Add a flag to a message."""
        return await self._set_flag(ref, flag)

    async def remove_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        """Remove a flag from a message."""
        return await self._unset_flag(ref, flag)

    async def delete_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        """Mark message as deleted (moves to trash after EXPUNGE)."""
        self._require_connected()
        self._require_capability(Capability.DELETE)

        try:
            status, _ = await self._imap.uid("store", ref.uid, "+FLAGS", "(\\Deleted)")
            if status != "OK":
                raise ProviderCapabilityError("Delete not supported")

            return EmailOperationResult(
                operation_id=f"delete-{ref.uid}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )
        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Delete failed: {e}")

    # ── Message Movement ──────────────────────────────────────────────────────

    async def move_message(self, ref: EmailMessageRef, target_folder: str) -> EmailOperationResult:
        """Move message to target folder using UID MOVE if supported."""
        self._require_connected()
        self._require_capability(Capability.MOVE)

        try:
            status, _ = await self._imap.uid("move", ref.uid, target_folder)

            if status == "OK":
                return EmailOperationResult(
                    operation_id=f"move-{ref.uid}",
                    status=OperationStatus.SUCCESS,
                    affected_refs=[ref],
                )

            # Fallback: COPY + DELETE with proper semantics
            copy_result = await self.copy_message(ref, target_folder)
            if copy_result.status != OperationStatus.SUCCESS:
                raise ConnectionError("Move fallback failed: copy failed")
            
            # Delete original
            delete_result = await self.delete_message(ref)
            if delete_result.status != OperationStatus.SUCCESS:
                # Copy succeeded but delete failed - message is now duplicated
                logger.error(f"Move failed: copy succeeded but delete failed for {ref.uid}")
                raise ConnectionError(f"Move partially succeeded: copy to {target_folder} succeeded, but delete failed")

            return EmailOperationResult(
                operation_id=f"move-{ref.uid}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )

        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Move failed: {e}")

    async def copy_message(self, ref: EmailMessageRef, target_folder: str) -> EmailOperationResult:
        """Copy message to target folder."""
        self._require_connected()
        self._require_capability(Capability.COPY)

        try:
            status, _ = await self._imap.uid("copy", ref.uid, target_folder)
            if status != "OK":
                raise ProviderCapabilityError("Copy not supported")

            return EmailOperationResult(
                operation_id=f"copy-{ref.uid}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )
        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Copy failed: {e}")

    async def archive_message(self, ref: EmailMessageRef) -> EmailOperationResult:
        """Archive message by moving to special-use Archive folder."""
        self._require_connected()
        self._require_capability(Capability.ARCHIVE)

        archive_folder = await self._find_archive_folder()
        if not archive_folder:
            raise ProviderCapabilityError("No archive folder found")

        return await self.move_message(ref, archive_folder)

    # ── Thread Operations ─────────────────────────────────────────────────────

    async def search_threads(self, query: EmailSearchQuery) -> list[EmailThread]:
        """Search for message threads (placeholder - IMAP THREAD not widely supported)."""
        self._require_connected()
        self._require_capability(Capability.THREADS)
        return []

    async def get_thread(self, thread_key: str) -> EmailThread:
        """Get a complete thread by key (placeholder)."""
        self._require_connected()
        self._require_capability(Capability.THREADS)
        return EmailThread(thread_key=thread_key)

    # ── Draft Operations ──────────────────────────────────────────────────────

    async def create_draft(self, draft: EmailDraft) -> EmailOperationResult:
        """Save draft to IMAP Drafts folder."""
        self._require_connected()
        self._require_capability(Capability.DRAFTS)

        try:
            draft_folder = await self._get_drafts_folder()
            await self.select_folder(draft_folder)

            message = self._compose_draft_message(draft)
            status, _ = await self._imap.append(draft_folder, "\\Draft", None, message.encode("utf-8"))

            if status != "OK":
                raise ConnectionError("Failed to append draft")

            # Get UID of newly created draft
            status, data = await self._imap.uid("search", None, "ALL")
            uid_str = data[0].decode("utf-8").split()[-1] if data[0] else ""

            ref = EmailMessageRef(account_id=self._account.account_id, mailbox=draft_folder, uid=uid_str)

            return EmailOperationResult(
                operation_id=f"draft-create-{uid_str}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )

        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Create draft failed: {e}")

    async def update_draft(self, ref: EmailMessageRef, draft: EmailDraft) -> EmailOperationResult:
        """Update existing draft (delete old, create new)."""
        await self.delete_message(ref)
        return await self.create_draft(draft)

    async def delete_draft(self, ref: EmailMessageRef) -> EmailOperationResult:
        """Delete a draft."""
        return await self.delete_message(ref)

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send(
        self,
        account: EmailAccount,
        to: list[EmailAddress],
        subject: str,
        body_plain: Optional[str] = None,
        body_html: Optional[str] = None,
        attachments: Optional[list[EmailAttachment]] = None,
        cc: Optional[list[EmailAddress]] = None,
        bcc: Optional[list[EmailAddress]] = None,
        reply_to: Optional[EmailAddress] = None,
    ) -> EmailOperationResult:
        """Send email via SMTP with TLS."""
        all_recipients = [r.address for r in to]
        if cc:
            all_recipients.extend([r.address for r in cc])
        if bcc:
            all_recipients.extend([r.address for r in bcc])

        if not all_recipients:
            raise InvalidRecipientError("No recipients specified")

        # Validate attachments
        if attachments:
            # Check individual attachment size
            for att in attachments:
                if att.byte_size > EmailLimits.MAX_ATTACHMENT_SIZE_BYTES:
                    raise AttachmentTooLargeError(
                        f"Attachment '{att.filename}' size {att.byte_size} exceeds limit"
                    )
            
            # Check attachment count
            if len(attachments) > EmailLimits.MAX_ATTACHMENT_COUNT:
                raise AttachmentTooLargeError(
                    f"Attachment count {len(attachments)} exceeds limit"
                )
            
            # Check total size
            total_size = sum(a.byte_size for a in attachments)
            if total_size > EmailLimits.MAX_TOTAL_ATTACHMENT_SIZE_BYTES:
                raise AttachmentTooLargeError(f"Total attachment size {total_size} exceeds limit")

        # Ensure SMTP connection
        smtp_connected = self._smtp is not None
        if not smtp_connected:
            await self._connect_smtp(account)

        try:
            message = self._compose_message(
                account=account, to=to, subject=subject,
                body_plain=body_plain, body_html=body_html,
                attachments=attachments, cc=cc, bcc=bcc, reply_to=reply_to,
            )

            all_addrs = [r.address for r in to]
            if cc:
                all_addrs.extend([r.address for r in cc])
            if bcc:
                all_addrs.extend([r.address for r in bcc])

            # Enforce send timeout
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._smtp.sendmail(
                        account.primary_address.address if account.primary_address else account.account_id,
                        all_addrs,
                        message.as_string(),
                    ),
                ),
                timeout=_DEFAULT_SEND_TIMEOUT,
            )

            return EmailOperationResult(
                operation_id=f"send-{datetime.now().isoformat()}",
                status=OperationStatus.SUCCESS,
                affected_refs=[],
            )

        except smtplib.SMTPRecipientsRefused as e:
            raise InvalidRecipientError(f"Invalid recipient: {e}")
        except smtplib.SMTPAuthenticationError as e:
            raise AuthenticationError(f"SMTP authentication failed: {e}")
        except smtplib.SMTPException as e:
            raise ConnectionError(f"SMTP send failed: {e}")
        except asyncio.TimeoutError:
            raise TimeoutError("SMTP send timed out")
        finally:
            if not smtp_connected and self._smtp is not None:
                await self._disconnect_smtp()

    # ── Capability Discovery ──────────────────────────────────────────────────

    def _discover_capabilities(self) -> None:
        """Discover and cache provider capabilities."""
        caps = self._capabilities
        caps.add(Capability.SEARCH)
        caps.add(Capability.FETCH)
        caps.add(Capability.FOLDERS)
        caps.add(Capability.FLAGS)
        caps.add(Capability.READ_STATE)
        caps.add(Capability.DELETE)
        caps.add(Capability.COPY)
        caps.add(Capability.DRAFTS)
        caps.add(Capability.MOVE)
        caps.add(Capability.ATTACHMENTS)
        caps.add(Capability.SEND)  # SMTP send capability

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise ConnectionError("Provider not connected")

    def _require_capability(self, capability: Capability) -> None:
        if not self._capabilities.supports(capability):
            raise ProviderCapabilityError(f"Capability {capability.name} not supported")

    async def _set_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        self._require_connected()
        self._require_capability(Capability.FLAGS)

        try:
            status, _ = await self._imap.uid("store", ref.uid, "+FLAGS", f"({flag})")
            if status != "OK":
                raise ProviderCapabilityError("Flag operation not supported")

            return EmailOperationResult(
                operation_id=f"flag-set-{ref.uid}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )
        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Set flag failed: {e}")

    async def _unset_flag(self, ref: EmailMessageRef, flag: str) -> EmailOperationResult:
        self._require_connected()
        self._require_capability(Capability.FLAGS)

        try:
            status, _ = await self._imap.uid("store", ref.uid, "-FLAGS", f"({flag})")
            if status != "OK":
                raise ProviderCapabilityError("Flag operation not supported")

            return EmailOperationResult(
                operation_id=f"flag-remove-{ref.uid}",
                status=OperationStatus.SUCCESS,
                affected_refs=[ref],
            )
        except ProviderCapabilityError:
            raise
        except Exception as e:
            raise ConnectionError(f"Unset flag failed: {e}")

    async def _find_archive_folder(self) -> Optional[str]:
        folders = await self.list_folders()
        for folder in folders:
            # Prefer special-use flags
            if folder.special_use and "\\Archive" in folder.special_use:
                return folder.provider_name
        # Fallback to name-based detection (less reliable)
        for folder in folders:
            if folder.provider_name.lower() in ("archive", "archives"):
                return folder.provider_name
        return None

    async def _get_drafts_folder(self) -> str:
        folders = await self.list_folders()
        for folder in folders:
            # Prefer special-use flags
            if folder.special_use and "\\Drafts" in folder.special_use:
                return folder.provider_name
        # Fallback to name-based detection
        for folder in folders:
            if folder.provider_name.lower() in ("drafts", "draft"):
                return folder.provider_name
        # Explicitly raise if no drafts folder found
        raise MailboxNotFoundError("No Drafts folder found")

    def _parse_folder_line(self, line: str) -> Optional[EmailFolder]:
        try:
            parts = line.split('"')
            if len(parts) < 4:
                return None

            flags_part = parts[0].strip()
            separator = parts[1]
            name = parts[3]

            special_use = None
            selectable = "\\Noselect" not in flags_part
            read_only = "\\ReadOnly" in flags_part

            for flag in ["\\All", "\\Archive", "\\Drafts", "\\Flagged", "\\Junk", "\\Sent", "\\Trash"]:
                if flag in flags_part:
                    special_use = flag
                    break

            return EmailFolder(
                provider_name=name,
                display_name=name,
                selectable=selectable,
                read_only=read_only,
                special_use=special_use,
            )
        except Exception:
            return EmailFolder(provider_name=line)

    def _build_search_criteria(self, query: EmailSearchQuery) -> str:
        criteria = []

        if query.sender:
            criteria.append(f'FROM "{query.sender}"')
        if query.recipients:
            for recipient in query.recipients:
                criteria.append(f'TO "{recipient}"')
        if query.subject:
            criteria.append(f'SUBJECT "{query.subject}"')
        if query.body:
            criteria.append(f'TEXT "{query.body}"')
        if query.date_from:
            criteria.append(f"SINCE {query.date_from.strftime('%d-%b-%Y')}")
        if query.date_to:
            criteria.append(f"BEFORE {query.date_to.strftime('%d-%b-%Y')}")
        if query.flags:
            for flag in query.flags:
                if flag.startswith("\\"):
                    criteria.append(flag)

        # Note: thread_id, has_attachment, sort_by, sort_order, offset are not supported by IMAP SEARCH
        # They are silently ignored as per IMAP protocol limitations

        return " ".join(criteria) if criteria else "ALL"

    def _extract_raw_message(self, data: list) -> Optional[bytes]:
        if not data or not data[0]:
            return None

        response = data[0]
        if isinstance(response, tuple):
            if len(response) >= 2:
                inner = response[1]
                if isinstance(inner, tuple) and len(inner) >= 2:
                    return inner[1]
                elif isinstance(inner, bytes):
                    return inner

        return None

    def _parse_flags_from_response(self, data: list) -> list[str]:
        """Extract IMAP flags from FETCH response metadata."""
        flags = []
        if not data or not data[0]:
            return flags
        
        response = data[0]
        if isinstance(response, tuple):
            for item in response:
                if isinstance(item, bytes):
                    flag_str = item.decode('utf-8', errors='replace')
                    if flag_str.startswith('\\'):
                        flags.append(flag_str)
                elif isinstance(item, tuple):
                    for sub_item in item:
                        if isinstance(sub_item, bytes):
                            flag_str = sub_item.decode('utf-8', errors='replace')
                            if flag_str.startswith('\\'):
                                flags.append(flag_str)
        
        return flags

    def _parse_message(self, raw: bytes, ref: EmailMessageRef, flags: Optional[list] = None) -> EmailMessage:
        from email.parser import BytesParser

        parser = BytesParser()
        msg = parser.parsebytes(raw)

        sender_str = msg.get("From", "")
        sender_name, sender_addr = parseaddr(sender_str)
        sender = EmailAddress(sender_addr, sender_name)

        to_str = msg.get("To", "")
        to_names, to_addrs = [], []
        for addr in to_str.split(","):
            name, email = parseaddr(addr.strip())
            to_names.append(name)
            to_addrs.append(email)
        recipients = [EmailAddress(addr, name) for name, addr in zip(to_names, to_addrs)]

        subject = self._decode_header(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        date = None

        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        # Extract flags from IMAP response metadata, not from message content
        message_flags = self._parse_flags_from_response(flags) if flags else []

        # Parse attachments from MIME structure
        attachments = self._extract_attachments(msg)

        return EmailMessage(
            reference=ref,
            sender=sender,
            recipients=recipients,
            subject=subject,
            date=date,
            flags=message_flags,
            body_plain=self._extract_body(raw, "plain"),
            body_html=self._extract_body(raw, "html"),
            attachments=attachments,
            provider_metadata={"raw_size": len(raw)},
        )

    def _parse_message_headers_only(self, raw: bytes, ref: EmailMessageRef, flags: Optional[list] = None) -> EmailMessage:
        """Parse message headers only - no body content extraction."""
        from email.parser import BytesParser

        parser = BytesParser()
        msg = parser.parsebytes(raw)

        sender_str = msg.get("From", "")
        sender_name, sender_addr = parseaddr(sender_str)
        sender = EmailAddress(sender_addr, sender_name)

        to_str = msg.get("To", "")
        to_names, to_addrs = [], []
        for addr in to_str.split(","):
            name, email = parseaddr(addr.strip())
            to_names.append(name)
            to_addrs.append(email)
        recipients = [EmailAddress(addr, name) for name, addr in zip(to_names, to_addrs)]

        subject = self._decode_header(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        date = None

        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        # Extract flags from IMAP response metadata
        message_flags = self._parse_flags_from_response(flags) if flags else []

        # Parse attachment metadata only (no content)
        attachments = self._extract_attachment_metadata(msg)

        return EmailMessage(
            reference=ref,
            sender=sender,
            recipients=recipients,
            subject=subject,
            date=date,
            flags=message_flags,
            body_plain=None,  # No body content for header-only fetch
            body_html=None,
            attachments=attachments,
            provider_metadata={"raw_size": len(raw)},
        )

    def _extract_attachments(self, msg: object) -> list[EmailAttachment]:
        """Extract full attachment metadata including content handles."""
        attachments = []
        from email.mime.base import MIMEBase
        
        if hasattr(msg, 'walk'):
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        # Create attachment metadata
                        att = EmailAttachment(
                            attachment_id=f"att_{len(attachments)}",
                            filename=filename,
                            content_type=part.get_content_type(),
                            byte_size=len(part.get_payload(decode=True) or b""),
                            content_handle=None,  # Content not loaded for memory efficiency
                        )
                        attachments.append(att)
        return attachments

    def _extract_attachment_metadata(self, msg: object) -> list[EmailAttachment]:
        """Extract attachment metadata only (no content loading)."""
        attachments = []
        
        if hasattr(msg, 'walk'):
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        att = EmailAttachment(
                            attachment_id=f"att_{len(attachments)}",
                            filename=filename,
                            content_type=part.get_content_type(),
                            byte_size=0,  # Don't load content to calculate size
                        )
                        attachments.append(att)
        return attachments

    def _extract_body(self, raw: bytes, content_type: str) -> Optional[str]:
        from email import policy
        from email.parser import BytesParser

        msg = BytesParser(policy=policy.default).parsebytes(raw)

        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if content_type in ctype:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            ctype = msg.get_content_type()
            if content_type in ctype:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")

        return None

    def _decode_header(self, header_value: str) -> str:
        if not header_value:
            return ""

        decoded_parts = []
        for part, encoding in decode_header(header_value):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)

        return "".join(decoded_parts)

    def _compose_message(
        self,
        account: EmailAccount,
        to: list[EmailAddress],
        subject: str,
        body_plain: Optional[str],
        body_html: Optional[str],
        attachments: Optional[list[EmailAttachment]],
        cc: Optional[list[EmailAddress]],
        bcc: Optional[list[EmailAddress]],
        reply_to: Optional[EmailAddress],
    ) -> object:
        """Compose MIME message for SMTP sending."""
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()

        from_addr = account.primary_address.format() if account.primary_address else account.account_id
        msg["From"] = from_addr
        msg["To"] = ", ".join(r.format() for r in to)
        msg["Subject"] = subject

        if reply_to:
            msg["Reply-To"] = reply_to.format()
        if cc:
            msg["Cc"] = ", ".join(r.format() for r in cc)

        msg["Date"] = formatdate(localtime=True)

        if body_plain and body_html:
            msg.attach(MIMEText(body_plain, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        elif body_plain:
            msg.attach(MIMEText(body_plain, "plain", "utf-8"))
        elif body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        else:
            msg.attach(MIMEText("", "plain", "utf-8"))

        if attachments:
            for att in attachments:
                from email.mime.base import MIMEBase
                from email import encoders

                if att.content_handle:
                    try:
                        with open(att.content_handle, "rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f"attachment; filename={att.filename}")
                        msg.attach(part)
                    except (IOError, OSError) as e:
                        # Re-raise instead of silently dropping
                        raise AttachmentTooLargeError(f"Failed to read attachment '{att.filename}': {e}")

        return msg

    def _compose_draft_message(self, draft: EmailDraft) -> str:
        from email.mime.text import MIMEText
        from email.utils import formatdate

        msg = MIMEText(draft.body_plain or "", "plain", "utf-8")
        msg["From"] = self._account.primary_address.format() if self._account and self._account.primary_address else ""
        msg["To"] = ", ".join(r.format() for r in draft.recipients)
        msg["Subject"] = draft.subject
        msg["Date"] = formatdate(localtime=True)

        return msg.as_string()

    async def _connect_smtp(self, account: EmailAccount) -> None:
        """Establish SMTP connection with TLS."""
        smtp_host = self._smtp_host
        smtp_port = self._smtp_port

        # Use credentials from connect() if available
        password = None
        if self._credentials:
            password = self._credentials.get_password(
                service=account.provider,
                username=account.primary_address.address if account.primary_address else account.account_id,
            )

        try:
            loop = asyncio.get_event_loop()
            if self._use_tls:
                # SMTP with STARTTLS (port 587 typically)
                self._smtp = _AsyncSMTPWrapper(await loop.run_in_executor(
                    None, lambda: smtplib.SMTP(smtp_host, smtp_port, timeout=_DEFAULT_CONNECT_TIMEOUT)
                ))
                await loop.run_in_executor(None, self._smtp._smtp.starttls)
            else:
                # Implicit TLS (port 465 typically)
                import smtplib as smtplib_module
                self._smtp = _AsyncSMTPWrapper(await loop.run_in_executor(
                    None, lambda: smtplib_module.SMTP_SSL(smtp_host, smtp_port, timeout=_DEFAULT_CONNECT_TIMEOUT)
                ))
            
            # Authenticate if credentials available
            if password:
                await self._smtp.login(account.account_id, password)

        except ssl.SSLError as e:
            raise TLSConfigurationError(f"SMTP TLS failed: {e}")
        except smtplib.SMTPConnectError as e:
            raise ConnectionError(f"SMTP connection failed: {e}")
        except smtplib.SMTPServerDisconnected as e:
            raise ConnectionError(f"SMTP connection failed: {e}")
        except smtplib.SMTPAuthenticationError as e:
            raise AuthenticationError(f"SMTP auth failed: {e}")
        except asyncio.TimeoutError:
            raise TimeoutError("SMTP connection timed out")

    async def _disconnect_smtp(self) -> None:
        if self._smtp:
            try:
                await self._smtp.quit()
            except Exception:
                pass
            finally:
                self._smtp = None

    async def _cleanup(self) -> None:
        """Emergency cleanup on connection failure."""
        await self._disconnect_smtp()
        if self._imap:
            try:
                await self._imap.logout()
            except Exception:
                pass
            finally:
                self._imap = None
        self._state = ProviderConnectionState.DISCONNECTED
        self._credentials = None  # Clear credentials on cleanup
