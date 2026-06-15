"""Chat engine: system history entries + permission-clipped RAG grounding."""

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatResponse
from zeropark_core.models import TaskRequest
from zeropark_engines.chat import LLMChatEngine


class CapturingLLM(BaseLLMClient):
    def __init__(self):
        self.last_messages = None

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        self.last_messages = messages
        return ChatResponse(content="grounded answer")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


class FakeStore:
    def __init__(self):
        self.last_allowed = None

    def similarity_search(self, query, allowed_collection_ids=None, k=3):
        self.last_allowed = allowed_collection_ids
        return [({"text": "보증 기간은 2년입니다.", "collection_id": "kb"}, 0.9)]


@pytest.mark.asyncio
async def test_chat_grounds_in_allowed_collections():
    llm = CapturingLLM()
    store = FakeStore()
    engine = LLMChatEngine(llm_client=llm, model="m", vector_store=store)

    task = TaskRequest(
        prompt="보증 기간 알려줘",
        capability=Capability.CHAT,
        params={"allowed_collection_ids": ["kb"]},
    )
    result = await engine.cap_chat(task, "t1")

    assert store.last_allowed == ["kb"]                      # permission filter forwarded
    assert result.metrics["retrieved_docs"] == 1
    assert result.sources and "보증 기간" in result.sources[0].snippet
    assert any("보증 기간은 2년" in m.content for m in llm.last_messages if m.role == "system")


@pytest.mark.asyncio
async def test_chat_without_allowed_list_skips_retrieval():
    llm = CapturingLLM()
    store = FakeStore()
    engine = LLMChatEngine(llm_client=llm, model="m", vector_store=store)

    task = TaskRequest(prompt="hi", capability=Capability.CHAT, params={})
    result = await engine.cap_chat(task, "t2")
    assert store.last_allowed is None
    assert result.metrics["retrieved_docs"] == 0


@pytest.mark.asyncio
async def test_system_history_entries_become_system_messages():
    llm = CapturingLLM()
    engine = LLMChatEngine(llm_client=llm, model="m")
    task = TaskRequest(
        prompt="이어서",
        capability=Capability.CHAT,
        params={"history": [
            {"role": "system", "content": "Summary: user likes 42"},
            {"role": "user", "content": "hello"},
        ]},
    )
    await engine.cap_chat(task, "t3")
    system_contents = [m.content for m in llm.last_messages if m.role == "system"]
    assert any("likes 42" in c for c in system_contents)
