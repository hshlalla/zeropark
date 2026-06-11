from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_engines.base import NativeEngine


import os
from typing import Any, Dict, List, Tuple
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore, TaskStatus
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_engines.base import NativeEngine
from zeropark_engines.chunking import RecursiveCharacterTextSplitter

class QdrantVectorStore:
    """Qdrant-based vector store with RBAC support."""
    
    def __init__(self, llm: BaseLLMClient, collection_name: str = "zeropark_rag"):
        self.llm = llm
        self.collection_name = collection_name
        # Default to embedded in-memory mode: no external service, matches the
        # single self-contained artifact principle (ideal for tests / base install).
        # Set QDRANT_URL (e.g. http://localhost:6333) to use a real Qdrant server at scale.
        import os
        qdrant_url = os.getenv("QDRANT_URL")
        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url)
        else:
            self.client = QdrantClient(location=":memory:")
        
        # Vector dimension is detected lazily on first use: probing it here
        # would make a live embeddings API call at STARTUP, so a bad/missing
        # key would crash engine registration instead of failing one request.
        self.dim: int | None = None

    def _ensure_collection(self, dim: int) -> None:
        if self.dim is not None:
            return
        self.dim = dim
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]] = None):
        if not texts:
            return

        embeddings = self.llm.create_embeddings(texts)
        self._ensure_collection(len(embeddings[0]))
        if metadatas is None:
            metadatas = [{"collection_id": "default"} for _ in texts]
            
        points = []
        import uuid
        for text, emb, meta in zip(texts, embeddings, metadatas):
            payload = {"text": text}
            payload.update(meta)
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload=payload
            ))
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
            
    def similarity_search(
        self,
        query: str,
        allowed_collection_ids: List[str] | None = None,
        k: int = 3,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Search restricted to the logical collections the caller may read.

        `allowed_collection_ids=None` means no restriction (internal/admin use);
        an empty list means the caller can read nothing and gets no results.
        """
        if allowed_collection_ids is not None and len(allowed_collection_ids) == 0:
            return []

        query_emb = self.llm.create_embeddings([query])[0]
        self._ensure_collection(len(query_emb))

        query_filter = None
        if allowed_collection_ids is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="collection_id",
                        match=MatchAny(any=allowed_collection_ids),
                    )
                ]
            )

        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_emb,
            query_filter=query_filter,
            limit=k
        )
        
        return [(hit.payload, hit.score) for hit in search_result.points]

class RAGEngine(NativeEngine):
    """Retrieval-Augmented Generation Engine with Advanced Vector Search."""
    
    id = "zeropark_engines.rag"
    name = "RAG Engine"
    capabilities = {Capability.RAG}

    def __init__(self, store: ArtifactStore, llm_client: BaseLLMClient) -> None:
        self.store = store
        self.llm = llm_client
        self.vector_store = QdrantVectorStore(self.llm)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        
    async def execute(self, request: TaskRequest, task_id: str) -> TaskResult:
        query = request.prompt
        context_texts = request.params.get("context_texts", [])

        # Collection-based access control (set by the gateway, not the client):
        #   collection_id            — where uploads are stored
        #   allowed_collection_ids   — which collections this caller may read
        collection_id = request.params.get("collection_id", "default")
        allowed_ids = request.params.get("allowed_collection_ids")  # None = unrestricted

        # 1. If context_texts are provided, chunk them and add them to vector store
        if context_texts:
            all_chunks = []
            all_metas = []
            for text in context_texts:
                chunks = self.splitter.split_text(text)
                all_chunks.extend(chunks)
                all_metas.extend([{"collection_id": collection_id} for _ in chunks])

            self.vector_store.add_texts(all_chunks, metadatas=all_metas)

        # 2. Retrieve relevant chunks, restricted to readable collections
        top_docs = self.vector_store.similarity_search(query, allowed_collection_ids=allowed_ids, k=3)

        # 3. Build context for LLM
        context_str = "\n\n".join([f"Source (Collection: {doc.get('collection_id','?')}, Score: {score:.2f}):\n{doc['text']}" for doc, score in top_docs])
        
        system_prompt = f"""You are a helpful assistant. Answer the user's question based ONLY on the following context.
If you cannot answer the question from the context, say "I cannot answer this based on the provided context."

Context:
{context_str}
"""
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=query)
        ]
        
        response = self.llm.chat_completion(messages, model="gpt-4o")
        answer = response.content or ""
        
        # 4. Save result
        artifact = Artifact(
            id=self.new_id("rag_answer"),
            kind="message",
            title="RAG Answer",
            inline=answer,
            metadata={"retrieved_docs": len(top_docs), "collection_filter": allowed_ids}
        )
        
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.RAG,
            provider_id=self.id,
            artifacts=[artifact],
            metrics={
                "prompt_tokens": getattr(response, "prompt_tokens", 0),
                "completion_tokens": getattr(response, "completion_tokens", 0)
            }
        )
