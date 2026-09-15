"""Gmail API provider behind the provider-neutral EmailProvider contract."""
from __future__ import annotations

from typing import Any

from .oauth import OAuthProviderBase
from .base import Capability


class GmailProvider(OAuthProviderBase):
    """Provider-neutral Gmail implementation.

    ``client`` is an adapter with methods documented by the internal provider
    boundary (authenticate, refresh, search, get_message, list_folders, etc.).
    This keeps Google SDK objects out of the EmailService/action boundary.
    """
    provider_type = "gmail"
    capabilities = (
        Capability.SEARCH, Capability.FETCH, Capability.SEND, Capability.DRAFTS,
        Capability.FLAGS, Capability.READ_STATE, Capability.THREADS, Capability.FOLDERS,
        Capability.MOVE, Capability.COPY, Capability.DELETE, Capability.ARCHIVE,
        Capability.ATTACHMENTS, Capability.ATTACHMENT_DOWNLOAD, Capability.REPLY,
        Capability.REPLY_ALL, Capability.FORWARD, Capability.RATE_LIMITING,
        Capability.IDEMPOTENT_SEND,
    )

    def __init__(self, client: Any = None) -> None:
        super().__init__(client)
