"""SuperAgentEngine loop tests with a fake LLM (no network)."""

import json

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage, ChatResponse, ToolCall
from zeropark_core.models import TaskRequest, TaskStatus
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.search import WebSearchEngine
from zeropark_engines.super_agent import SuperAgentEngine


class FakeLLM(BaseLLMClient):
    """Mimics the Planner→Researcher→Reporter call sequence:
    1) planner (no tools)  2) researcher requests web_search
    3) researcher writes notes (tool observation must be in history)
    4) reporter writes the final answer."""

    def __init__(self):
        self.calls = 0

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(content="1. Search the web. 2. Summarize.")
        if self.calls == 2:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(id="tc1", name="web_search", arguments=json.dumps({"query": "zeropark"}))
                ],
            )
        if self.calls == 3:
            # the tool observation must be in the message history by now
            assert any(m.role == "tool" for m in messages)
            return ChatResponse(content="Notes: zeropark found at example.com")
        return ChatResponse(content="Final report based on search results.")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


class FakeSearchEngine(WebSearchEngine):
    def __init__(self):
        super().__init__(base_url="http://example.invalid")

    async def cap_search(self, task, task_id):
        from zeropark_core.models import SourceRef, TaskResult

        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.SEARCH,
            provider_id=self.id,
            sources=[SourceRef(url="https://example.com", title="Example", snippet="hit")],
        )


@pytest.mark.asyncio
async def test_agent_uses_real_search_tool_and_streams_events(tmp_path, monkeypatch):
    monkeypatch.delenv("ZEROPARK_ALLOW_UNSAFE_SANDBOX", raising=False)
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = SuperAgentEngine(
        store=store,
        llm_client=FakeLLM(),
        search_engine=FakeSearchEngine(),
        model="test-model",
        max_iterations=5,
    )
    task = TaskRequest(prompt="research zeropark", capability=Capability.SUPER_AGENT)

    result = await engine.cap_super_agent(task, "t1")

    assert result.status == TaskStatus.SUCCEEDED
    assert result.artifacts[0].inline == "Final report based on search results."
    assert result.metrics["iterations"] == 2  # researcher loop: tool call + notes
    assert result.metrics["model"] == "test-model"
    phases = [e.data.get("phase") for e in result.events]
    assert "action" in phases and "observation" in phases


@pytest.mark.asyncio
async def test_agent_native_stream_yields_live_events(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    engine = SuperAgentEngine(
        store=store,
        llm_client=FakeLLM(),
        search_engine=FakeSearchEngine(),
        model="test-model",
        max_iterations=5,
    )
    task = TaskRequest(prompt="research zeropark", capability=Capability.SUPER_AGENT)

    events = [e async for e in engine.stream(task, task_id="t2")]
    types = [e.type for e in events]
    assert types[0] == "status"          # started
    assert "artifact" in types
    assert types[-1] == "done"
