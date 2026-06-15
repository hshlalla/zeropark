"""API-facing request DTOs. Response shapes come straight from zeropark-core
(TaskResult, etc.) so the wire contract and the internal contract never diverge.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    prompt: str = Field(min_length=1)
    mode: str = "super_agent"


class TaskCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    mode: str = "super_agent"
    params: dict[str, Any] = Field(default_factory=dict)
    provider_id: str | None = None
    tenant: str | None = None
    # Conversation memory (Dify-style): when set, the gateway loads this
    # session's recent messages into the task context and persists the new
    # user/assistant turns after the run.
    session_id: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    provider_id: str | None = None


class CrawlRequest(BaseModel):
    url: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    provider_id: str | None = None


class SlidesRequest(BaseModel):
    content: str = Field(min_length=1)
    n_slides: int = Field(default=8, ge=1, le=40)
    language: str = "English"
    template: str = "general"
    export_as: str = "pptx"
    instructions: str | None = None
    provider_id: str | None = None
