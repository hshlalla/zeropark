"""Multi-provider LLM layer.

Sync + async chat completion, token streaming, native tool calling, and
embeddings behind one abstract interface. Providers: OpenAI(-compatible) and
Anthropic. Engines depend only on `BaseLLMClient`, so swapping or routing
models never touches engine code.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool invocation requested by the model (provider-normalized)."""

    id: str
    name: str
    arguments: str  # raw JSON string as produced by the model


class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    # assistant messages that requested tool calls
    tool_calls: List[ToolCall] = Field(default_factory=list)
    # tool result messages
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    tool_calls: List[ToolCall] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


def compress_messages(
    messages: List[ChatMessage], *, max_history: int = 20, digest_chars: int = 300
) -> List[ChatMessage]:
    """Bound conversation length without losing early context entirely.

    Keeps system messages and the most recent `max_history` turns; older turns
    are folded into a single compact digest message instead of being dropped,
    so long agent loops keep a trace of early observations.
    """
    system_msgs = [m for m in messages if m.role == "system"]
    rest = [m for m in messages if m.role != "system"]
    if len(rest) <= max_history:
        return system_msgs + rest

    dropped, recent = rest[:-max_history], rest[-max_history:]
    lines = []
    for m in dropped:
        text = (m.content or "").strip().replace("\n", " ")
        if text:
            lines.append(f"[{m.role}] {text[:digest_chars]}")
    digest = ChatMessage(
        role="user",
        content=(
            "Summary of earlier conversation (auto-compressed):\n" + "\n".join(lines)
        ),
    )
    return system_msgs + [digest] + recent


