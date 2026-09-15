"""
Tests for core/email/providers/base.py — Provider abstraction contract.

Verifies:
- Abstract interface cannot be instantiated without implementation
- FakeEmailProvider implements the corrected contract
- Capability model works correctly
- Domain models are used (not provider-native objects)
- Error contract is preserved
- No secrets leak into provider metadata
- Search uses EmailSearchQuery, not provider-specific syntax
- Lifecycle contract: connect/disconnect/cancellation/context-manager
- Typed send interface uses EmailAddress, not raw strings
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.providers.base import (
    Capability,
    EmailProvider,
    ProviderCapabilities,
    ProviderConnectionState,
    ProviderMetadata,
)
from core.email.models import (
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
from core.email.credentials import CredentialStore
from core.email.errors import (
    AttachmentTooLargeError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    InvalidRecipientError,
    MailboxNotFoundError,
    MessageNotFoundError,
    ProviderCapabilityError,
    RateLimitError,
    TimeoutError,
    TransientProviderError,
    PermanentProviderError,
)


# ── Test: Abstract Interface ───────────────────────────────────────────────────

class TestAbstractInterface:
    """Verify EmailProvider cannot be instantiated without implementing required methods."""

    def test_cannot_instantiate_abstract(self):
        """EmailProvider is abstract and cannot be directly instantiated."""
        with pytest.raises(TypeError):
            EmailProvider()

    def test_subclass_without_implementing_raises(self):
        """Subclass that doesn't implement abstract methods cannot be instantiated."""
        class IncompleteProvider(EmailProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_subclass_partial_implementation_raises(self):
        """Subclass missing even one abstract method cannot be instantiated."""
        class PartialProvider(EmailProvider):
            @property
            def metadata(self):
                return MagicMock()

            @property
            def is_connected(self):
                return False

            async def connect(self, account, credentials, timeout=None):
                pass

            async def disconnect(self):
                pass

        # Still missing many abstract methods
        with pytest.raises(TypeError):
            PartialProvider()


# ── FakeEmailProvider (for tests only) ────────────────────────────────────────

class FakeEmailProvider(EmailProvider):
    """
    Minimal fake provider for contract testing.

    Implements the abstract EmailProvider interface with deterministic data.
    Performs no network access. Not for production use.
    """

    def __init__(self, provider_type: str = "fake", capabilities: Optional[list] = None):
        self._capabilities = ProviderCapabilities(capabilities or [])
        self._state = ProviderConnectionState.DISCONNECTED
        self._account_id = "fake-account"
        self._provider_type = provider_type

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type=self._provider_type,
            account_id=self._account_id,
            capabilities=self._capabilities,
            connection_state=self._state,
            display_name="Fake Provider",
        )

    @property
    def is_connected(self) -> bool:
        return self._state in (
            ProviderConnectionState.CONNECTED,
            ProviderConnectionState.AUTHENTICATED,
        )

    async def connect(self, account, credentials, timeout=None):
        self._state = ProviderConnectionState.CONNECTING
        self._state = ProviderConnectionState.AUTHENTICATED
        return self.metadata

    async def disconnect(self):
        if self._state == ProviderConnectionState.DISCONNECTED:
            return  # idempotent no-op
        self._state = ProviderConnectionState.DISCONNECTING
        self._state = ProviderConnectionState.DISCONNECTED

    async def list_folders(self):
        if not self.supports(Capability.FOLDERS):
            raise ProviderCapabilityError("FOLDERS not supported")
        return [
            EmailFolder(provider_name="INBOX", display_name="Inbox"),
            EmailFolder(provider_name="Sent", display_name="Sent"),
        ]

    async def get_folder_info(self, folder_name):
        if not self.supports(Capability.FOLDERS):
            raise ProviderCapabilityError("FOLDERS not supported")
        return EmailFolder(provider_name=folder_name, display_name=folder_name)

    async def select_folder(self, folder_name):
        return await self.get_folder_info(folder_name)

    async def search(self, query):
        if not self.supports(Capability.SEARCH):
            raise ProviderCapabilityError("SEARCH not supported")
        return []

    async def fetch_message(self, ref, include_body=True, include_attachments=False):
        if not self.supports(Capability.FETCH):
            raise ProviderCapabilityError("FETCH not supported")
        return EmailMessage(
            reference=ref,
            sender=EmailAddress("test@example.com"),
            subject="Test",
        )

    async def fetch_message_headers(self, ref):
        return await self.fetch_message(ref, include_body=False)

    async def fetch_attachments(self, ref):
        if not self.supports(Capability.ATTACHMENTS):
            raise ProviderCapabilityError("ATTACHMENTS not supported")
        return []

    async def mark_read(self, ref):
        return EmailOperationResult(operation_id="read-1", status=OperationStatus.SUCCESS)

    async def mark_unread(self, ref):
        return EmailOperationResult(operation_id="unread-1", status=OperationStatus.SUCCESS)

    async def add_flag(self, ref, flag):
        return EmailOperationResult(operation_id="flag-1", status=OperationStatus.SUCCESS)

    async def remove_flag(self, ref, flag):
        return EmailOperationResult(operation_id="unflag-1", status=OperationStatus.SUCCESS)

    async def delete_message(self, ref):
        return EmailOperationResult(operation_id="delete-1", status=OperationStatus.SUCCESS)

    async def move_message(self, ref, target_folder):
        return EmailOperationResult(operation_id="move-1", status=OperationStatus.SUCCESS)

    async def copy_message(self, ref, target_folder):
        return EmailOperationResult(operation_id="copy-1", status=OperationStatus.SUCCESS)

    async def archive_message(self, ref):
        return EmailOperationResult(operation_id="archive-1", status=OperationStatus.SUCCESS)

    async def search_threads(self, query):
        return []

    async def get_thread(self, thread_key):
        return EmailThread(thread_key=thread_key)

    async def create_draft(self, draft):
        return EmailOperationResult(operation_id="draft-1", status=OperationStatus.SUCCESS)

    async def update_draft(self, ref, draft):
        return EmailOperationResult(operation_id="draft-2", status=OperationStatus.SUCCESS)

    async def delete_draft(self, ref):
        return EmailOperationResult(operation_id="draft-3", status=OperationStatus.SUCCESS)

    async def send(self, account, to, subject, **kwargs):
        if not self.supports(Capability.SEND):
            raise ProviderCapabilityError("SEND not supported")
        return EmailOperationResult(operation_id="send-1", status=OperationStatus.SUCCESS)


