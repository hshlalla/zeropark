"""Zeropark core: the engine-agnostic spine of the framework.

Nothing here imports an engine. It defines capabilities, the Provider interface,
the registry, the router, normalized models, and deployment config. Native engine
implementations live in `zeropark-engines`.
"""

from zeropark_core.capabilities import Capability
from zeropark_core.config import LLMConfig, SearchConfig, ZeroparkSettings
from zeropark_core.errors import (
    CapabilityNotImplemented,
    CapabilityNotSupported,
    NoProviderForCapability,
    ProviderNotConfigured,
    ZeroparkError,
)
from zeropark_core.models import (
    Artifact,
    ProviderHealth,
    RunEvent,
    SourceRef,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from zeropark_core.provider import Provider
from zeropark_core.registry import ProviderRegistry
from zeropark_core.router import DEFAULT_MODES, ModePlan, Router
from zeropark_core.store import ArtifactStore, LocalArtifactStore

__all__ = [
    "Capability",
    "LLMConfig",
    "SearchConfig",
    "ZeroparkSettings",
    "ZeroparkError",
    "ProviderNotConfigured",
    "CapabilityNotSupported",
    "CapabilityNotImplemented",
    "NoProviderForCapability",
    "Artifact",
    "ArtifactStore",
    "LocalArtifactStore",
    "ProviderHealth",
    "RunEvent",
    "SourceRef",
    "TaskRequest",
    "TaskResult",
    "TaskStatus",
    "Provider",
    "ProviderRegistry",
    "Router",
    "ModePlan",
    "DEFAULT_MODES",
]
