"""Security-first tests for production email credential storage."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.credentials import CredentialStore, EmailCredentials, InMemoryCredentialStore, KeyringCredentialStore

SECRET_PASSWORD = "super-secret-password-7f4c"
SECRET_ACCESS = "access-secret-8a2d"
SECRET_REFRESH = "refresh-secret-9b3e"


class TestCredentialStoreInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            CredentialStore()  # type: ignore

    def test_requires_get_password(self):
        class Partial(CredentialStore):
            pass
        with pytest.raises(TypeError):
            Partial()

    def test_complete_implementation_is_instantiable(self):
        class Partial(CredentialStore):
            def get_password(self, service, username): return None
            def set_password(self, service, username, password): pass
            def delete_password(self, service, username): pass
            def get_token(self, service, token_type): return None
            def set_token(self, service, token_type, token, expires_at=None): pass
            def delete_token(self, service, token_type): pass
        assert Partial() is not None


class TestInMemoryCredentialStore:
    def test_round_trip_password(self):
        store = InMemoryCredentialStore()
        store.set_password("smtp.example.com", "user@example.com", "secret123")
        assert store.get_password("smtp.example.com", "user@example.com") == "secret123"

    def test_round_trip_token_and_expiry(self):
        store = InMemoryCredentialStore()
        store.set_token("oauth", "access", "token123", expires_at=1000.0)
        assert store.get_token("oauth", "access") == "token123"
        assert store.get_token_expiry("oauth", "access") == 1000.0

    def test_delete_credentials(self):
        store = InMemoryCredentialStore()
        store.set_password("s", "u", "p")
        store.set_token("s", "t", "tok")
        store.delete_password("s", "u")
        store.delete_token("s", "t")
        assert store.get_password("s", "u") is None
        assert store.get_token("s", "t") is None


class TestKeyringCredentialStore:
    def test_round_trip_uses_backend_and_keeps_expiry_separately(self):
        class FakeKeyring:
            def __init__(self): self.values = {}
            def get_password(self, service, username): return self.values.get((service, username))
            def set_password(self, service, username, password): self.values[(service, username)] = password
            def delete_password(self, service, username): self.values.pop((service, username), None)

        backend = FakeKeyring()
        store = KeyringCredentialStore(keyring_backend=backend)
        store.set_password("mark.email", "acct-1", SECRET_PASSWORD)
        store.set_token("mark.email/acct-1", "access", SECRET_ACCESS, expires_at=123.0)
        store.set_token("mark.email/acct-1", "refresh", SECRET_REFRESH)
        assert store.get_password("mark.email", "acct-1") == SECRET_PASSWORD
        assert store.get_token("mark.email/acct-1", "access") == SECRET_ACCESS
        assert store.get_token_expiry("mark.email/acct-1", "access") == 123.0
        assert store.get_token("mark.email/acct-1", "refresh") == SECRET_REFRESH

    def test_missing_optional_dependency_fails_closed(self):
        with pytest.raises(RuntimeError):
            KeyringCredentialStore(keyring_backend=None, keyring_module=None)


class TestEmailCredentials:
    def test_rejects_secret_oauth_fields(self):
        creds = EmailCredentials.from_config(
            email_address="user@example.com", smtp_server="smtp.example.com", smtp_port=465,
            imap_server="imap.example.com", imap_port=993, password_ref="email/user",
            oauth_config={"client_id": "public", "access_token": SECRET_ACCESS,
                          "refresh_token": SECRET_REFRESH, "client_secret": SECRET_PASSWORD},
        )
        with pytest.raises(ValueError):
            creds.to_dict()

    def test_serialization_contains_only_allowlisted_oauth_metadata(self):
        creds = EmailCredentials.from_config(
            email_address="user@example.com", smtp_server="smtp.example.com", smtp_port=465,
            imap_server="imap.example.com", imap_port=993,
            oauth_config={"client_id": "public", "token_uri": "https://oauth.example/token"},
        )
        serialized = json.dumps(creds.to_dict())
        assert "client_id" in serialized and "token_uri" in serialized
        assert SECRET_ACCESS not in serialized and SECRET_REFRESH not in serialized
        assert SECRET_PASSWORD not in serialized
        assert "access_token" not in serialized and "refresh_token" not in serialized

    def test_no_secret_attributes(self):
        creds = EmailCredentials("user@example.com", "smtp.example.com", 587, "imap.example.com", 993)
        assert not hasattr(creds, "password")
        assert not hasattr(creds, "secret")
        assert not hasattr(creds, "token")
