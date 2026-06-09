from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_engines.base import NativeEngine


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


class LocalVectorStore:
    """In-memory vector store for RAG."""
    
    def __init__(self, llm: BaseLLMClient):
        self.llm = llm
        self.documents: List[Dict[str, Any]] = []
    
    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]] = None):
        if not texts:
            return
        
        embeddings = self.llm.create_embeddings(texts)
        if metadatas is None:
            metadatas = [{} for _ in texts]
            
        for text, emb, meta in zip(texts, embeddings, metadatas):
            self.documents.append({
                "text": text,
                "embedding": emb,
                "metadata": meta
            })
            
    def similarity_search(self, query: str, k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
        if not self.documents:
            return []
            
        query_emb = self.llm.create_embeddings([query])[0]
        
        results = []
        for doc in self.documents:
            score = cosine_similarity(query_emb, doc["embedding"])
            results.append((doc, score))
            
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]


class RAGEngine(NativeEngine):
    """Retrieval-Augmented Generation Engine."""
    
    id = "zeropark_engines.rag"
    name = "RAG Engine"
    capabilities = {Capability.RAG}

    def __init__(self, store: ArtifactStore, llm_client: BaseLLMClient) -> None:
        self.store = store
        self.llm = llm_client
        self.vector_store = LocalVectorStore(self.llm)
        
    async def execute(self, request: TaskRequest, task_id: str) -> TaskResult:
        query = request.prompt
        context_texts = request.params.get("context_texts", [])
        
        # 1. If context_texts are provided, add them to vector store
        if context_texts:
            self.vector_store.add_texts(context_texts)
            
        # 2. Retrieve relevant chunks
        top_docs = self.vector_store.similarity_search(query, k=3)
        
        # 3. Build context for LLM
        context_str = "\n\n".join([f"Source ({score:.2f}): {doc['text']}" for doc, score in top_docs])
        
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
            id=f"{task_id}_rag_answer",
            kind="message",
            title="RAG Answer",
            inline=answer,
            metadata={"retrieved_docs": len(top_docs)}
        )
        
        return TaskResult(
            task_id=task_id,
            status="completed",
            capability=Capability.RAG,
            provider_id=self.id,
            artifacts=[artifact],
            metrics={
                "prompt_tokens": getattr(response, "prompt_tokens", 0),
                "completion_tokens": getattr(response, "completion_tokens", 0)
            }
        )
