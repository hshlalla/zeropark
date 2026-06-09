from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_engines.base import NativeEngine


import os
from typing import Any, Dict, List, Tuple
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore, TaskStatus
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_engines.base import NativeEngine
from zeropark_engines.chunking import RecursiveCharacterTextSplitter

class QdrantVectorStore:
    """Qdrant-based vector store with RBAC support."""
    
    def __init__(self, llm: BaseLLMClient, collection_name: str = "zeropark_rag"):
        self.llm = llm
        self.collection_name = collection_name
        # Using in-memory storage for fast development and testing without lock issues
        self.client = QdrantClient(location=":memory:")
        
        # Test vector dimension (e.g. text-embedding-3-small is usually 1536)
        # We fetch a dummy embedding to know the dimension
        dummy_emb = self.llm.create_embeddings(["test"])[0]
        self.dim = len(dummy_emb)
        
        # Init collection if not exists
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
        if metadatas is None:
            metadatas = [{"role": "user"} for _ in texts] # default open to all
            
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
            
    def similarity_search(self, query: str, user_role: str = "user", k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
        query_emb = self.llm.create_embeddings([query])[0]
        
        # RBAC Filtering
        # If user is 'admin', they can see 'admin' and 'user' docs.
        # If user is 'user', they can only see 'user' docs.
        query_filter = None
        if user_role != "admin":
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="role",
                        match=MatchValue(value="user")
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
        
        # User Role Context
        user_role = request.params.get("user_role", "user")
        
        # 1. If context_texts are provided, chunk them and add them to vector store
        if context_texts:
            all_chunks = []
            all_metas = []
            for text in context_texts:
                chunks = self.splitter.split_text(text)
                all_chunks.extend(chunks)
                # Assign the current user role to the document
                all_metas.extend([{"role": user_role} for _ in chunks])
                
            self.vector_store.add_texts(all_chunks, metadatas=all_metas)
            
        # 2. Retrieve relevant chunks (Filter by user_role)
        top_docs = self.vector_store.similarity_search(query, user_role=user_role, k=3)
        
        # 3. Build context for LLM
        context_str = "\n\n".join([f"Source (Role: {doc.get('role','unknown')}, Score: {score:.2f}):\n{doc['text']}" for doc, score in top_docs])
        
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
            metadata={"retrieved_docs": len(top_docs), "role_filter": user_role}
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
