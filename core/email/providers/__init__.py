"""
core/email/providers — Provider abstraction package.

This package defines the provider-neutral interface that all email backend
implementations (IMAP/SMTP, Gmail API/OAuth, Microsoft Graph/OAuth) must satisfy.

See docs/email-engine-v2/03-provider-abstraction.md for the full specification.
"""
from __future__ import annotations

from .base import (
    Capability,
    EmailProvider,
    ProviderCapabilities,
    ProviderConnectionState,
    ProviderMetadata,
)

__all__ = [
    "Capability",
    "ProviderCapabilities",
    "ProviderConnectionState",
    "ProviderMetadata",
    "EmailProvider",
]