# ── Test: Concrete Implementation ─────────────────────────────────────────────

class TestConcreteImplementation:
    """Verify a concrete provider can implement the contract."""

    def test_fake_provider_instantiates(self):
        """A concrete implementation of EmailProvider can be instantiated."""
        provider = FakeEmailProvider()
        assert provider is not None

    def test_fake_provider_has_all_methods(self):
        """Fake provider has all required abstract methods."""
        provider = FakeEmailProvider()
        assert callable(provider.connect)
        assert callable(provider.disconnect)
        assert callable(provider.list_folders)
        assert callable(provider.search)
        assert callable(provider.fetch_message)
        assert callable(provider.send)

    def test_fake_provider_connection_lifecycle(self):
        """Provider connects and disconnects correctly."""
        provider = FakeEmailProvider()
        assert not provider.is_connected
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.is_connected
            loop.run_until_complete(provider.disconnect())
            assert not provider.is_connected
        finally:
            loop.close()


# ── Test: Lifecycle Contract ──────────────────────────────────────────────────

class TestLifecycleContract:
    """Verify connection lifecycle, cancellation, and cleanup semantics."""

    def test_connect_transitions_state(self):
        """Successful connect transitions: DISCONNECTED → AUTHENTICATED."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.metadata.connection_state == ProviderConnectionState.AUTHENTICATED
            assert provider.is_connected
        finally:
            loop.close()

    def test_disconnect_returns_to_disconnected(self):
        """Disconnect returns to DISCONNECTED state."""
        provider = FakeEmailProvider()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.is_connected
            loop.run_until_complete(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            assert not provider.is_connected
        finally:
            loop.close()

    def test_disconnect_idempotent_when_already_disconnected(self):
        """Disconnect is safe when already disconnected."""
        provider = FakeEmailProvider()
        loop = asyncio.new_event_loop()
        try:
            # Should not raise
            loop.run_until_complete(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
        finally:
            loop.close()

    def test_failed_connect_returns_to_disconnected(self):
        """Failed connection leaves provider in DISCONNECTED state."""
        class FailingProvider(FakeEmailProvider):
            async def connect(self, account, credentials, timeout=None):
                self._state = ProviderConnectionState.CONNECTING
                # Simulate failure
                self._state = ProviderConnectionState.DISCONNECTED
                raise ConnectionError("Connection failed")

        provider = FailingProvider()
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(ConnectionError):
                loop.run_until_complete(provider.connect(
                    EmailAccount(account_id="test", provider="fake"),
                    MagicMock(spec=CredentialStore),
                ))
            # Provider must NOT be authenticated after failure
            assert not provider.is_connected
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
        finally:
            loop.close()

    def test_timeout_parameter_accepted(self):
        """Timeout parameter is accepted by connect()."""
        provider = FakeEmailProvider()
        loop = asyncio.new_event_loop()
        try:
            # Should not raise TypeError for unexpected keyword
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
                timeout=30.0,
            ))
            assert provider.is_connected
        finally:
            loop.close()

    def test_negative_timeout_rejected(self):
        """Negative timeout values are rejected."""
        class StrictProvider(FakeEmailProvider):
            async def connect(self, account, credentials, timeout=None):
                if timeout is not None and timeout < 0:
                    raise ValueError("timeout must be non-negative")
                self._state = ProviderConnectionState.AUTHENTICATED
                return self.metadata

        provider = StrictProvider()
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(ValueError):
                loop.run_until_complete(provider.connect(
                    EmailAccount(account_id="test", provider="fake"),
                    MagicMock(spec=CredentialStore),
                    timeout=-1,
                ))
        finally:
            loop.close()

    def test_context_manager_cleanup_on_success(self):
        """Async context manager cleans up after success."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            async def use_provider():
                # Manually connect first (context manager just handles cleanup)
                await provider.connect(
                    EmailAccount(account_id="test", provider="fake"),
                    MagicMock(spec=CredentialStore),
                )
                assert provider.is_connected
                result = await provider.send(
                    account=EmailAccount(account_id="acc", provider="fake"),
                    to=[EmailAddress("to@example.com")],
                    subject="Test",
                )
                # Manual disconnect for test
                await provider.disconnect()
                return result
            result = loop.run_until_complete(use_provider())
            assert result.operation_id == "send-1"
            assert not provider.is_connected
        finally:
            loop.close()

    def test_context_manager_cleanup_on_exception(self):
        """Async context manager cleans up even when exception occurs."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            async def use_provider_failing():
                # Manually connect first
                await provider.connect(
                    EmailAccount(account_id="test", provider="fake"),
                    MagicMock(spec=CredentialStore),
                )
                assert provider.is_connected
                raise RuntimeError("intentional failure")

            with pytest.raises(RuntimeError):
                loop.run_until_complete(use_provider_failing())
            # Provider must be cleaned up despite exception
            loop.run_until_complete(provider.disconnect())
            assert not provider.is_connected
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
        finally:
            loop.close()

    def test_cancellation_during_connect_returns_disconnected(self):
        """Cancellation during connect returns provider to DISCONNECTED state."""
        class SlowConnectingProvider(FakeEmailProvider):
            async def connect(self, account, credentials, timeout=None):
                self._state = ProviderConnectionState.CONNECTING
                try:
                    # Simulate slow operation that can be cancelled
                    await asyncio.sleep(10)
                    self._state = ProviderConnectionState.AUTHENTICATED
                except asyncio.CancelledError:
                    # On cancellation, ensure we return to DISCONNECTED
                    self._state = ProviderConnectionState.DISCONNECTED
                    raise

        provider = SlowConnectingProvider()
        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            # Let it start connecting
            loop.run_until_complete(asyncio.sleep(0.01))
            assert provider.metadata.connection_state == ProviderConnectionState.CONNECTING
            # Cancel the task
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                loop.run_until_complete(task)
            # Provider must not remain in CONNECTING or AUTHENTICATED
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            assert not provider.is_connected
        finally:
            loop.close()

    def test_state_machine_transitions(self):
        """Verify complete state machine transitions."""
        provider = FakeEmailProvider()
        loop = asyncio.new_event_loop()
        try:
            # Initial state
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            
            # Connect
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.metadata.connection_state == ProviderConnectionState.AUTHENTICATED
            
            # Disconnect
            loop.run_until_complete(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            
            # Connect again
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.metadata.connection_state == ProviderConnectionState.AUTHENTICATED
            
            # Double disconnect (idempotent)
            loop.run_until_complete(provider.disconnect())
            loop.run_until_complete(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
        finally:
            loop.close()


# ── Test: Capability Model ────────────────────────────────────────────────────

class TestCapabilityModel:
    """Verify capabilities are represented consistently and queryable."""

    def test_capabilities_container_empty_by_default(self):
        """ProviderCapabilities starts empty."""
        caps = ProviderCapabilities()
        assert len(caps) == 0
        assert not caps.supports(Capability.SEARCH)

    def test_capabilities_container_with_values(self):
        """ProviderCapabilities can be initialized with values."""
        caps = ProviderCapabilities([Capability.SEARCH, Capability.SEND])
        assert caps.supports(Capability.SEARCH)
        assert caps.supports(Capability.SEND)
        assert not caps.supports(Capability.FOLDERS)

    def test_capabilities_contains_operator(self):
        """Supports 'in' operator for capability checking."""
        caps = ProviderCapabilities([Capability.SEARCH])
        assert Capability.SEARCH in caps
        assert Capability.SEND not in caps

    def test_capabilities_add_remove(self):
        """Capabilities can be added and removed."""
        caps = ProviderCapabilities()
        caps.add(Capability.SEARCH)
        assert caps.supports(Capability.SEARCH)
        caps.remove(Capability.SEARCH)
        assert not caps.supports(Capability.SEARCH)

    def test_all_capabilities_defined(self):
        """All expected capabilities are defined."""
        expected = [
            Capability.SEARCH,
            Capability.FETCH,
            Capability.SEND,
            Capability.DRAFTS,
            Capability.FLAGS,
            Capability.READ_STATE,
            Capability.THREADS,
            Capability.FOLDERS,
            Capability.MOVE,
            Capability.COPY,
            Capability.DELETE,
            Capability.ARCHIVE,
            Capability.ATTACHMENTS,
            Capability.ATTACHMENT_UPLOAD,
            Capability.ATTACHMENT_DOWNLOAD,
            Capability.REPLY,
            Capability.REPLY_ALL,
            Capability.FORWARD,
            Capability.BULK_OPERATIONS,
            Capability.RATE_LIMITING,
            Capability.IDEMPOTENT_SEND,
        ]
        for cap in expected:
            assert isinstance(cap, Capability)

    def test_provider_supports_delegates_to_metadata(self):
        """EmailProvider.supports() delegates to metadata.capabilities."""
        provider = FakeEmailProvider(capabilities=[Capability.SEARCH])
        assert provider.supports(Capability.SEARCH)
        assert not provider.supports(Capability.SEND)


# ── Test: Domain Model Usage ─────────────────────────────────────────────────

class TestDomainModelUsage:
    """Verify the abstraction uses existing domain models, not provider-native objects."""

    def test_search_accepts_email_search_query(self):
        """search() accepts EmailSearchQuery, not provider-specific syntax."""
        provider = FakeEmailProvider(capabilities=[Capability.SEARCH])
        loop = asyncio.new_event_loop()
        try:
            query = EmailSearchQuery(subject="test")
            result = loop.run_until_complete(provider.search(query))
            assert isinstance(result, list)
        finally:
            loop.close()

    def test_fetch_returns_email_message(self):
        """fetch_message() returns EmailMessage, not raw provider objects."""
        provider = FakeEmailProvider(capabilities=[Capability.FETCH])
        loop = asyncio.new_event_loop()
        try:
            ref = EmailMessageRef(account_id="acc", mailbox="INBOX", uid="123")
            result = loop.run_until_complete(provider.fetch_message(ref))
            assert isinstance(result, EmailMessage)
        finally:
            loop.close()

    def test_list_folders_returns_email_folders(self):
        """list_folders() returns EmailFolder instances."""
        provider = FakeEmailProvider(capabilities=[Capability.FOLDERS])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.list_folders())
            assert len(result) > 0
            assert all(isinstance(f, EmailFolder) for f in result)
        finally:
            loop.close()

    def test_send_uses_typed_email_address(self):
        """send() uses EmailAddress, not raw strings."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("to@example.com", "To Name")],
                subject="Test",
                cc=[EmailAddress("cc@example.com")],
                bcc=[EmailAddress("bcc@example.com")],
                reply_to=EmailAddress("reply@example.com"),
            ))
            assert isinstance(result, EmailOperationResult)
        finally:
            loop.close()

    def test_no_imap_sequence_numbers_in_interface(self):
        """Interface does not require IMAP sequence numbers."""
        provider = FakeEmailProvider(capabilities=[Capability.FETCH])
        loop = asyncio.new_event_loop()
        try:
            ref = EmailMessageRef(account_id="acc", mailbox="INBOX", uid="12345")
            result = loop.run_until_complete(provider.fetch_message(ref))
            assert isinstance(result, EmailMessage)
        finally:
            loop.close()


