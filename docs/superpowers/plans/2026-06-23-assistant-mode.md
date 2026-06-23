# Assistant 모드 (만능 채팅) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자가 에이전트를 만들 때 도구(image/slides/sheets/research/rag)를 골라 묶을 수 있는 대화형 `assistant` 모드를 추가해, 사용자가 한 대화 안에서 모드 전환 없이 AI가 도구를 호출하게 한다.

**Architecture:** 기존 capability→mode→engine 3계층을 그대로 따른다. 새 `AssistantEngine`은 `LLMChatEngine`처럼 `params.history`를 받는 대화 루프이되, `SuperAgentEngine`의 네이티브 도구 호출 루프를 빌려 다른 엔진들을 도구로 노출한다. 각 도구는 라우터를 감싼 범용 어댑터로, 호출되면 `provider.execute()`로 서브태스크를 디스패치하고 생성 아티팩트를 RunEvent로 스트리밍한다. 도구 목록은 `App.params.tools`에 저장되어 마이그레이션 없이 `task.params["tools"]`까지 흐른다.

**Tech Stack:** Python 3, pytest / pytest-asyncio, SQLAlchemy(기존), React+TypeScript(프론트).

## Global Constraints

- 엔진은 `NativeEngine`을 상속하고 `cap_<capability_value>` 코루틴을 구현한다 (시그니처: `async def cap_x(self, task: TaskRequest, task_id: str) -> TaskResult`).
- OSS 프로젝트는 **설계 참조만** — 코드 임포트/네트워크 호출 금지. `reference` 문자열로 출처 기록.
- 도구 목록은 capability **값 문자열** 리스트로 저장/전달한다: `["image","slides","sheets","research","rag"]`.
- 기존 `chat`/`super_agent`/단일-모드 엔진과 동작은 건드리지 않는다.
- 각 Task는 독립적으로 테스트 가능한 산출물로 끝나고, 끝나면 커밋한다.
- 테스트는 네트워크 없이 가짜 LLM/스텁 엔진으로 돌린다 ([test_super_agent.py](../../../packages/zeropark-engines/tests/test_super_agent.py) 스타일).

---

### Task 1: ASSISTANT capability + assistant 모드 등록

**Files:**
- Modify: `packages/zeropark-core/src/zeropark_core/capabilities.py`
- Modify: `packages/zeropark-core/src/zeropark_core/router.py`
- Test: `packages/zeropark-core/tests/test_router.py` (없으면 생성)

**Interfaces:**
- Produces: `Capability.ASSISTANT` (value `"assistant"`); `Router.plan("assistant")` → `ModePlan(primary=Capability.ASSISTANT, pipeline=(Capability.ASSISTANT,))`.

- [ ] **Step 1: Write the failing test**

`packages/zeropark-core/tests/test_router.py`에 추가 (파일이 없으면 새로 생성하고 아래 임포트 포함):

```python
from zeropark_core.capabilities import Capability
from zeropark_core.registry import ProviderRegistry
from zeropark_core.router import Router


def test_assistant_mode_is_registered():
    router = Router(ProviderRegistry())
    plan = router.plan("assistant")
    assert plan.primary == Capability.ASSISTANT
    assert plan.pipeline == (Capability.ASSISTANT,)


def test_assistant_capability_value():
    assert Capability.ASSISTANT.value == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest packages/zeropark-core/tests/test_router.py -v`
Expected: FAIL — `AttributeError: ASSISTANT` / `KeyError: assistant`.

- [ ] **Step 3: Add the capability**

`capabilities.py`의 `Capability` enum에 `CHAT` 줄 아래로 추가:

```python
    CHAT = "chat"                # conversational question answering
    ASSISTANT = "assistant"      # conversational chat that can call other engines as tools
```

- [ ] **Step 4: Add the mode plan**

`router.py`의 `DEFAULT_MODES` 딕셔너리, `"chat": ModePlan(...)` 항목 바로 위에 추가:

