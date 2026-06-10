"""CRAWL — fetch a URL and return clean markdown. Native (httpx + markdownify).

Design reference: Crawl4AI (Apache-2.0). No Crawl4AI code or service is used.
For JavaScript-heavy pages a Playwright-backed variant is the planned upgrade
(the `browser` extra); this engine handles static HTML.
"""

from __future__ import annotations

import re

import asyncio
import json
from urllib.parse import urljoin, urlparse

import httpx
from markdownify import markdownify as html_to_md
from zeropark_core.llm import BaseLLMClient, ChatMessage
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

class LLMCrawlEngine(NativeEngine):
    id = "llm-crawl"
    name = "Advanced Crawl (JS Render, Deep, Structured)"
    capabilities = frozenset({Capability.CRAWL})
    reference = "Crawl4AI (Apache-2.0) - advanced features"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        browse_engine: NativeEngine | None = None,
        model_name: str = "gpt-4o-mini",
        *,
        timeout: float = 30.0,
        user_agent: str = "ZeroparkBot/0.1"
    ) -> None:
        self.llm_client = llm_client
        self.browse_engine = browse_engine
        self.model_name = model_name
        self.timeout = timeout
        self.user_agent = user_agent
        self._local_crawl = LocalCrawlEngine(timeout=timeout, user_agent=user_agent)

    def _extract_links(self, markdown: str, base_url: str) -> list[str]:
        links = []
        for match in re.finditer(r"\[.*?\]\((.*?)\)", markdown):
            url = match.group(1).split(" ")[0]
            if url.startswith("#") or url.startswith("mailto:"):
                continue
            full_url = urljoin(base_url, url)
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                links.append(full_url)
        return list(dict.fromkeys(links))

    async def _fetch_page(self, url: str, use_browser: bool, task_id: str) -> tuple[str, str, Artifact | None]:
        if use_browser and self.browse_engine:
            sub_task = TaskRequest(prompt=url, capability=Capability.BROWSE, params={"url": url, "headless": True})
            result = await self.browse_engine.cap_browse(sub_task, task_id=f"{task_id}_browse")
            if result.status == TaskStatus.SUCCEEDED:
                md_artifact = next((a for a in result.artifacts if a.mime_type == "text/markdown"), None)
                if md_artifact and md_artifact.inline:
                    return "", md_artifact.inline, md_artifact
        
        sub_task = TaskRequest(prompt=url, capability=Capability.CRAWL, params={"url": url})
        result = await self._local_crawl.cap_crawl(sub_task, task_id=f"{task_id}_local")
        if result.status == TaskStatus.SUCCEEDED and result.artifacts:
            art = result.artifacts[0]
            return "", str(art.inline), art
            
        raise ValueError(f"Failed to fetch {url}")

    async def _extract_structured(self, markdown: str, schema: dict) -> dict:
        sys_prompt = ChatMessage(
            role="system",
            content=(
                "You are a structured data extractor. Extract the requested information from the provided markdown "
                "text according to the given JSON schema. Return ONLY a valid JSON object matching the schema."
            )
        )
        user_prompt = ChatMessage(
            role="user",
            content=f"SCHEMA:\n{json.dumps(schema, indent=2)}\n\nMARKDOWN CONTENT:\n{markdown[:15000]}"
        )
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.llm_client.chat_completion([sys_prompt, user_prompt], self.model_name, temperature=0.1)
        )
        text = response.content.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            return json.loads(text)
        except Exception:
            return {"error": "Failed to parse JSON", "raw": text}

    async def cap_crawl(self, task: TaskRequest, task_id: str) -> TaskResult:
        start_url = task.params.get("url") or task.prompt
        use_browser = str(task.params.get("use_browser", "false")).lower() == "true"
        max_depth = int(task.params.get("max_depth", 0))
        schema = task.params.get("extraction_schema")

        visited = set()
        queue = [start_url]
        all_markdown = []
        artifacts = []
        sources = []

        depth = 0
        while queue and depth <= max_depth:
            next_queue = []
            for url in queue:
                if url in visited:
                    continue
                visited.add(url)
                
                try:
                    _, md, art = await self._fetch_page(url, use_browser, f"{task_id}_{len(visited)}")
                    if md and art:
                        all_markdown.append(md)
                        artifacts.append(art)
                        sources.append(SourceRef(url=url, provider_id=self.id))
                        
                        if depth < max_depth:
                            links = self._extract_links(md, url)
                            next_queue.extend([l for l in links if l not in visited])
                except Exception:
                    pass
                    
            queue = list(dict.fromkeys(next_queue))
            depth += 1

        combined_md = "\n\n---\n\n".join(all_markdown)
        
        if schema:
            extracted_data = await self._extract_structured(combined_md, schema)
            artifacts.append(Artifact(
                id=self.new_id("extraction"),
                kind="data",
                title=f"Extracted Data from {start_url}",
                mime_type="application/json",
                inline=json.dumps(extracted_data, indent=2, ensure_ascii=False)
            ))

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED if artifacts else TaskStatus.FAILED,
            capability=Capability.CRAWL,
            provider_id=self.id,
            artifacts=artifacts,
            sources=sources,
            metrics={"pages_crawled": len(visited), "chars": len(combined_md)},
        )