class BaseLLMClient(abc.ABC):
    """Abstract interface for multi-provider LLM calls."""

    @abc.abstractmethod
    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        pass

    async def achat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        """Async variant; default wraps the sync call in a thread executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chat_completion(
                messages, model, temperature, max_tokens, tools=tools, **kwargs
            ),
        )

    async def achat_completion_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Default: one chunk from the non-streaming call."""
        response = await self.achat_completion(
            messages, model, temperature, max_tokens, **kwargs
        )
        if response.content:
            yield response.content

    @abc.abstractmethod
    def create_embeddings(
        self, texts: List[str], model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        pass


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-compatible LLM client wrapping the official openai python package."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        if not api_key or api_key in ("dummy_key", "changeme"):
            raise ValueError(
                "OpenAILLMClient requires a real API key. "
                "Set ZEROPARK_LLM__API_KEY (or OPENAI_API_KEY) before enabling LLM engines."
            )
        import openai

        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.async_client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _to_oai_messages(messages: List[ChatMessage]) -> List[dict]:
        out: List[dict] = []
        for m in compress_messages(messages):
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.role == "assistant" and m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in m.tool_calls
                ]
            if m.role == "tool":
                entry["tool_call_id"] = m.tool_call_id
            out.append(entry)
        return out

    @staticmethod
    def _from_oai_response(response: Any) -> ChatResponse:
        choice = response.choices[0].message
        usage = response.usage
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (choice.tool_calls or [])
        ]
        return ChatResponse(
            content=choice.content or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=response.model,
        )

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """Reasoning-family models (gpt-5*, o1*, o3*, o4*) reject custom
        temperature and require max_completion_tokens instead of max_tokens."""
        name = model.lower()
        return name.startswith(("gpt-5", "o1", "o3", "o4"))

    def _create_kwargs(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        tools: Optional[List[Dict[str, Any]]],
        **kwargs,
    ) -> dict:
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._to_oai_messages(messages),
            **kwargs,
        }
        if self._is_reasoning_model(model):
            # only the default temperature (1) is supported — omit it
            if max_tokens is not None:
                create_kwargs["max_completion_tokens"] = max_tokens
        else:
            create_kwargs["temperature"] = temperature
            if max_tokens is not None:
                create_kwargs["max_tokens"] = max_tokens
        if tools:
            create_kwargs["tools"] = tools
        return create_kwargs

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        response = self.client.chat.completions.create(
            **self._create_kwargs(messages, model, temperature, max_tokens, tools, **kwargs)
        )
        return self._from_oai_response(response)

    async def achat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        response = await self.async_client.chat.completions.create(
            **self._create_kwargs(messages, model, temperature, max_tokens, tools, **kwargs)
        )
        return self._from_oai_response(response)

    async def achat_completion_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        stream = await self.async_client.chat.completions.create(
            stream=True,
            **self._create_kwargs(messages, model, temperature, max_tokens, None, **kwargs),
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def create_embeddings(
        self, texts: List[str], model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        response = self.client.embeddings.create(input=texts, model=model)
        return [data.embedding for data in response.data]


class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Claude client (Messages API), normalized to the same interface."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        if not api_key:
            raise ValueError("AnthropicLLMClient requires a real API key.")
        import anthropic

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.async_client = anthropic.AsyncAnthropic(**kwargs)

    @staticmethod
    def _split_messages(messages: List[ChatMessage]) -> tuple[str, List[dict]]:
        system = "\n".join(m.content for m in messages if m.role == "system")
        converted: List[dict] = []
        for m in compress_messages(messages):
            if m.role == "system":
                continue
            if m.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.role == "assistant" and m.tool_calls:
                import json as _json

                blocks: List[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    try:
                        args = _json.loads(tc.arguments) if tc.arguments else {}
                    except Exception:
                        args = {}
                    blocks.append(
                        {"type": "tool_use", "id": tc.id, "name": tc.name, "input": args}
                    )
                converted.append({"role": "assistant", "content": blocks})
            else:
                converted.append({"role": m.role, "content": m.content})
        return system, converted

    @staticmethod
    def _to_anthropic_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[dict]]:
        """Convert OpenAI-style function tool specs to Anthropic tool specs."""
        if not tools:
            return None
        converted = []
        for t in tools:
            fn = t.get("function", t)
            converted.append(
                {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        return converted

    @staticmethod
    def _from_anthropic_response(response: Any) -> ChatResponse:
        import json as _json

        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=_json.dumps(block.input))
                )
        usage = response.usage
        return ChatResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            prompt_tokens=getattr(usage, "input_tokens", 0),
            completion_tokens=getattr(usage, "output_tokens", 0),
            total_tokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
            model=response.model,
        )

    def _create_kwargs(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        tools: Optional[List[Dict[str, Any]]],
        **kwargs,
    ) -> dict:
        system, converted = self._split_messages(messages)
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            **kwargs,
        }
        if system:
            create_kwargs["system"] = system
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            create_kwargs["tools"] = anthropic_tools
        return create_kwargs

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        response = self.client.messages.create(
            **self._create_kwargs(messages, model, temperature, max_tokens, tools, **kwargs)
        )
        return self._from_anthropic_response(response)

    async def achat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ChatResponse:
        response = await self.async_client.messages.create(
            **self._create_kwargs(messages, model, temperature, max_tokens, tools, **kwargs)
        )
        return self._from_anthropic_response(response)

    async def achat_completion_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        async with self.async_client.messages.stream(
            **self._create_kwargs(messages, model, temperature, max_tokens, None, **kwargs)
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def create_embeddings(
        self, texts: List[str], model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API; configure an "
            "OpenAI-compatible embeddings provider for RAG."
        )


def create_llm_client(
    provider: str | None,
    api_key: str,
    base_url: Optional[str] = None,
) -> BaseLLMClient:
    """Factory used by config-driven wiring. Fails fast on a missing key."""
    if not api_key:
        raise ValueError("LLM api_key is not configured (ZEROPARK_LLM__API_KEY).")
    name = (provider or "openai").lower()
    if name in ("anthropic", "claude"):
        return AnthropicLLMClient(api_key=api_key, base_url=base_url)
    return OpenAILLMClient(api_key=api_key, base_url=base_url)
