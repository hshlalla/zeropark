"""Normalized, transport-agnostic data shapes.

Every engine returns something different; these types are the single normalized
contract the product layer and UI consume. Adapters translate engine-native
responses INTO these types so that no engine-specific shape ever leaks upward.
This is what lets us add/replace engines without rewriting the product or UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from zeropark_core.capabilities import Capability


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskRequest(BaseModel):
    """A single unit of work targeting one capability."""

    prompt: str = Field(min_length=1)
    capability: Capability
    params: dict[str, Any] = Field(default_factory=dict)
    # Optional hard pin to a specific provider id; otherwise the router decides.
    provider_id: str | None = None
    tenant: str | None = None


class SourceRef(BaseModel):
    """A citation/source surfaced by search, crawl, or research."""

    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    score: float | None = None
    provider_id: str | None = None


ArtifactKind = Literal[
    "report", "deck", "sheet", "page", "file", "data", "message", "image", "audio"
]


class Artifact(BaseModel):
    """A produced output. `uri` points at durable storage; `inline` carries small
    payloads returned synchronously."""

    id: str
    kind: ArtifactKind
    title: str | None = None
    mime_type: str | None = None
    uri: str | None = None
    inline: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


EventType = Literal["status", "log", "source", "artifact", "error", "token", "done", "pause"]


class RunEvent(BaseModel):
    """A streamed progress event. The web shell renders a timeline from these."""

    type: EventType
    task_id: str
    provider_id: str | None = None
    at: datetime = Field(default_factory=_utcnow)
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Terminal, normalized result of a task."""

    task_id: str
    status: TaskStatus
    capability: Capability
    provider_id: str
    artifacts: list[Artifact] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    # Observability: latency_ms, cost_estimate, model, retries, source_count, ...
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ProviderHealth(BaseModel):
    provider_id: str
    ok: bool
    detail: str | None = None
    latency_ms: float | None = None
