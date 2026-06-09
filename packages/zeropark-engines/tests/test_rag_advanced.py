import pytest
import os
from unittest.mock import AsyncMock, MagicMock
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
            # dummy vector
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
async def test_rag_engine_rbac_isolation(tmp_path):
    store = LocalArtifactStore(base_dir=str(tmp_path))
    llm = MockLLMClientForRAG()
    
    # Init Engine (which initializes Qdrant in-memory)
    engine = RAGEngine(store=store, llm_client=llm)
    
    # Clear collection for clean test
    engine.vector_store.client.delete_collection(engine.vector_store.collection_name)
    engine.vector_store.client.create_collection(
        collection_name=engine.vector_store.collection_name,
        vectors_config=__import__("qdrant_client").models.VectorParams(size=llm.dim, distance=__import__("qdrant_client").models.Distance.COSINE)
    )
    
    # 1. Admin uploads highly confidential text
    admin_req = TaskRequest(
        prompt="Not used",
        capability=Capability.RAG,
        params={
            "context_texts": ["The secret code is 42."],
            "user_role": "admin"
        }
    )
    # RAG engine currently triggers add_texts if context_texts is provided, then answers the prompt.
    await engine.execute(admin_req, "admin-upload-1")
    
    # 2. Normal User uploads public text
    user_req = TaskRequest(
        prompt="Not used",
        capability=Capability.RAG,
        params={
            "context_texts": ["Zeropark is awesome."],
            "user_role": "user"
        }
    )
    await engine.execute(user_req, "user-upload-1")
    
    # 3. Normal User tries to query the secret code
    user_query = TaskRequest(
        prompt="What is the secret code?",
        capability=Capability.RAG,
        params={
            "user_role": "user"
        }
    )
    user_res = await engine.execute(user_query, "user-query-1")
    
    # Get top docs from the underlying search to assert
    user_search_result = engine.vector_store.similarity_search("secret code", user_role="user")
    
    # The normal user should NOT be able to retrieve the admin document
    # So all retrieved docs should have role == 'user'
    for payload, score in user_search_result:
        assert payload.get("role") == "user", f"User retrieved an unauthorized document! Payload: {payload}"
        
    # 4. Admin tries to query the secret code
    admin_query = TaskRequest(
        prompt="What is the secret code?",
        capability=Capability.RAG,
        params={
            "user_role": "admin"
        }
    )
    
    admin_search_result = engine.vector_store.similarity_search("secret code", user_role="admin")
    
    # Admin should see both docs, including the secret one
    roles_retrieved = set(payload.get("role") for payload, _ in admin_search_result)
    assert "admin" in roles_retrieved, "Admin could not retrieve the admin document!"
