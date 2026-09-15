"""Provider abstraction and production email provider implementations."""
from .base import Capability, EmailProvider, ProviderCapabilities, ProviderConnectionState, ProviderMetadata
from .gmail import GmailProvider
from .microsoft import MicrosoftProvider
from .registry import EmailProviderRegistry
__all__=["Capability","EmailProvider","ProviderCapabilities","ProviderConnectionState","ProviderMetadata","GmailProvider","MicrosoftProvider","EmailProviderRegistry"]
