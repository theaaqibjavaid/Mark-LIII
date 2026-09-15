"""Microsoft Graph email provider behind the provider-neutral contract."""
from __future__ import annotations

from typing import Any

from .oauth import OAuthProviderBase
from .base import Capability


class MicrosoftProvider(OAuthProviderBase):
    """Provider-neutral Microsoft 365/Outlook implementation.

    The injected client is a Graph adapter. Raw Graph responses and bearer
    tokens remain inside the adapter/provider boundary.
    """
    provider_type = "microsoft"
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