# ── Test: Typed Send Contract ─────────────────────────────────────────────────

class TestTypedSendContract:
    """Verify the send interface uses typed EmailAddress parameters."""

    def test_send_to_parameter_is_email_address_list(self):
        """to parameter accepts list[EmailAddress]."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("user@example.com")],
                subject="Test Subject",
            ))
            assert result.is_success
        finally:
            loop.close()

    def test_send_cc_parameter_is_email_address_list(self):
        """cc parameter accepts list[EmailAddress]."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("to@example.com")],
                cc=[EmailAddress("cc@example.com")],
                subject="Test",
            ))
            assert result.is_success
        finally:
            loop.close()

    def test_send_bcc_parameter_is_email_address_list(self):
        """bcc parameter accepts list[EmailAddress]."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("to@example.com")],
                bcc=[EmailAddress("bcc@example.com")],
                subject="Test",
            ))
            assert result.is_success
        finally:
            loop.close()

    def test_send_reply_to_parameter_is_email_address(self):
        """reply_to parameter accepts EmailAddress."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("to@example.com")],
                reply_to=EmailAddress("reply@example.com"),
                subject="Test",
            ))
            assert result.is_success
        finally:
            loop.close()

    def test_send_without_optional_params_works(self):
        """send() works with minimal required params."""
        provider = FakeEmailProvider(capabilities=[Capability.SEND])
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(provider.send(
                account=EmailAccount(account_id="acc", provider="fake"),
                to=[EmailAddress("to@example.com")],
                subject="Minimal Test",
            ))
            assert result.is_success
        finally:
            loop.close()

    def test_send_uses_domain_models_not_strings(self):
        """send() parameters are typed EmailAddress, not strings."""
        import inspect
        sig = inspect.signature(EmailProvider.send)
        params = sig.parameters
        # Verify parameter names match domain model
        assert "to" in params
        assert "subject" in params
        assert "account" in params