```python
    "assistant": ModePlan(
        "assistant",
        Capability.ASSISTANT,
        (Capability.ASSISTANT,),
        "Conversational assistant that can call tools (image, slides, sheets, research, knowledge).",
    ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest packages/zeropark-core/tests/test_router.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add packages/zeropark-core/src/zeropark_core/capabilities.py packages/zeropark-core/src/zeropark_core/router.py packages/zeropark-core/tests/test_router.py
git commit -m "feat(core): add ASSISTANT capability and assistant mode"
```

---

### Task 2: AssistantEngine — 대화형 코어 (도구 없는 순수 챗 폴백)

**Files:**
- Create: `packages/zeropark-engines/src/zeropark_engines/assistant.py`
- Test: `packages/zeropark-engines/tests/test_assistant.py`

**Interfaces:**
- Consumes: `Capability.ASSISTANT` (Task 1); `ProviderRegistry`, `Router` (core).
- Produces:
  - `AssistantEngine(llm_client, registry, *, model="gpt-4o", temperature=0.7, max_iterations=10)`
  - `async AssistantEngine.cap_assistant(task: TaskRequest, task_id: str) -> TaskResult`
  - 모듈 상수 `TOOL_CAPABILITY: dict[str, Capability]` (tool name → capability), `DEFAULT_SYSTEM_PROMPT`.
  - 결과 아티팩트: `kind="message"`, `mime_type="text/markdown"`, `inline=<최종 답변>`.

- [ ] **Step 1: Write the failing test**

`packages/zeropark-engines/tests/test_assistant.py` 생성:

