"""DeepResearchEngine pipeline with fake LLM/search/crawl (no network)."""

import json

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatResponse
from zeropark_core.models import SourceRef, TaskRequest, TaskResult, TaskStatus
from zeropark_engines.base import NativeEngine
from zeropark_engines.deep_research import DeepResearchEngine


class FakeLLM(BaseLLMClient):
    """Planner returns a 2-section plan; section/report calls echo markers."""

    def __init__(self):
        self.calls = []

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        system = messages[0].content
        self.calls.append(system[:30])
        if "research planner" in system:
            return ChatResponse(content=json.dumps({
                "title": "Test Report",
                "sections": [
                    {"heading": "Background", "queries": ["q1"]},
                    {"heading": "Outlook", "queries": ["q2"]},
                ],
            }))
        if "ONE section" in system:
            return ChatResponse(content="Section draft with citation [1].")
        return ChatResponse(content="# Test Report\n\nFinal assembled report [1].\n\n## References\n[1] https://example.com/a")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


class FakeSearch(NativeEngine):
    id = "fake-search"
    capabilities = frozenset({Capability.SEARCH})

    async def cap_search(self, task, task_id):
        return TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.SEARCH,
            provider_id=self.id,
            sources=[SourceRef(url=f"https://example.com/{task.prompt}", title=task.prompt)],
        )


class FakeCrawl(NativeEngine):
    id = "fake-crawl"
    capabilities = frozenset({Capability.CRAWL})

    async def cap_crawl(self, task, task_id):
        from zeropark_core.models import Artifact

        return TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.CRAWL,
            provider_id=self.id,
            artifacts=[Artifact(id="a", kind="page", inline=f"content of {task.params['url']}")],
        )


@pytest.mark.asyncio
async def test_pipeline_plans_researches_and_reports():
    engine = DeepResearchEngine(FakeLLM(), FakeSearch(), FakeCrawl(), model="m")
    task = TaskRequest(prompt="research something", capability=Capability.RESEARCH)

    result = await engine.cap_research(task, "t1")

    assert result.status == TaskStatus.SUCCEEDED
    assert result.metrics["sections"] == 2
    assert result.metrics["sources"] == 2  # one unique URL per section query
    assert "Final assembled report" in result.artifacts[0].inline
    phases = [e.data.get("phase") for e in result.events if e.type == "status"]
    assert phases == ["plan", "research", "research", "report"]
    assert sum(1 for e in result.events if e.type == "source") == 2


@pytest.mark.asyncio
async def test_stream_emits_plan_then_done():
    engine = DeepResearchEngine(FakeLLM(), FakeSearch(), FakeCrawl(), model="m")
    task = TaskRequest(prompt="research something", capability=Capability.RESEARCH)

    events = [e async for e in engine.stream(task, task_id="t2")]
    types = [e.type for e in events]
    assert types[0] == "status" and types[-1] == "done"
    assert "artifact" in types
