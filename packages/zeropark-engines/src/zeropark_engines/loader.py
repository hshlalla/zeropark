"""Build a ProviderRegistry of native engines.

Always-on engines (no external dependency) are registered unconditionally. Engines
that need configuration (search backend, an LLM, a browser) are registered only
when that configuration is present, so a base install runs with zero setup.

Adding a new native engine = implement it + register it here. The core
registry/router/gateway never change.
"""

from __future__ import annotations

from typing import Any

from zeropark_core.registry import ProviderRegistry

from zeropark_engines.crawl import LocalCrawlEngine
from zeropark_engines.search import WebSearchEngine
from zeropark_engines.slides import PptxSlidesEngine


def build_registry(
    *, output_dir: str = "artifacts", search: dict[str, Any] | None = None
) -> ProviderRegistry:
    registry = ProviderRegistry()
    # Always available — pure-Python, no external service.
    registry.register(LocalCrawlEngine())
    registry.register(PptxSlidesEngine(output_dir=output_dir))
    # Optional — only when a commodity search backend is configured.
    if search and search.get("base_url"):
        registry.register(WebSearchEngine(**search))
    return registry
