"""
core/email/credentials.py — Credential abstraction interface.

This module defines the interface for secure credential storage and retrieval.
Concrete implementations (OS keyring, encrypted vault, etc.) should be added
in later phases.

IMPORTANT: No plaintext passwords, OAuth tokens, or secrets are stored here.
Credential values are always handled through the abstraction interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class CredentialStore(ABC):
    """
    Abstract interface for credential storage and retrieval.

    Concrete implementations should:
    - Use OS keyring (keyring, SecretService, Keychain) for passwords
    - Use encrypted storage for OAuth tokens
    - Never write secrets to plaintext files
    - Never log credential values
    """

    @abstractmethod
    def get_password(self, service: str, username: str) -> Optional[str]:
        """Retrieve a password for the given service/username pair."""
        ...

    @abstractmethod
    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a password securely."""
        ...

    @abstractmethod
    def delete_password(self, service: str, username: str) -> None:
        """Remove stored credentials."""
        ...

    @abstractmethod
    def get_token(self, service: str, token_type: str) -> Optional[str]:
        """Retrieve an OAuth token (access or refresh)."""
        ...

    @abstractmethod
    def set_token(
        self, service: str, token_type: str, token: str, expires_at: Optional[float] = None
    ) -> None:
        """Store an OAuth token securely."""
        ...

    @abstractmethod
    def delete_token(self, service: str, token_type: str) -> None:
        """Remove stored OAuth token."""
        ...


@dataclass
class EmailCredentials:
    """
    Non-secret email configuration.

    This class holds everything EXCEPT the actual password/token.
    Concrete credential values must be obtained through a CredentialStore.
    """
    email_address: str
    smtp_server: str
    smtp_port: int
    imap_server: str
    imap_port: int
    # Store references to where credentials live, not the credentials themselves
    password_ref: Optional[str] = None  # e.g. "keyring:smtp.example.com:user"
    oauth_config: dict = field(default_factory=dict)  # provider-specific, non-secret config

    @classmethod
    def from_config(
        cls,
        email_address: str,
        smtp_server: str,
        smtp_port: int,
        imap_server: str,
        imap_port: int,
        password_ref: Optional[str] = None,
        oauth_config: Optional[dict] = None,
    ) -> EmailCredentials:
        """Create EmailCredentials from config (no secrets)."""
        return cls(
            email_address=email_address,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            imap_server=imap_server,
            imap_port=imap_port,
            password_ref=password_ref,
            oauth_config=oauth_config or {},
        )

    def to_dict(self) -> dict:
        """Serialize to dict — never includes actual secret values."""
        return {
            "email_address": self.email_address,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "imap_server": self.imap_server,
            "imap_port": self.imap_port,
            "password_ref": self.password_ref,
            "oauth_config": self.oauth_config,
        }


class InMemoryCredentialStore(CredentialStore):
    """
    In-memory credential store for testing only.

    DO NOT use this in production — it does not persist credentials securely.
    """

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}
        self._tokens: dict[tuple[str, str], tuple[str, Optional[float]]] = {}

    def get_password(self, service: str, username: str) -> Optional[str]:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)

    def get_token(self, service: str, token_type: str) -> Optional[str]:
        entry = self._tokens.get((service, token_type))
        return entry[0] if entry else None

    def set_token(
        self, service: str, token_type: str, token: str, expires_at: Optional[float] = None
    ) -> None:
        self._tokens[(service, token_type)] = (token, expires_at)

    def delete_token(self, service: str, token_type: str) -> None:
        self._tokens.pop((service, token_type), None)
