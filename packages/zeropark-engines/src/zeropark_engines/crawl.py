"""CRAWL — fetch a URL and return clean markdown. Native (httpx + markdownify).

Design reference: Crawl4AI (Apache-2.0). No Crawl4AI code or service is used.
For JavaScript-heavy pages a Playwright-backed variant is the planned upgrade
(the `browser` extra); this engine handles static HTML.
"""

from __future__ import annotations

import re

import httpx
from markdownify import markdownify as html_to_md
from zeropark_core.capabilities import Capability
from zeropark_core.models import Artifact, SourceRef, TaskRequest, TaskResult, TaskStatus
from zeropark_core.netguard import validate_public_url

from zeropark_engines.base import NativeEngine

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLANK_LINES = re.compile(r"\n{3,}")


def html_to_markdown(html: str) -> str:
    cleaned = _SCRIPT_STYLE.sub("", html)
    markdown = html_to_md(cleaned, heading_style="ATX", strip=["script", "style"])
    return _BLANK_LINES.sub("\n\n", markdown).strip()


class LocalCrawlEngine(NativeEngine):
    id = "local-crawl"
    name = "Local Crawl (httpx + markdownify)"
    capabilities = frozenset({Capability.CRAWL})
    reference = "Crawl4AI (Apache-2.0) - design reference only"

    def __init__(self, *, timeout: float = 30.0, user_agent: str = "ZeroparkBot/0.1") -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    async def cap_crawl(self, task: TaskRequest, task_id: str) -> TaskResult:
        target = task.params.get("url") or task.prompt
        html = task.params.get("html")  # allows offline use / testing without a fetch
        if html is None:
            validate_public_url(target)
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(target, headers={"User-Agent": self.user_agent})
                response.raise_for_status()
                html = response.text

        markdown = html_to_markdown(html)
        artifact = Artifact(
            id=self.new_id("crawl"),
            kind="page",
            title=task.params.get("title") or target,
            mime_type="text/markdown",
            inline=markdown,
            metadata={"source_url": target, "chars": len(markdown)},
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.CRAWL,
            provider_id=self.id,
            artifacts=[artifact],
            sources=[SourceRef(url=target, provider_id=self.id)],
            metrics={"chars": len(markdown)},
        )
