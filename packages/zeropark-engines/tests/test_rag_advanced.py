"""RAG collection-based access isolation.

Documents are stored into logical collections; queries are restricted to the
collection ids the caller may read (computed server-side by the gateway).
"""

import pytest
from unittest.mock import MagicMock
from zeropark_core.models import TaskRequest, Capability
from zeropark_core.store import LocalArtifactStore
from zeropark_engines.rag import RAGEngine


class MockLLMClientForRAG:
    def __init__(self):
        # We need realistic 10-dimensional embeddings for Qdrant local test
        self.dim = 10
        self.call_count = 0

    def create_embeddings(self, texts):
        res = []
        for _ in texts:
            self.call_count += 1
            res.append([float(self.call_count % self.dim) for _ in range(self.dim)])
        return res

    def chat_completion(self, messages, **kwargs):
        mock_response = MagicMock()
        mock_response.content = "This is a dummy RAG response."
        mock_response.prompt_tokens = 10
        mock_response.completion_tokens = 20
        return mock_response


@pytest.mark.asyncio
async def test_rag_collection_isolation(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    llm = MockLLMClientForRAG()
    engine = RAGEngine(store=store, llm_client=llm)

    # 1. Upload a confidential doc into the admin-only collection
    await engine.execute(
        TaskRequest(
            prompt="Not used",
            capability=Capability.RAG,
            params={
                "context_texts": ["The secret code is 42."],
                "collection_id": "hr_confidential",
                "allowed_collection_ids": [],
            },
        ),
        "admin-upload-1",
    )

    # 2. Upload a public doc into the default collection
    await engine.execute(
        TaskRequest(
            prompt="Not used",
            capability=Capability.RAG,
            params={
                "context_texts": ["Zeropark is awesome."],
                "collection_id": "default",
                "allowed_collection_ids": [],
            },
        ),
        "user-upload-1",
    )

    # 3. A caller allowed only ['default'] must never see hr_confidential docs
    user_hits = engine.vector_store.similarity_search(
        "secret code", allowed_collection_ids=["default"], k=5
    )
    assert user_hits, "expected at least the public doc"
    for payload, _ in user_hits:
        assert payload.get("collection_id") == "default", (
            f"User retrieved an unauthorized document! Payload: {payload}"
        )

    # 4. A caller allowed both collections (admin) sees the confidential doc
    admin_hits = engine.vector_store.similarity_search(
        "secret code", allowed_collection_ids=["default", "hr_confidential"], k=5
    )
    collections_retrieved = {p.get("collection_id") for p, _ in admin_hits}
    assert "hr_confidential" in collections_retrieved

    # 5. An empty allowed list means no access at all
    assert engine.vector_store.similarity_search("anything", allowed_collection_ids=[]) == []
