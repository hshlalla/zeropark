"""Zeropark engines: native, in-process implementations of capabilities.

OSS projects are design references only (see each engine's `reference`). Nothing
here imports or calls an external engine, so the framework ships as one artifact.
"""

from zeropark_engines.base import NativeEngine
from zeropark_engines.crawl import LocalCrawlEngine, html_to_markdown
from zeropark_engines.loader import build_registry
from zeropark_engines.search import WebSearchEngine
from zeropark_engines.slides import PptxSlidesEngine

__all__ = [
    "NativeEngine",
    "LocalCrawlEngine",
    "html_to_markdown",
    "PptxSlidesEngine",
    "WebSearchEngine",
    "build_registry",
]
