"""CHAT — lightweight conversational engine.

The default surface for "just talk to the model": no tools, no planning loop,
so latency and cost stay minimal. History is passed in `params.history`
([{role, content}, ...]) and bounded by the LLM layer's context compression.
Streaming yields token events so the UI can render text as it generates.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import Artifact, RunEvent, TaskRequest, TaskResult, TaskStatus
from zeropark_engines.base import NativeEngine

DEFAULT_SYSTEM_PROMPT = (
    "You are Zeropark's assistant: helpful, concise, and direct. "
    "Answer in the same language the user writes in."
)


class LLMChatEngine(NativeEngine):
    id = "llm-chat"
    name = "LLM Chat Engine"
    capabilities = frozenset({Capability.CHAT})
    reference = "Native conversational engine"

    def __init__(self, llm_client: BaseLLMClient, *, model: str = "gpt-4o-mini") -> None:
        self.llm_client = llm_client
        self.model = model

    def _build_messages(self, task: TaskRequest) -> list[ChatMessage]:
        system = task.params.get("system") or DEFAULT_SYSTEM_PROMPT
        messages = [ChatMessage(role="system", content=system)]
        for turn in task.params.get("history", []) or []:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=task.prompt))
        return messages

    async def cap_chat(self, task: TaskRequest, task_id: str) -> TaskResult:
        model = task.params.get("model") or self.model
        start = time.time()
        response = await self.llm_client.achat_completion(
            self._build_messages(task), model=model
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
            metrics={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "latency_ms": round((time.time() - start) * 1000, 2),
                "model": model,
            },
        )

    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Token-level streaming for live typing in the chat UI."""
        yield RunEvent(
            type="status", task_id=task_id, provider_id=self.id, message="started",
            data={"capability": task.capability.value},
        )
        model = task.params.get("model") or self.model
        parts: list[str] = []
        try:
            async for delta in self.llm_client.achat_completion_stream(
                self._build_messages(task), model=model
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