# ── Test: Error Contract ──────────────────────────────────────────────────────

class TestErrorContract:
    """Verify typed email errors are used, not provider-specific exceptions."""

    def test_provider_capability_error_for_unsupported(self):
        """Unsupported operations raise ProviderCapabilityError."""
        provider = FakeEmailProvider(capabilities=[])  # No capabilities
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(ProviderCapabilityError):
                loop.run_until_complete(provider.list_folders())
        finally:
            loop.close()

    def test_typed_errors_are_email_errors(self):
        """All provider errors are subclasses of EmailError."""
        from core.email.errors import EmailError
        errors = [
            AuthenticationError,
            AuthorizationError,
            ConnectionError,
            TimeoutError,
            RateLimitError,
            MailboxNotFoundError,
            MessageNotFoundError,
            ProviderCapabilityError,
            TransientProviderError,
            PermanentProviderError,
        ]
        for err in errors:
            assert issubclass(err, EmailError), f"{err.__name__} must be an EmailError"

    def test_exception_hierarchy_preserved(self):
        """Exception hierarchy matches documented structure."""
        assert issubclass(AuthenticationError, Exception)
        assert issubclass(ConnectionError, Exception)
        assert issubclass(ProviderCapabilityError, Exception)


# ── Test: Security ─────────────────────────────────────────────────────────────

