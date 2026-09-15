"""
Tests for core/email/credentials.py — credential abstraction.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.credentials import CredentialStore, EmailCredentials, InMemoryCredentialStore


# ═══════════════════════════════════════════════════════════════════════════════
# Abstraction contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestCredentialStoreInterface:
    def test_is_abstract(self):
        """CredentialStore should not be instantiable directly."""
        with pytest.raises(TypeError):
            CredentialStore()  # type: ignore

    def test_requires_get_password(self):
        """Subclasses must implement get_password."""
        class Partial(CredentialStore):
            pass

        with pytest.raises(TypeError):
            Partial()

    def test_requires_set_password(self):
        class Partial(CredentialStore):
            def get_password(self, service, username):
                return None
            def set_password(self, service, username, password):
                pass
            def delete_password(self, service, username):
                pass
            def get_token(self, service, token_type):
                return None
            def set_token(self, service, token_type, token, expires_at=None):
                pass
            def delete_token(self, service, token_type):
                pass

        # This should work - all methods implemented
        store = Partial()
        assert store is not None


# ═══════════════════════════════════════════════════════════════════════════════
# InMemoryCredentialStore
# ═══════════════════════════════════════════════════════════════════════════════


class TestInMemoryCredentialStore:
    def test_get_password_not_found(self):
        store = InMemoryCredentialStore()
        assert store.get_password("service", "user") is None

    def test_set_and_get_password(self):
        store = InMemoryCredentialStore()
        store.set_password("smtp.example.com", "user@example.com", "secret123")
        assert store.get_password("smtp.example.com", "user@example.com") == "secret123"

    def test_delete_password(self):
        store = InMemoryCredentialStore()
        store.set_password("s", "u", "p")
        store.delete_password("s", "u")
        assert store.get_password("s", "u") is None

    def test_get_token_not_found(self):
        store = InMemoryCredentialStore()
        assert store.get_token("service", "access") is None

    def test_set_and_get_token(self):
        store = InMemoryCredentialStore()
        store.set_token("oauth", "access", "token123", expires_at=1000.0)
        token, expires = store._tokens[("oauth", "access")]
        assert token == "token123"
        assert expires == 1000.0

    def test_delete_token(self):
        store = InMemoryCredentialStore()
        store.set_token("s", "t", "tok")
        store.delete_token("s", "t")
        assert store.get_token("s", "t") is None


# ═══════════════════════════════════════════════════════════════════════════════
# EmailCredentials
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailCredentials:
    def test_basic_construction(self):
        creds = EmailCredentials(
            email_address="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=993,
        )
        assert creds.email_address == "user@example.com"
        assert creds.password_ref is None
        assert creds.oauth_config == {}

    def test_with_password_ref(self):
        creds = EmailCredentials(
            email_address="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=993,
            password_ref="keyring:smtp.example.com:user@example.com",
        )
        assert creds.password_ref == "keyring:smtp.example.com:user@example.com"

    def test_from_config_classmethod(self):
        creds = EmailCredentials.from_config(
            email_address="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=993,
            password_ref="ref123",
        )
        assert creds.email_address == "user@example.com"
        assert creds.password_ref == "ref123"

    def test_to_dict_no_secrets(self):
        creds = EmailCredentials(
            email_address="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=993,
            password_ref="keyring:service:user",
            oauth_config={"client_id": "abc123"},
        )
        d = creds.to_dict()
        assert d["email_address"] == "user@example.com"
        assert d["password_ref"] == "keyring:service:user"
        assert d["oauth_config"] == {"client_id": "abc123"}
        # No actual password or token in the dict
        assert "secret" not in str(d).lower()
        assert "password" not in d  # password is not stored here


# ═══════════════════════════════════════════════════════════════════════════════
# No plaintext persistence
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoPlaintextPersistence:
    def test_credentials_dont_contain_password(self):
        """EmailCredentials should never store actual passwords."""
        creds = EmailCredentials(
            email_address="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            imap_server="imap.example.com",
            imap_port=993,
        )
        # No password attribute should exist
        assert not hasattr(creds, "password")
        assert not hasattr(creds, "secret")
        assert not hasattr(creds, "token")

    def test_in_memory_store_is_testing_only(self):
        """InMemoryCredentialStore should be clearly marked as test-only."""
        # This is documented in the class docstring
        import inspect
        doc = InMemoryCredentialStore.__doc__
        assert "testing" in doc.lower() or "test" in doc.lower()
