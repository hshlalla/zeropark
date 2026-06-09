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
from zeropark_engines.slides import PptxSlidesEngine, LLMSlidesEngine
from zeropark_engines.sheets import OpenpyxlSheetsEngine, LLMSheetsEngine
from zeropark_engines.research import ResearchEngine
from zeropark_engines.browse import PlaywrightBrowseEngine
from zeropark_engines.super_agent import SuperAgentEngine
from zeropark_core.llm import OpenAILLMClient


def build_registry(
    *, output_dir: str = "artifacts", search: dict[str, Any] | None = None, llm: dict[str, Any] | None = None
) -> ProviderRegistry:
    registry = ProviderRegistry()
    # Always available — pure-Python, no external service.
    registry.register(LocalCrawlEngine())
    
    pptx_renderer = PptxSlidesEngine(output_dir=output_dir)
    registry.register(pptx_renderer)
    
    xlsx_renderer = OpenpyxlSheetsEngine(output_dir=output_dir)
    registry.register(xlsx_renderer)
    
    # Register Playwright Browse Engine if playwright is installed
    try:
        import playwright
        registry.register(PlaywrightBrowseEngine(output_dir=output_dir))
    except ImportError:
        pass
    
    # Optional — only when a commodity search backend is configured.
    if search and search.get("base_url"):
        search_engine = WebSearchEngine(**search)
        registry.register(search_engine)
        
        # Optional - Register Research Engine if search and LLM are configured
        if llm and llm.get("api_key"):
            llm_client = OpenAILLMClient(api_key=llm["api_key"])
            crawl_engine = LocalCrawlEngine()
            registry.register(ResearchEngine(llm_client=llm_client, search_engine=search_engine, crawl_engine=crawl_engine))
            
            # Also register LLMSlidesEngine (overrides or supplements default slides capability)
            registry.register(LLMSlidesEngine(llm_client=llm_client, renderer=pptx_renderer))
            
            # Register LLMSheetsEngine
            registry.register(LLMSheetsEngine(llm_client=llm_client, renderer=xlsx_renderer))
            
            # Register SuperAgentEngine
            registry.register(SuperAgentEngine(output_dir=output_dir))
            
    return registry
