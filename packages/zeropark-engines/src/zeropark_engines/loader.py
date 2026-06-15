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
from zeropark_core.store import LocalArtifactStore

from zeropark_engines.crawl import LocalCrawlEngine, LLMCrawlEngine
from zeropark_engines.search import WebSearchEngine
from zeropark_engines.slides import PptxSlidesEngine, LLMSlidesEngine
from zeropark_engines.sheets import OpenpyxlSheetsEngine, LLMSheetsEngine
from zeropark_engines.research import ResearchEngine
from zeropark_engines.deep_research import DeepResearchEngine
from zeropark_engines.browse import PlaywrightBrowseEngine
from zeropark_engines.browser_agent import BrowserAgentEngine
from zeropark_engines.chat import LLMChatEngine
from zeropark_engines.media import ImageEngine, PageEngine, PodcastEngine
from zeropark_engines.super_agent import SuperAgentEngine
from zeropark_engines.rag import RAGEngine
from zeropark_core.llm import create_llm_client


def build_registry(
    *,
    output_dir: str = "artifacts",
    search: dict[str, Any] | None = None,
    llm: dict[str, Any] | None = None,
    features: dict[str, bool] | None = None,
) -> ProviderRegistry:
    """`features` is the deployment profile's capability switchboard: a
    capability value mapped to False is not registered at all for this client.
    Anything unlisted defaults to enabled."""
    features = features or {}

    def enabled(capability_value: str) -> bool:
        return features.get(capability_value, True)

    registry = ProviderRegistry()
    store = LocalArtifactStore(base_dir=output_dir)

    # Always available — pure-Python, no external service.
    crawl_engine = LocalCrawlEngine()
    if enabled("crawl"):
        registry.register(crawl_engine)

    pptx_renderer = PptxSlidesEngine(store=store)
    if enabled("slides"):
        registry.register(pptx_renderer)

    xlsx_renderer = OpenpyxlSheetsEngine(store=store)
    if enabled("sheets"):
        registry.register(xlsx_renderer)

    # Playwright availability check. The plain capture engine is registered at
    # the END so that, when an LLM is configured, BrowserAgentEngine becomes the
    # default for `browse` (it handles prompt-only tasks; the capture engine
    # requires a URL).
    playwright_available = False
    browse_engine = None
    if enabled("browse"):
        try:
            import playwright  # noqa: F401
            playwright_available = True
            browse_engine = PlaywrightBrowseEngine(store=store)
        except ImportError:
            pass

    # Optional — only when a commodity search backend is configured.
    search_engine = None
    if search and search.get("base_url") and enabled("search"):
        search_engine = WebSearchEngine(**search)
        registry.register(search_engine)

    # LLM-backed engines — registered whenever an LLM is configured.
    if llm and llm.get("api_key"):
        llm_client = create_llm_client(
            llm.get("provider"), llm["api_key"], llm.get("base_url")
        )

        # Research needs a search backend in addition to the LLM. DeepResearch
        # (planner→researcher→reporter) registers first, so it is the default;
        # the single-shot ResearchEngine stays available via provider_id.
        if search_engine is not None and enabled("research"):
            registry.register(
                DeepResearchEngine(
                    llm_client=llm_client,
                    search_engine=search_engine,
                    crawl_engine=crawl_engine,
                    model=llm.get("model") or "gpt-4o",
                )
            )
            registry.register(
                ResearchEngine(
                    llm_client=llm_client,
                    search_engine=search_engine,
                    crawl_engine=crawl_engine,
                )
            )

        if enabled("crawl"):
            registry.register(LLMCrawlEngine(
                llm_client=llm_client,
                browse_engine=browse_engine,
                model_name=llm.get("model") or "gpt-4o-mini",
            ))

        # RAG first: chat shares its vector store for knowledge-grounded replies
        rag_engine = None
        if enabled("rag"):
            try:
                rag_engine = RAGEngine(store=store, llm_client=llm_client)
                registry.register(rag_engine)
            except Exception as exc:
                # e.g. Qdrant client unavailable — one engine must never take
                # down the whole deployment's registry.
                print(f"Warning: RAG engine not registered: {exc}")

        if enabled("chat"):
            registry.register(
                LLMChatEngine(
                    llm_client=llm_client,
                    model=llm.get("model") or "gpt-4o-mini",
                    vector_store=rag_engine.vector_store if rag_engine else None,
                )
            )
        if enabled("slides"):
            registry.register(LLMSlidesEngine(llm_client=llm_client, renderer=pptx_renderer))
        if enabled("sheets"):
            registry.register(LLMSheetsEngine(llm_client=llm_client, renderer=xlsx_renderer))
        if enabled("super_agent"):
            registry.register(
                SuperAgentEngine(
                    store=store,
                    llm_client=llm_client,
                    search_engine=search_engine,
                    crawl_engine=crawl_engine,
                    model=llm.get("model"),
                )
            )
        # media engines: PAGE works with any provider; IMAGE/AUDIO need the
        # OpenAI SDK (engine checks at call time and fails the task cleanly)
        if enabled("page"):
            registry.register(
                PageEngine(store=store, llm_client=llm_client, model=llm.get("model") or "gpt-4o-mini")
            )
        if enabled("image") and getattr(llm_client, "client", None) is not None:
            registry.register(ImageEngine(store=store, llm_client=llm_client))
        if enabled("audio") and getattr(llm_client, "client", None) is not None:
            registry.register(
                PodcastEngine(store=store, llm_client=llm_client, model=llm.get("model") or "gpt-4o-mini")
            )
        if enabled("browse") and playwright_available:
            registry.register(
                BrowserAgentEngine(
                    store=store,
                    llm_client=llm_client,
                    model=llm.get("model") or "gpt-4o",
                )
            )

    # Plain page-capture browse engine: registered last so the agent (above)
    # wins default selection when present; still pinnable via provider_id.
    if browse_engine is not None:
        registry.register(browse_engine)

    return registry