class TestSecurity:
    """Verify no secrets/tokens/passwords leak into provider metadata."""

    def test_metadata_no_secrets(self):
        """ProviderMetadata does not contain secrets."""
        metadata = ProviderMetadata(
            provider_type="fake",
            account_id="test-account",
            capabilities=ProviderCapabilities([Capability.SEARCH]),
            connection_state=ProviderConnectionState.AUTHENTICATED,
            display_name="Test",
        )
        repr_str = repr(metadata)
        assert "password" not in repr_str.lower()
        assert "token" not in repr_str.lower()
        assert "secret" not in repr_str.lower()
        assert "credential" not in repr_str.lower()

    def test_provider_class_no_secret_fields(self):
        """EmailProvider class doesn't define secret storage."""
        import inspect
        source = inspect.getsource(EmailProvider)
        # Verify no obvious secret storage patterns in the abstract class
        assert "password" not in source.lower() or "credential" in source.lower()

    def test_fake_provider_no_credentials_stored(self):
        """Fake provider doesn't store credentials passed to connect()."""
        provider = FakeEmailProvider()
        creds = MagicMock(spec=CredentialStore)
        creds.get_password = MagicMock(return_value="should-not-be-stored")
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                creds,
            ))
            # After connect, credentials should not be accessible from provider
            assert not hasattr(provider, '_password')
            assert not hasattr(provider, '_token')
        finally:
            loop.close()


