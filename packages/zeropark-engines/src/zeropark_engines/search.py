"""SEARCH — native thin client to a commodity search API (pluggable).

IMPORTANT: SearXNG is AGPL-3.0, so we do NOT run or copy it. Instead, search is a
small native client to whatever commodity search API the deployment configures
(Brave, Bing, SerpAPI, or a self-hosted permissive endpoint). It is registered
ONLY when a backend is configured, so the framework has no hard search dependency.
"""

from __future__ import annotations

import httpx
from zeropark_core.capabilities import Capability
from zeropark_core.models import Artifact, SourceRef, TaskRequest, TaskResult, TaskStatus

from zeropark_engines.base import NativeEngine


class WebSearchEngine(NativeEngine):
    id = "web-search"
    name = "Web Search (commodity API client)"
    capabilities = frozenset({Capability.SEARCH})
    reference = "SearXNG (AGPL-3.0) - NOT used; independent commodity-API client"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 20.0,
        query_param: str = "q",
        results_key: str = "results",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.query_param = query_param
        self.results_key = results_key

    async def cap_search(self, task: TaskRequest, task_id: str) -> TaskResult:
        limit = int(task.params.get("limit", 10))
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                self.base_url, params={self.query_param: task.prompt}, headers=headers
            )
            response.raise_for_status()
            data = response.json()

        rows = data.get(self.results_key, []) if isinstance(data, dict) else []
        sources = [
            SourceRef(
                url=r.get("url") or r.get("link"),
                title=r.get("title"),
                snippet=r.get("snippet") or r.get("content") or r.get("description"),
                provider_id=self.id,
            )
            for r in rows[:limit]
        ]
        artifact = Artifact(
            id=self.new_id("search"),
            kind="data",
            title=f"Search: {task.prompt}",
            mime_type="application/json",
            inline={"query": task.prompt, "count": len(sources)},
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.SEARCH,
            provider_id=self.id,
            sources=sources,
            artifacts=[artifact],
            metrics={"source_count": len(sources)},
        )
