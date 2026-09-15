"""Deterministic email provider discovery and selection."""
from __future__ import annotations
from typing import Callable, Mapping
from ..models import EmailAccount
from ..errors import ProviderCapabilityError

class EmailProviderRegistry:
    """Maps explicit account.provider values to exactly one provider factory."""
    def __init__(self, factories: Mapping[str, Callable[[], object]] | None = None):
        self._factories = dict(factories or {})
    def register(self, provider_type: str, factory: Callable[[], object]) -> None:
        if not provider_type.strip(): raise ValueError("provider_type must not be empty")
        if provider_type in self._factories: raise ValueError(f"Provider already registered: {provider_type}")
        self._factories[provider_type] = factory
    def discover(self, account: EmailAccount) -> object:
        provider_type = account.provider.strip().lower()
        factory = self._factories.get(provider_type)
        if factory is None: raise ProviderCapabilityError(f"No provider registered for account provider '{provider_type}'")
        provider = factory()
        if getattr(provider, "provider_type", None) != provider_type:
            raise ProviderCapabilityError("Provider registry returned an incompatible provider")
        return provider
    def provider_types(self) -> tuple[str, ...]: return tuple(sorted(self._factories))
