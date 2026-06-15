"""CHAT — lightweight conversational engine, optionally knowledge-grounded.

The default surface for "just talk to the model": no tools, no planning loop,
so latency and cost stay minimal. History is passed in `params.history`
([{role, content}, ...]); `role: system` entries (rolling summary, conversation
variables) become extra system messages. When a vector store is injected and
the task carries `allowed_collection_ids`, each turn retrieves relevant chunks
and grounds the answer in them (chat+RAG hybrid), emitting `source` events.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import Artifact, RunEvent, SourceRef, TaskRequest, TaskResult, TaskStatus
from zeropark_engines.base import NativeEngine

DEFAULT_SYSTEM_PROMPT = (
    "You are Zeropark's assistant: helpful, concise, and direct. "
    "Answer in the same language the user writes in."
)

RAG_CONTEXT_PROMPT = (
    "Relevant knowledge base excerpts for the user's question are below. "
    "Prefer them over your own knowledge when they apply; if they don't cover "
    "the question, say so instead of inventing facts.\n\n{context}"
)


class LLMChatEngine(NativeEngine):
    id = "llm-chat"
    name = "LLM Chat Engine"
    capabilities = frozenset({Capability.CHAT})
    reference = "Native conversational engine (chat + optional RAG grounding)"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        *,
        model: str = "gpt-4o-mini",
        vector_store: Any | None = None,
        retrieval_k: int = 3,
    ) -> None:
        self.llm_client = llm_client
        self.model = model
        self.vector_store = vector_store  # shared with the RAG engine
        self.retrieval_k = retrieval_k

    def _retrieve(self, task: TaskRequest) -> list[dict[str, Any]]:
        """Knowledge grounding: only when a store is wired AND the gateway
        attached an allowed-collections list (permission-clipped server-side)."""
        allowed = task.params.get("allowed_collection_ids")
        if self.vector_store is None or not allowed:
            return []
        try:
            hits = self.vector_store.similarity_search(
                task.prompt, allowed_collection_ids=allowed, k=self.retrieval_k
            )
        except Exception:
            return []  # retrieval hiccups must never kill the conversation
        return [{"text": p.get("text", ""), "collection_id": p.get("collection_id"), "score": s}
                for p, s in hits]

    def _build_messages(self, task: TaskRequest, retrieved: list[dict[str, Any]]) -> list[ChatMessage]:
        system = task.params.get("system") or DEFAULT_SYSTEM_PROMPT
        messages = [ChatMessage(role="system", content=system)]
        for turn in task.params.get("history", []) or []:
            role = turn.get("role")
            content = turn.get("content", "")
            # system entries carry session context (rolling summary, variables)
            if role in ("user", "assistant", "system") and content:
                messages.append(ChatMessage(role=role, content=content))
        if retrieved:
            context = "\n\n".join(
                f"[{i + 1}] (collection: {r['collection_id']})\n{r['text']}"
                for i, r in enumerate(retrieved)
            )
            messages.append(
                ChatMessage(role="system", content=RAG_CONTEXT_PROMPT.format(context=context))
            )
        messages.append(ChatMessage(role="user", content=task.prompt))
        return messages

    async def cap_chat(self, task: TaskRequest, task_id: str) -> TaskResult:
        model = task.params.get("model") or self.model
        start = time.time()
        loop = asyncio.get_event_loop()
        retrieved = await loop.run_in_executor(None, lambda: self._retrieve(task))
        response = await self.llm_client.achat_completion(
            self._build_messages(task, retrieved), model=model,
            temperature=float(task.params.get("temperature", 0.7)),
        )
        artifact = Artifact(
            id=f"{task_id}_reply",
            kind="message",
            title="Chat Reply",
            mime_type="text/markdown",
            inline=response.content,
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.CHAT,
            provider_id=self.id,
            artifacts=[artifact],
            sources=[
                SourceRef(snippet=r["text"][:200], title=f"collection:{r['collection_id']}",
                          score=r["score"], provider_id=self.id)
                for r in retrieved
            ],
            metrics={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "latency_ms": round((time.time() - start) * 1000, 2),
                "model": model,
                "retrieved_docs": len(retrieved),
            },
        )

    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Token-level streaming for live typing in the chat UI."""
        yield RunEvent(
            type="status", task_id=task_id, provider_id=self.id, message="started",
            data={"capability": task.capability.value},
        )
        model = task.params.get("model") or self.model
        loop = asyncio.get_event_loop()
        retrieved = await loop.run_in_executor(None, lambda: self._retrieve(task))
        for i, r in enumerate(retrieved):
            yield RunEvent(
                type="source", task_id=task_id, provider_id=self.id,
                data={"index": i + 1, "collection_id": r["collection_id"],
                      "snippet": r["text"][:200], "score": r["score"]},
            )
        parts: list[str] = []
        try:
            async for delta in self.llm_client.achat_completion_stream(
                self._build_messages(task, retrieved), model=model,
                temperature=float(task.params.get("temperature", 0.7)),
            ):
                parts.append(delta)
                yield RunEvent(
                    type="token", task_id=task_id, provider_id=self.id, message=delta
                )
        except Exception as exc:
            yield RunEvent(type="error", task_id=task_id, provider_id=self.id, message=str(exc))
            return

        full = "".join(parts)
        artifact = Artifact(
            id=f"{task_id}_reply", kind="message", title="Chat Reply",
            mime_type="text/markdown", inline=full,
        )
        result = TaskResult(
            task_id=task_id, status=TaskStatus.SUCCEEDED, capability=Capability.CHAT,
            provider_id=self.id, artifacts=[artifact], metrics={"model": model},
        )
        yield RunEvent(
            type="artifact", task_id=task_id, provider_id=self.id,
            data={"artifact": artifact.model_dump(mode="json")},
        )
        yield RunEvent(
            type="done", task_id=task_id, provider_id=self.id,
            data={"status": "succeeded", "result": result.model_dump(mode="json")},
        )
