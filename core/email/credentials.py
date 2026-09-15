"""Secure credential storage for the Email Engine.

Secrets are deliberately separated from account configuration. Production uses
an OS credential manager through ``keyring``; tests can inject a backend or use
``InMemoryCredentialStore``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

_SECRET_KEYS = {
    "password", "passwd", "secret", "client_secret", "access_token",
    "refresh_token", "id_token", "token", "authorization", "authorization_code",
}
_ALLOWED_OAUTH_CONFIG_KEYS = {
    "client_id", "authorization_uri", "token_uri", "scopes", "redirect_uri",
    "tenant_id", "authority", "cloud", "api_base_url",
}


class CredentialStore(ABC):
    @abstractmethod
    def get_password(self, service: str, username: str) -> Optional[str]: ...

    @abstractmethod
    def set_password(self, service: str, username: str, password: str) -> None: ...

    @abstractmethod
    def delete_password(self, service: str, username: str) -> None: ...

    @abstractmethod
    def get_token(self, service: str, token_type: str) -> Optional[str]: ...

    @abstractmethod
    def set_token(self, service: str, token_type: str, token: str, expires_at: Optional[float] = None) -> None: ...

    @abstractmethod
    def delete_token(self, service: str, token_type: str) -> None: ...

    def get_token_expiry(self, service: str, token_type: str) -> Optional[float]:
        """Return token expiry without exposing token material."""
        return None


class CredentialSecurityError(ValueError):
    """Raised when a secret is about to cross the configuration boundary."""


@dataclass
class EmailCredentials:
    email_address: str
    smtp_server: str
    smtp_port: int
    imap_server: str
    imap_port: int
    password_ref: Optional[str] = None
    oauth_config: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._validate_oauth_config(self.oauth_config)

    @staticmethod
    def _validate_oauth_config(config: dict) -> None:
        if not isinstance(config, dict):
            raise CredentialSecurityError("oauth_config must be a mapping")
        secret_names = {str(k).lower() for k in config} & _SECRET_KEYS
        if secret_names:
            raise CredentialSecurityError("oauth_config contains secret material")
        unknown = set(config) - _ALLOWED_OAUTH_CONFIG_KEYS
        if unknown:
            raise CredentialSecurityError("oauth_config contains unsupported fields")

    @classmethod
    def from_config(cls, email_address: str, smtp_server: str, smtp_port: int,
                    imap_server: str, imap_port: int, password_ref: Optional[str] = None,
                    oauth_config: Optional[dict] = None) -> "EmailCredentials":
        return cls(email_address, smtp_server, smtp_port, imap_server, imap_port,
                   password_ref, dict(oauth_config or {}))

    def to_dict(self) -> dict:
        self._validate_oauth_config(self.oauth_config)
        return {
            "email_address": self.email_address,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "imap_server": self.imap_server,
            "imap_port": self.imap_port,
            "password_ref": self.password_ref,
            "oauth_config": dict(self.oauth_config),
        }


class InMemoryCredentialStore(CredentialStore):
    """Test-only credential store; never use for persistent production secrets."""
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

    def set_token(self, service: str, token_type: str, token: str, expires_at: Optional[float] = None) -> None:
        self._tokens[(service, token_type)] = (token, expires_at)

    def delete_token(self, service: str, token_type: str) -> None:
        self._tokens.pop((service, token_type), None)

    def get_token_expiry(self, service: str, token_type: str) -> Optional[float]:
        entry = self._tokens.get((service, token_type))
        return entry[1] if entry else None


class KeyringCredentialStore(CredentialStore):
    """Production credential store backed by the operating system keyring."""
    _EXPIRY_PREFIX = "__mark_liii_email_expiry__"

    def __init__(self, *, keyring_backend: Any = None, keyring_module: Any = None) -> None:
        if keyring_backend is not None:
            self._backend = keyring_backend
            self._keyring = None
            return
        if keyring_module is None:
            try:
                import keyring as keyring_module
            except ImportError as exc:
                raise RuntimeError("keyring package is required for production credential storage") from exc
        self._keyring = keyring_module
        try:
            self._backend = keyring_module.get_keyring()
        except Exception as exc:
            raise RuntimeError("OS credential manager is unavailable") from exc

    def _get(self, service: str, username: str) -> Optional[str]:
        try:
            if self._keyring is not None:
                return self._keyring.get_password(service, username)
            return self._backend.get_password(service, username)
        except Exception as exc:
            raise RuntimeError("credential manager read failed") from exc

    def _set(self, service: str, username: str, value: str) -> None:
        try:
            if self._keyring is not None:
                self._keyring.set_password(service, username, value)
            else:
                self._backend.set_password(service, username, value)
        except Exception as exc:
            raise RuntimeError("credential manager write failed") from exc

    def _delete(self, service: str, username: str) -> None:
        try:
            if self._keyring is not None:
                self._keyring.delete_password(service, username)
            else:
                self._backend.delete_password(service, username)
        except Exception as exc:
            raise RuntimeError("credential manager delete failed") from exc

    def get_password(self, service: str, username: str) -> Optional[str]:
        return self._get(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        self._set(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        self._delete(service, username)

    def get_token(self, service: str, token_type: str) -> Optional[str]:
        return self._get(service, f"token:{token_type}")

    def set_token(self, service: str, token_type: str, token: str, expires_at: Optional[float] = None) -> None:
        self._set(service, f"token:{token_type}", token)
        if expires_at is not None:
            self._set(service, f"{self._EXPIRY_PREFIX}:{token_type}", str(float(expires_at)))

    def delete_token(self, service: str, token_type: str) -> None:
        self._delete(service, f"token:{token_type}")
        try:
            self._delete(service, f"{self._EXPIRY_PREFIX}:{token_type}")
        except RuntimeError:
            pass

    def get_token_expiry(self, service: str, token_type: str) -> Optional[float]:
        value = self._get(service, f"{self._EXPIRY_PREFIX}:{token_type}")
        return float(value) if value is not None else None
