"""ProviderRegistry: the live index of configured engines.

The registry is the only place that knows which concrete providers exist in a
given deployment. Product code asks the registry "who can do X?" and never
imports an adapter directly. This is what makes a deployment a matter of
*configuration* (which providers get registered) rather than code — exactly what
a resold, per-client build needs.
"""

from __future__ import annotations

from zeropark_core.capabilities import Capability
from zeropark_core.errors import ProviderNotConfigured
from zeropark_core.provider import Provider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"Provider id '{provider.id}' already registered.")
        self._providers[provider.id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> Provider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderNotConfigured(provider_id) from exc

    def all(self) -> list[Provider]:
        return list(self._providers.values())

    def for_capability(self, capability: Capability) -> list[Provider]:
        """Providers that support `capability`, in registration order."""
        return [p for p in self._providers.values() if p.supports(capability)]

    def capabilities(self) -> set[Capability]:
        caps: set[Capability] = set()
        for provider in self._providers.values():
            caps |= set(provider.capabilities)
        return caps

    def __contains__(self, provider_id: object) -> bool:
        return provider_id in self._providers

    def __len__(self) -> int:
        return len(self._providers)