```python
"""AssistantEngine tests with a fake LLM and stub engines (no network)."""

import json

import pytest

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatResponse, ToolCall
from zeropark_core.models import Artifact, TaskRequest, TaskResult, TaskStatus
from zeropark_core.registry import ProviderRegistry
from zeropark_engines.assistant import AssistantEngine
from zeropark_engines.base import NativeEngine


class PlainLLM(BaseLLMClient):
    """Answers in one shot, no tool calls."""

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        return ChatResponse(content="Hello there.")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_pure_chat_when_no_tools():
    engine = AssistantEngine(PlainLLM(), ProviderRegistry(), model="test-model")
    task = TaskRequest(
        prompt="hi", capability=Capability.ASSISTANT, params={"tools": []}
    )
    result = await engine.cap_assistant(task, "a1")
    assert result.status == TaskStatus.SUCCEEDED
    assert result.artifacts[0].inline == "Hello there."
    assert result.metrics["model"] == "test-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: FAIL — `ModuleNotFoundError: zeropark_engines.assistant`.

- [ ] **Step 3: Create the engine (core loop, no tool specs yet)**

`packages/zeropark-engines/src/zeropark_engines/assistant.py`:

```python
"""ASSISTANT — conversational engine that can call other capabilities as tools.

Unlike SuperAgentEngine (a one-shot planner->researcher->reporter research loop),
this is a multi-turn chat loop: it carries params.history like LLMChatEngine, but
exposes a configurable set of other engines (image, slides, sheets, research, rag)
as native tools. Which tools an agent may use comes from params["tools"]; a tool
whose capability has no registered engine in this deployment is omitted.

When a tool runs, its sub-task is dispatched through the Router to the engine that
serves that capability; produced artifacts are streamed to the UI as RunEvents and
a short text summary is fed back to the LLM so the conversation can continue.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

from zeropark_core.capabilities import Capability
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import Artifact, RunEvent, TaskRequest, TaskResult, TaskStatus
from zeropark_core.registry import ProviderRegistry
from zeropark_core.router import Router
from zeropark_engines.base import NativeEngine

DEFAULT_MAX_ITERATIONS = 10

DEFAULT_SYSTEM_PROMPT = (
    "You are Zeropark's assistant: helpful, concise, and direct. "
    "You can call tools to generate images, slides, spreadsheets, run research, "
    "or search the knowledge base when the user asks for them. "
    "Answer in the same language the user writes in."
)

# tool name -> capability it dispatches to. Add a row to expose a new engine.
TOOL_CAPABILITY: dict[str, Capability] = {
    "generate_image": Capability.IMAGE,
    "make_slides": Capability.SLIDES,
    "make_sheet": Capability.SHEETS,
    "research": Capability.RESEARCH,
    "search_knowledge": Capability.RAG,
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "generate_image": "Generate an image from a text prompt.",
    "make_slides": "Generate an editable slide deck (PPTX) from a topic or outline.",
    "make_sheet": "Generate a spreadsheet (XLSX) from a description of the data.",
    "research": "Run multi-step web research with citations and return findings.",
    "search_knowledge": "Search the uploaded knowledge base and return relevant excerpts.",
}


class AssistantEngine(NativeEngine):
    id = "assistant"
    name = "Assistant Engine"
    capabilities = frozenset({Capability.ASSISTANT})
    reference = "Native conversational tool-calling engine"

    def __init__(
        self,
        llm_client: BaseLLMClient,
        registry: ProviderRegistry,
        *,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations

    # --------------------------------------------------------------- helpers

    def _build_messages(self, task: TaskRequest) -> list[ChatMessage]:
        system = task.params.get("system") or DEFAULT_SYSTEM_PROMPT
        messages = [ChatMessage(role="system", content=system)]
        for turn in task.params.get("history", []) or []:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant", "system") and content:
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=task.prompt))
        return messages

    def _tool_specs(self, task: TaskRequest) -> list[dict[str, Any]]:
        return []  # tools added in Task 3

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        task: TaskRequest,
        task_id: str,
        emit: Callable[[RunEvent], None],
    ) -> str:
        return f"Error: unknown tool '{name}'"  # filled in Task 3

    # ------------------------------------------------------------------ loop

    async def _run(
        self,
        request: TaskRequest,
        task_id: str,
        emit: Callable[[RunEvent], None],
    ) -> TaskResult:
        model = request.params.get("model") or self.model
        max_iterations = int(request.params.get("max_iterations") or self.max_iterations)
        tools = self._tool_specs(request)
        messages = self._build_messages(request)

        total_prompt_tokens = 0
        total_completion_tokens = 0
        start_time = time.time()
        iterations = 0
        final_answer = ""

        for iterations in range(1, max_iterations + 1):
            response = await self.llm_client.achat_completion(
                messages, model=model, temperature=self.temperature, tools=tools or None
            )
            total_prompt_tokens += response.prompt_tokens
            total_completion_tokens += response.completion_tokens

            if not response.tool_calls:
                final_answer = response.content or ""
                break

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )
            )
            if response.content:
                emit(RunEvent(type="log", task_id=task_id, provider_id=self.id,
                              message=response.content,
                              data={"phase": "thought", "iteration": iterations}))

            for tool_call in response.tool_calls:
                try:
                    arguments = json.loads(tool_call.arguments) if tool_call.arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
                emit(RunEvent(type="status", task_id=task_id, provider_id=self.id,
                              message=f"tool:{tool_call.name}",
                              data={"phase": "action", "tool": tool_call.name, "arguments": arguments}))
                try:
                    observation = await self._execute_tool(
                        tool_call.name, arguments, request, task_id, emit
                    )
                except Exception as exc:
                    observation = f"Tool execution error: {exc}"
                emit(RunEvent(type="log", task_id=task_id, provider_id=self.id,
                              message=str(observation)[:500],
                              data={"phase": "observation", "tool": tool_call.name}))
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=str(observation),
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )

        if not final_answer:
            final_answer = "Reached the step limit before finishing."

        artifact = Artifact(
            id=f"{task_id}_reply",
            kind="message",
            title="Assistant Reply",
            mime_type="text/markdown",
            inline=final_answer,
        )
        latency_ms = (time.time() - start_time) * 1000
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=Capability.ASSISTANT,
            provider_id=self.id,
            artifacts=[artifact],
            metrics={
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "iterations": iterations,
                "latency_ms": round(latency_ms, 2),
                "model": model,
            },
        )

    async def cap_assistant(self, request: TaskRequest, task_id: str) -> TaskResult:
        events: list[RunEvent] = []
        result = await self._run(request, task_id, events.append)
        result.events = events
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/zeropark-engines/src/zeropark_engines/assistant.py packages/zeropark-engines/tests/test_assistant.py
git commit -m "feat(engines): AssistantEngine conversational core (pure-chat fallback)"
```

---

### Task 3: AssistantEngine — 도구 어댑터 (필터링 · 디스패치 · 아티팩트 emit)

**Files:**
- Modify: `packages/zeropark-engines/src/zeropark_engines/assistant.py` (`_tool_specs`, `_execute_tool`)
- Test: `packages/zeropark-engines/tests/test_assistant.py` (테스트 추가)

**Interfaces:**
- Consumes: `AssistantEngine` (Task 2), `provider.execute(task, task_id=...)` (core `Provider`).
- Produces: 채워진 `_tool_specs(task)` → OpenAI 함수 스펙 리스트; `_execute_tool(...)` → 도구 결과 요약 문자열, 부수효과로 각 아티팩트마다 `RunEvent(type="artifact")` emit.

- [ ] **Step 1: Write the failing tests**

`test_assistant.py`에 추가 (상단 임포트는 Task 2에서 이미 있음):

```python
class _StubImageEngine(NativeEngine):
    id = "stub-image"
    name = "Stub Image"
    capabilities = frozenset({Capability.IMAGE})

    async def cap_image(self, task, task_id):
        art = Artifact(id="img1", kind="image", title=task.prompt[:40],
                       mime_type="image/png", uri="file:///tmp/img1.png")
        return TaskResult(task_id=task_id, status=TaskStatus.SUCCEEDED,
                          capability=Capability.IMAGE, provider_id=self.id, artifacts=[art])


class ToolThenAnswerLLM(BaseLLMClient):
    """1) request generate_image  2) (tool result in history) final text."""

    def __init__(self):
        self.calls = 0

    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="generate_image",
                                     arguments=json.dumps({"prompt": "a cat"}))],
            )
        assert any(m.role == "tool" for m in messages)
        return ChatResponse(content="Here is your image.")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


def _registry_with_image():
    reg = ProviderRegistry()
    reg.register(_StubImageEngine())
    return reg


@pytest.mark.asyncio
async def test_tool_call_dispatches_and_emits_artifact():
    engine = AssistantEngine(ToolThenAnswerLLM(), _registry_with_image(), model="m")
    task = TaskRequest(prompt="draw a cat", capability=Capability.ASSISTANT,
                       params={"tools": ["image"]})
    result = await engine.cap_assistant(task, "a2")
    assert result.artifacts[0].inline == "Here is your image."
    # the image artifact was streamed as a RunEvent during the loop
    artifact_events = [e for e in result.events if e.type == "artifact"]
    assert len(artifact_events) == 1
    assert artifact_events[0].data["artifact"]["kind"] == "image"


@pytest.mark.asyncio
async def test_tools_filtered_to_allowed_list():
    engine = AssistantEngine(PlainLLM(), _registry_with_image(), model="m")
    # image engine is registered, but agent only allows... nothing image-related
    task = TaskRequest(prompt="hi", capability=Capability.ASSISTANT,
                       params={"tools": ["slides"]})
    specs = engine._tool_specs(task)
    # slides requested but no slides engine registered -> excluded;
    # image engine registered but not requested -> excluded
    assert specs == []


@pytest.mark.asyncio
async def test_requested_tool_excluded_when_engine_missing():
    engine = AssistantEngine(PlainLLM(), ProviderRegistry(), model="m")
    task = TaskRequest(prompt="hi", capability=Capability.ASSISTANT,
                       params={"tools": ["image"]})
    assert engine._tool_specs(task) == []


@pytest.mark.asyncio
async def test_requested_tool_present_when_engine_registered():
    engine = AssistantEngine(PlainLLM(), _registry_with_image(), model="m")
    task = TaskRequest(prompt="hi", capability=Capability.ASSISTANT,
                       params={"tools": ["image"]})
    specs = engine._tool_specs(task)
    names = [s["function"]["name"] for s in specs]
    assert names == ["generate_image"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: FAIL — `_tool_specs` returns `[]` always; `_execute_tool` returns unknown-tool error so no artifact event.

- [ ] **Step 3: Implement `_tool_specs`**

`assistant.py`의 `_tool_specs`를 교체:

```python
    def _tool_specs(self, task: TaskRequest) -> list[dict[str, Any]]:
        """Tool specs for capabilities this agent allows AND that have a
        registered engine in this deployment."""
        requested = set(task.params.get("tools") or [])
        specs: list[dict[str, Any]] = []
        for name, capability in TOOL_CAPABILITY.items():
            if capability.value not in requested:
                continue
            if not self.registry.for_capability(capability):
                continue
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": _TOOL_DESCRIPTIONS[name],
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {
                                    "type": "string",
                                    "description": "What to produce or look up.",
                                }
                            },
                            "required": ["prompt"],
                        },
                    },
                }
            )
        return specs
```

- [ ] **Step 4: Implement `_execute_tool`**

`assistant.py`의 `_execute_tool`을 교체:

```python
    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        task: TaskRequest,
        task_id: str,
        emit: Callable[[RunEvent], None],
    ) -> str:
        capability = TOOL_CAPABILITY.get(name)
        if capability is None:
            return f"Error: unknown tool '{name}'"

        router = Router(self.registry)
        try:
            provider = router.select(capability)
        except Exception as exc:
            return f"Error: no engine available for {capability.value}: {exc}"

        # carry RAG permission clipping through to the knowledge engine
        sub_params: dict[str, Any] = {}
        if capability == Capability.RAG:
            for key in ("allowed_collection_ids", "collection_ids"):
                if key in task.params:
                    sub_params[key] = task.params[key]

        sub_task = TaskRequest(
            prompt=arguments.get("prompt", ""),
            capability=capability,
            params=sub_params,
        )
        result = await provider.execute(sub_task, task_id=f"{task_id}_{name}")
        if result.status == TaskStatus.FAILED:
            return f"Tool '{name}' failed: {result.error}"

        parts: list[str] = []
        for artifact in result.artifacts:
            emit(
                RunEvent(
                    type="artifact",
                    task_id=task_id,
                    provider_id=self.id,
                    data={"artifact": artifact.model_dump(mode="json")},
                )
            )
            if artifact.inline:
                # text-bearing results (research, knowledge): feed content back
                parts.append(f"{artifact.title}:\n{str(artifact.inline)[:4000]}")
            else:
                # file results (image, slides, sheet): feed a pointer back
                loc = artifact.uri or "artifact store"
                parts.append(
                    f"{artifact.kind} '{artifact.title}' saved at {loc} ({artifact.mime_type})"
                )
        return "\n\n".join(parts) if parts else "Done."
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: PASS (5 passed — 1 from Task 2 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add packages/zeropark-engines/src/zeropark_engines/assistant.py packages/zeropark-engines/tests/test_assistant.py
git commit -m "feat(engines): AssistantEngine router-backed tool adapter with artifact streaming"
```

---

### Task 4: AssistantEngine 네이티브 스트리밍 + loader 등록

**Files:**
- Modify: `packages/zeropark-engines/src/zeropark_engines/assistant.py` (`stream` 추가)
- Modify: `packages/zeropark-engines/src/zeropark_engines/loader.py`
- Test: `packages/zeropark-engines/tests/test_assistant.py` (스트리밍 테스트 추가)

**Interfaces:**
- Consumes: `AssistantEngine._run` (Task 2/3); `build_registry(...)` (loader).
- Produces: `async AssistantEngine.stream(task, *, task_id) -> AsyncIterator[RunEvent]` (첫 이벤트 `status`, 마지막 `done`, 중간에 `artifact`); loader가 LLM 설정 시 `enabled("assistant")`이면 `AssistantEngine`을 registry에 등록.

- [ ] **Step 1: Write the failing test**

`test_assistant.py`에 추가:

```python
@pytest.mark.asyncio
async def test_stream_yields_status_artifact_done():
    engine = AssistantEngine(ToolThenAnswerLLM(), _registry_with_image(), model="m")
    task = TaskRequest(prompt="draw a cat", capability=Capability.ASSISTANT,
                       params={"tools": ["image"]})
    events = [e async for e in engine.stream(task, task_id="a3")]
    types = [e.type for e in events]
    assert types[0] == "status"
    assert "artifact" in types
    assert types[-1] == "done"


def test_loader_registers_assistant_when_llm_configured():
    from zeropark_engines.loader import build_registry
    registry = build_registry(llm={"api_key": "x", "provider": "openai", "model": "gpt-4o"})
    assert any(p.id == "assistant" for p in registry.all())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: FAIL — `stream` 미정의(기본 Provider.stream가 status/done은 내되 도구 아티팩트 emit 안 함 → 실제로는 통과할 수도 있으니 확인) 및 loader가 assistant 미등록.

> 참고: 기본 `Provider.stream`은 `result.events`를 재생하지 않고 `result.artifacts`(=message 한 개)만 emit하므로 도구 아티팩트가 누락된다. 네이티브 `stream`을 구현해 `_run`의 emit 이벤트를 라이브로 흘려야 한다.

- [ ] **Step 3: Add native `stream` to AssistantEngine**

`assistant.py`에 `cap_assistant` 아래로 추가 (`SuperAgentEngine.stream`과 동일 구조):

```python
    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Native streaming: yield Thought/Action/Observation + tool artifacts live."""
        import asyncio

        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

        yield RunEvent(
            type="status",
            task_id=task_id,
            provider_id=self.id,
            message="started",
            data={"capability": task.capability.value},
        )

        async def runner() -> TaskResult:
            try:
                return await self._run(task, task_id, queue.put_nowait)
            finally:
                queue.put_nowait(None)

        run_task = asyncio.create_task(runner())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

        try:
            result = await run_task
        except Exception as exc:
            yield RunEvent(type="error", task_id=task_id, provider_id=self.id, message=str(exc))
            return

        for artifact in result.artifacts:
            yield RunEvent(
                type="artifact",
                task_id=task_id,
                provider_id=self.id,
                data={"artifact": artifact.model_dump(mode="json")},
            )
        yield RunEvent(
            type="done",
            task_id=task_id,
            provider_id=self.id,
            data={"status": result.status.value, "result": result.model_dump(mode="json")},
        )
