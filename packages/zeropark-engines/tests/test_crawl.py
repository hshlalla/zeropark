from __future__ import annotations

import asyncio

from zeropark_core.capabilities import Capability
from zeropark_core.models import TaskRequest

from zeropark_engines.crawl import LocalCrawlEngine, html_to_markdown


def test_html_to_markdown_strips_scripts_and_keeps_text() -> None:
    html = "<html><body><h1>Title</h1><script>var x=1;</script><p>Hello <b>world</b></p></body></html>"
    md = html_to_markdown(html)
    assert "# Title" in md
    assert "Hello" in md
    assert "var x=1" not in md


def test_crawl_uses_inline_html_without_network() -> None:
    engine = LocalCrawlEngine()
    task = TaskRequest(
        prompt="https://example.com",
        capability=Capability.CRAWL,
        params={"url": "https://example.com", "html": "<h1>Doc</h1><p>Body text</p>"},
    )
    result = asyncio.run(engine.execute(task, task_id="t1"))
    assert result.status.value == "succeeded"
    assert result.provider_id == "local-crawl"
    assert result.artifacts[0].kind == "page"
    assert "# Doc" in result.artifacts[0].inline
    assert result.sources[0].url == "https://example.com"
