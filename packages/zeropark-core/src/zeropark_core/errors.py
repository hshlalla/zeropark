"""Typed error hierarchy so callers can distinguish config vs capability vs
routing failures and map them to HTTP status codes at the edge.
"""

from __future__ import annotations


class ZeroparkError(Exception):
    """Base class for all Zeropark errors."""


class ProviderNotConfigured(ZeroparkError):
    def __init__(self, provider_id: str, detail: str | None = None) -> None:
        self.provider_id = provider_id
        super().__init__(detail or f"Provider '{provider_id}' is not configured.")


class CapabilityNotSupported(ZeroparkError):
    """The provider does not advertise this capability at all."""

    def __init__(self, provider_id: str, capability: object) -> None:
        self.provider_id = provider_id
        self.capability = capability
        super().__init__(f"Provider '{provider_id}' does not support capability '{capability}'.")


class CapabilityNotImplemented(ZeroparkError):
    """The provider advertises the capability but is missing its handler."""

    def __init__(self, provider_id: str, capability: object) -> None:
        self.provider_id = provider_id
        self.capability = capability
        super().__init__(
            f"Provider '{provider_id}' advertises '{capability}' but has no cap_{capability} handler."
        )


class NoProviderForCapability(ZeroparkError):
    def __init__(self, capability: object) -> None:
        self.capability = capability
        super().__init__(f"No registered provider can serve capability '{capability}'.")