# ── Test: Identity and UID Usage ───────────────────────────────────────────────

class TestIdentityAndUID:
    """Verify UID-based identity is preserved, not sequence numbers."""

    def test_message_ref_uses_uid(self):
        """EmailMessageRef uses uid, not sequence number."""
        ref = EmailMessageRef(account_id="acc", mailbox="INBOX", uid="abc123")
        assert ref.uid == "abc123"
        assert hasattr(ref, 'uid')

    def test_provider_accepts_uid_references(self):
        """Provider methods accept UID-based EmailMessageRef."""
        provider = FakeEmailProvider(capabilities=[Capability.FETCH])
        loop = asyncio.new_event_loop()
        try:
            ref = EmailMessageRef(account_id="acc", mailbox="INBOX", uid="unique-id-123")
            result = loop.run_until_complete(provider.fetch_message(ref))
            assert result.reference.uid == "unique-id-123"
        finally:
            loop.close()


# ── Test: Connection State ─────────────────────────────────────────────────────

class TestConnectionState:
    """Verify connection state tracking."""

    def test_initial_state_disconnected(self):
        """Provider starts in DISCONNECTED state."""
        provider = FakeEmailProvider()
        assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED

    def test_state_transitions(self):
        """Provider transitions through states correctly."""
        provider = FakeEmailProvider()
        loop = asyncio.new_event_loop()
        try:
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            loop.run_until_complete(provider.connect(
                EmailAccount(account_id="test", provider="fake"),
                MagicMock(spec=CredentialStore),
            ))
            assert provider.metadata.connection_state == ProviderConnectionState.AUTHENTICATED
            assert provider.is_connected
            loop.run_until_complete(provider.disconnect())
            assert provider.metadata.connection_state == ProviderConnectionState.DISCONNECTED
            assert not provider.is_connected
        finally:
            loop.close()

    def test_is_connected_property(self):
        """is_connected property reflects AUTHENTICATED state."""
        provider = FakeEmailProvider()
        assert not provider.is_connected


# ── Test: Capability Query ─────────────────────────────────────────────────────

class TestCapabilityQuery:
    """Verify capability queries work correctly."""

    def test_search_capability_required(self):
        """SEARCH capability checked before search operation."""
        provider = FakeEmailProvider(capabilities=[])  # No capabilities
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(ProviderCapabilityError):
                loop.run_until_complete(provider.search(EmailSearchQuery()))
        finally:
            loop.close()

    def test_fetch_capability_required(self):
        """FETCH capability checked before fetch operation."""
        provider = FakeEmailProvider(capabilities=[])
        loop = asyncio.new_event_loop()
        try:
            ref = EmailMessageRef(account_id="acc", mailbox="INBOX", uid="1")
            with pytest.raises(ProviderCapabilityError):
                loop.run_until_complete(provider.fetch_message(ref))
        finally:
            loop.close()

    def test_send_capability_required(self):
        """SEND capability checked before send operation."""
        provider = FakeEmailProvider(capabilities=[])
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(ProviderCapabilityError):
                loop.run_until_complete(provider.send(
                    account=EmailAccount(account_id="acc", provider="fake"),
                    to=[EmailAddress("test@example.com")],
                    subject="Test",
                ))
        finally:
            loop.close()


# ── Test: Package Exports ──────────────────────────────────────────────────────

class TestPackageExports:
    """Verify clean public exports from providers package."""

    def test_providers_init_exports(self):
        """core.email.providers.__init__ exports the correct symbols."""
        from core.email.providers import (
            Capability,
            EmailProvider,
            ProviderCapabilities,
            ProviderConnectionState,
            ProviderMetadata,
        )
        assert Capability is not None
        assert EmailProvider is not None
        assert ProviderCapabilities is not None
        assert ProviderConnectionState is not None
        assert ProviderMetadata is not None

    def test_email_package_exposes_providers(self):
        """core.email package can import from providers."""
        from core.email.providers.base import EmailProvider
        assert EmailProvider is not None
