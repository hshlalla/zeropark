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
    # comma-separated list of models admins may pick per agent
    # (e.g. ZEROPARK_LLM__MODELS=gpt-4o,gpt-4o-mini,gpt-5-nano)
    models: str | None = None

    def model_choices(self) -> list[str]:
        choices = [m.strip() for m in (self.models or "").split(",") if m.strip()]
        if self.model and self.model not in choices:
            choices.insert(0, self.model)
        return choices


class SearchConfig(BaseModel):
    """Commodity search API used by the native search engine (NOT SearXNG)."""

    base_url: str | None = None
    api_key: str | None = None
    query_param: str = "q"
    results_key: str = "results"


class BrandingConfig(BaseModel):
    """Per-client white-labeling: what the deployed UI shows."""

    product_name: str = "Zeropark"
    logo_url: str | None = None
    primary_color: str = "#4F46E5"
    client_name: str | None = None  # e.g. "Samsung", "LG"
    layout: dict = Field(default_factory=lambda: {
        "type": "default",
        "widgets": [
            {"id": "chat", "position": "main"}
        ]
    })


class ControlPlaneConfig(BaseModel):
    """Where this deployment reports to (fleet management). Optional."""

    url: str | None = None
    license_key: str | None = None
    deployment_id: str | None = None
    heartbeat_interval_s: int = 60


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
    branding: BrandingConfig = Field(default_factory=BrandingConfig)
    control_plane: ControlPlaneConfig = Field(default_factory=ControlPlaneConfig)
    # capability value -> enabled? Anything not listed defaults to enabled.
    # e.g. ZEROPARK_FEATURES='{"browse": false, "super_agent": true}'
    features: dict[str, bool] = Field(default_factory=dict)
    # capability value -> ordered preferred engine ids
    capability_preferences: dict[str, list[str]] = Field(default_factory=dict)

    def feature_enabled(self, capability_value: str) -> bool:
        return self.features.get(capability_value, True)

    def llm_kwargs(self) -> dict[str, object] | None:
        """Engine kwargs for LLM-backed engines, or None if unconfigured."""
        if not self.llm.api_key:
            return None
        return {
            "provider": self.llm.provider,
            "model": self.llm.model,
            "api_key": self.llm.api_key,
            "base_url": self.llm.base_url,
        }

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