```

- [ ] **Step 4: Register in loader**

`loader.py` 상단 임포트에 추가 (다른 엔진 임포트 옆):

```python
from zeropark_engines.assistant import AssistantEngine
```

그리고 `if enabled("super_agent"):` 블록 바로 아래에 추가:

```python
        if enabled("assistant"):
            registry.register(
                AssistantEngine(
                    llm_client=llm_client,
                    registry=registry,
                    model=llm.get("model") or "gpt-4o",
                )
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest packages/zeropark-engines/tests/test_assistant.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Run the full engine + core suites (no regressions)**

Run: `python -m pytest packages/zeropark-engines/tests packages/zeropark-core/tests -q`
Expected: PASS (기존 테스트 전부 그대로 통과).

- [ ] **Step 7: Commit**

```bash
git add packages/zeropark-engines/src/zeropark_engines/assistant.py packages/zeropark-engines/src/zeropark_engines/loader.py packages/zeropark-engines/tests/test_assistant.py
git commit -m "feat(engines): native streaming for AssistantEngine + loader registration"
```

---

### Task 5: 프론트 — 에이전트 생성 시 도구 선택 체크박스

**Files:**
- Modify: `packages/zeropark-web/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: 기존 create/edit App 모달 (`selectedMode`, `handleSubmitApp`, `params`).
- Produces: `selectedMode === 'assistant'`일 때 도구 체크박스 UI를 렌더하고 선택값을 `params.tools`(capability 값 문자열 배열)에 넣어 POST/PATCH. 기존 `App.params`를 통해 `AppViewer`가 그대로 task params로 전달한다.

> 프론트는 자동 테스트 하니스가 없으므로 수동 검증한다.

- [ ] **Step 1: Add tools state**

다른 `useState` 선언들 옆(예: `const [systemPrompt, setSystemPrompt] = ...` 근처)에 추가:

```tsx
  const [tools, setTools] = useState<string[]>([]);
  const ASSISTANT_TOOLS = [
    { value: 'image', label: '이미지 생성' },
    { value: 'slides', label: '슬라이드' },
    { value: 'sheets', label: '시트/표' },
    { value: 'research', label: '리서치/웹검색' },
    { value: 'rag', label: '지식베이스 검색' },
  ];
```

- [ ] **Step 2: Reset/populate tools in the form open handlers**

`resetForm`(또는 신규 생성 초기화 함수) 안에 추가:

```tsx
    setTools([]);
```

`openEditModal(app)` 안, `setSystemPrompt(...)` 줄 아래에 추가:

```tsx
    setTools((app.params as any)?.tools || []);
```

- [ ] **Step 3: Include tools in the submit payload**

`handleSubmitApp`에서 `params` 객체를 만드는 부분(`if (model) params.model = model;` 근처)에 추가:

```tsx
    if (selectedMode === 'assistant') params.tools = tools;
```

- [ ] **Step 4: Render the checkboxes when mode is assistant**

App Template(Mode) select 블록 바로 아래에 추가:

```tsx
              {selectedMode === 'assistant' && (
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>
                    사용할 도구
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
                    {ASSISTANT_TOOLS.map((t) => (
                      <label key={t.value} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <input
                          type="checkbox"
                          checked={tools.includes(t.value)}
                          onChange={(e) =>
                            setTools((prev) =>
                              e.target.checked ? [...prev, t.value] : prev.filter((x) => x !== t.value)
                            )
                          }
                        />
                        {t.label}
                      </label>
                    ))}
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                    체크한 도구만 이 에이전트가 대화 중 호출할 수 있습니다. 아무것도 체크하지 않으면 순수 대화 에이전트가 됩니다.
                  </p>
                </div>
              )}
```

- [ ] **Step 5: Manual verification**

빌드/실행 후 관리자로 로그인 → "Create New App" → Mode를 `assistant`로 선택 → 도구 체크박스가 나타나는지 확인 → image+slides 체크하고 저장 → 그 에이전트로 대화하며 "고양이 그려줘" 요청 시 이미지가 생성·표시되는지, 도구 미체크 에이전트는 순수 대화만 되는지 확인.

빠른 빌드 점검:

Run: `cd packages/zeropark-web && npm run build`
Expected: 타입/빌드 에러 없음.

- [ ] **Step 6: Commit**

```bash
git add packages/zeropark-web/src/pages/Dashboard.tsx
git commit -m "feat(web): tool picker for assistant-mode agents"
```

---

## 자가 검토 (Self-Review)

- **Spec 커버리지:** capability/mode(Task 1) · AssistantEngine 코어(Task 2) · 도구 어댑터+필터링+아티팩트(Task 3) · 스트리밍+loader(Task 4) · 프론트 도구 선택(Task 5). spec의 5개 테스트가 Task 1/2/3/4에 모두 매핑됨. 게이트웨이 주입은 `App.params` 자동 전달로 불필요(spec §5 구현결정 반영).
- **Placeholder 스캔:** 모든 코드 스텝에 실제 코드 포함, TBD 없음.
- **타입 일관성:** `AssistantEngine(llm_client, registry, *, model, temperature, max_iterations)` · `cap_assistant` · `_tool_specs(task)` · `_execute_tool(name, arguments, task, task_id, emit)` · `TOOL_CAPABILITY` · 도구 값 문자열(`"image"` 등)이 프론트·엔진·필터에서 일관됨.

## 범위 밖 (YAGNI)

- 저장된 workflow를 `run_workflow` 도구로 호출.
- 도구별 토큰/비용 한도, browse/audio/page 도구 노출(어댑터 `TOOL_CAPABILITY`에 한 줄로 확장 가능).
