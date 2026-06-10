"""DEEP RESEARCH — multi-agent pipeline: Planner → Researcher → Reporter.

Design reference: DeerFlow (MIT) — reimplemented natively, no code used.

The single-shot ResearchEngine extracts a few queries and writes one report.
This engine works the way deer-flow does:

  1. PLANNER   — an LLM turns the prompt into a structured plan: report title +
                 sections, each with its own search queries.
  2. RESEARCHER— per section, run searches, pick the best URLs, crawl them, and
                 distill section findings (with per-source citations).
  3. REPORTER  — a final LLM pass writes the full report from section findings,
                 keeping inline [n] citations and a references list.

Progress is emitted as RunEvents so the UI shows the plan, then each section
completing live.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, Callable

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import (
    Artifact,
    RunEvent,
    SourceRef,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from zeropark_engines.base import NativeEngine

PLANNER_PROMPT = """You are a research planner. Break the user's research request into a
structured plan. Return ONLY strict JSON:
{"title": "<report title>",
 "sections": [{"heading": "<section heading>", "queries": ["<search query>", ...]}, ...]}
Use 2-4 sections, each with 1-2 highly targeted search queries. Queries should be in the
language most likely to find authoritative sources."""

SECTION_PROMPT = """You are a research analyst writing ONE section of a larger report.
Section heading: {heading}
Using ONLY the provided sources, write 2-4 dense paragraphs for this section.
Cite sources inline as [{offset}], [{offset_plus}] etc. matching the source numbers given.
If sources are insufficient, say what is missing. Do not write a conclusion."""

REPORTER_PROMPT = """You are an expert report writer. Assemble the final markdown report from
the section drafts below. Keep ALL inline [n] citations exactly as written. Structure:
# <title>
brief executive summary, then each section under '## <heading>', then a '## References'
section listing every numbered source URL. Improve flow but do not invent facts."""


class DeepResearchEngine(NativeEngine):
    id = "deep-research"
    name = "Deep Research (Planner → Researcher → Reporter)"
    capabilities = frozenset({Capability.RESEARCH})
    reference = "DeerFlow (MIT) - design reference only"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        search_engine: NativeEngine,
        crawl_engine: NativeEngine,
        *,
        model: str = "gpt-4o",
        max_sources_per_section: int = 3,
        crawl_char_limit: int = 4000,
    ) -> None:
        self.llm_client = llm_client
        self.search_engine = search_engine
        self.crawl_engine = crawl_engine
        self.model = model
        self.max_sources_per_section = max_sources_per_section
        self.crawl_char_limit = crawl_char_limit

    # ---------------------------------------------------------------- agents

    async def _plan(self, prompt: str) -> dict[str, Any]:
        response = await self.llm_client.achat_completion(
            [
                ChatMessage(role="system", content=PLANNER_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            model=self.model,
            temperature=0.2,
        )
        text = response.content.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            plan = json.loads(text)
            if plan.get("sections"):
                return plan
        except json.JSONDecodeError:
            pass
        # degraded plan: single section straight from the prompt
        return {"title": prompt[:80], "sections": [{"heading": "Findings", "queries": [prompt[:120]]}]}

    async def _search(self, query: str, limit: int) -> list[SourceRef]:
        task = TaskRequest(prompt=query, capability=Capability.SEARCH, params={"limit": limit})
        result = await self.search_engine.cap_search(task, task_id="research_search")
        return result.sources

    async def _crawl(self, url: str) -> str:
        task = TaskRequest(prompt=url, capability=Capability.CRAWL, params={"url": url})
        try:
            result = await self.crawl_engine.cap_crawl(task, task_id="research_crawl")
            content = result.artifacts[0].inline if result.artifacts else ""
            return str(content)[: self.crawl_char_limit]
        except Exception as exc:
            return f"(crawl failed: {exc})"

    async def _research_section(
        self, section: dict[str, Any], source_offset: int
    ) -> tuple[str, list[SourceRef]]:
        """Gather sources for one section and draft it. Returns (draft, sources)."""
        seen: set[str] = set()
        sources: list[SourceRef] = []
        for query in section.get("queries", [])[:2]:
            for ref in await self._search(query, self.max_sources_per_section):
                if ref.url and ref.url not in seen:
                    seen.add(ref.url)
                    sources.append(ref)
        sources = sources[: self.max_sources_per_section]

        # crawl in parallel
        contents = await asyncio.gather(*(self._crawl(s.url) for s in sources))

        context_parts = []
        for i, (ref, content) in enumerate(zip(sources, contents)):
            number = source_offset + i + 1
            context_parts.append(f"--- Source [{number}] {ref.title or ''} ({ref.url}) ---\n{content}")

        prompt = SECTION_PROMPT.format(
            heading=section.get("heading", ""),
            offset=source_offset + 1,
            offset_plus=source_offset + 2,
        )
        response = await self.llm_client.achat_completion(
            [
                ChatMessage(role="system", content=prompt),
                ChatMessage(role="user", content="\n\n".join(context_parts) or "(no sources found)"),
            ],
            model=self.model,
            temperature=0.3,
        )
        return response.content, sources

    async def _report(self, title: str, drafts: list[tuple[str, str]], sources: list[SourceRef]) -> str:
        references = "\n".join(f"[{i + 1}] {s.url}" for i, s in enumerate(sources))
        body = "\n\n".join(f"## {heading}\n{draft}" for heading, draft in drafts)
        response = await self.llm_client.achat_completion(
            [
                ChatMessage(role="system", content=REPORTER_PROMPT),
                ChatMessage(
                    role="user",
                    content=f"Title: {title}\n\nSection drafts:\n{body}\n\nNumbered sources:\n{references}",
                ),
            ],
            model=self.model,
            temperature=0.3,
        )
        return response.content

    # ------------------------------------------------------------------ run

    async def _run(
        self, task: TaskRequest, task_id: str, emit: Callable[[RunEvent], None]
    ) -> TaskResult:
        plan = await self._plan(task.prompt)
        emit(
            RunEvent(
                type="status",
                task_id=task_id,
                provider_id=self.id,
                message="plan",
                data={"phase": "plan", "plan": plan},
            )
        )

        drafts: list[tuple[str, str]] = []
        all_sources: list[SourceRef] = []
        for section in plan["sections"]:
            heading = section.get("heading", "")
            emit(
                RunEvent(
                    type="status",
                    task_id=task_id,
                    provider_id=self.id,
                    message=f"researching: {heading}",
                    data={"phase": "research", "section": heading},
                )
            )
            draft, sources = await self._research_section(section, len(all_sources))
            drafts.append((heading, draft))
            all_sources.extend(sources)
            for ref in sources:
                emit(
                    RunEvent(
                        type="source",
                        task_id=task_id,
                        provider_id=self.id,
                        data={"url": ref.url, "title": ref.title, "section": heading},
                    )
                )

        emit(
            RunEvent(
                type="status",
                task_id=task_id,
                provider_id=self.id,
                message="writing report",
                data={"phase": "report"},
            )
        )
        report = await self._report(plan.get("title", task.prompt[:80]), drafts, all_sources)

        artifact = Artifact(
            id=self.new_id("research"),
            kind="report",
            title=plan.get("title", task.prompt[:80]),
            mime_type="text/markdown",
            inline=report,
            metadata={"sections": len(drafts), "sources": len(all_sources)},
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.RESEARCH,
            provider_id=self.id,
            artifacts=[artifact],
            sources=all_sources,
            metrics={"sections": len(drafts), "sources": len(all_sources), "model": self.model},
        )

    async def cap_research(self, task: TaskRequest, task_id: str) -> TaskResult:
        events: list[RunEvent] = []
        result = await self._run(task, task_id, events.append)
        result.events = events
        return result

    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Live streaming: plan, per-section progress, sources, then done."""
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

        yield RunEvent(
            type="status",
            task_id=task_id,
            provider_id=self.id,
            message="started",
            data={"capability": task.capability.value},
        )

        async def runner() -> TaskResult:
            try:
                return await self._run(task, task_id, queue.put_nowait)
            finally:
                queue.put_nowait(None)

        run_task = asyncio.create_task(runner())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        try:
            result = await run_task
        except Exception as exc:
            yield RunEvent(type="error", task_id=task_id, provider_id=self.id, message=str(exc))
            return

        for artifact in result.artifacts:
            yield RunEvent(
                type="artifact",
                task_id=task_id,
                provider_id=self.id,
                data={"artifact": artifact.model_dump(mode="json")},
            )
        yield RunEvent(
            type="done",
            task_id=task_id,
            provider_id=self.id,
            data={"status": result.status.value, "result": result.model_dump(mode="json")},
        )
