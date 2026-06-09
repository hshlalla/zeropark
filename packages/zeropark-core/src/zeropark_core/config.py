"""Configuration for a single, self-contained framework deployment.

Because engines are NATIVE (no external services), config is about the framework
itself: where to write artifacts, which LLM to call for generative steps, and an
optional commodity search backend. A deployment = same code + this config; that is
the seam that makes Zeropark resellable per client.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """Provider-agnostic LLM target (OpenAI-compatible endpoints recommended)."""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class SearchConfig(BaseModel):
    """Commodity search API used by the native search engine (NOT SearXNG)."""

    base_url: str | None = None
    api_key: str | None = None
    query_param: str = "q"
    results_key: str = "results"


class ZeroparkSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZEROPARK_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    tenant: str | None = None
    output_dir: str = "artifacts"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    # capability value -> ordered preferred engine ids
    capability_preferences: dict[str, list[str]] = Field(default_factory=dict)

    def search_kwargs(self) -> dict[str, object] | None:
        """Engine kwargs for the native search engine, or None if unconfigured."""
        if not self.search.base_url:
            return None
        return {
            "base_url": self.search.base_url,
            "api_key": self.search.api_key,
            "query_param": self.search.query_param,
            "results_key": self.search.results_key,
        }
