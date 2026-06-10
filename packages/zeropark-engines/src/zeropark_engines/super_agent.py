"""SUPER_AGENT — long-horizon agent loop over native tools.

Native OpenAI-style tool calling (no fragile JSON-in-text parsing), real tools
(web search, crawl, sandboxed python, MCP), and live RunEvent streaming so the
UI renders Thought/Action progress as it happens.

Design reference: DeerFlow / OpenManus (MIT) — design only, no code used.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Callable, Optional

from zeropark_core import (
    Artifact,
    Capability,
    RunEvent,
    TaskRequest,
    TaskResult,
    TaskStatus,
    ArtifactStore,
)
from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.mcp_client import MCPClientManager
from zeropark_engines.base import NativeEngine
from zeropark_engines.sandbox import DockerSandbox, PythonSandbox

DEFAULT_MAX_ITERATIONS = 15

PLANNER_PROMPT = """You are the Planner. Analyze the user's request and create a concise, step-by-step research execution plan. Do not execute the plan, just return the numbered list of steps."""
RESEARCHER_PROMPT = """You are the Researcher. Execute the following plan step-by-step using the provided tools to gather facts and run computations. Cite your sources. Return your comprehensive research notes when finished."""
REPORTER_PROMPT = """You are the Reporter. Using the provided research notes, write the final comprehensive response to the user's original request in well-structured markdown."""


def _build_sandbox() -> Optional[Any]:
    """Prefer Docker isolation; fall back to in-process exec ONLY when the
    operator explicitly opted in via ZEROPARK_ALLOW_UNSAFE_SANDBOX."""
    try:
        return DockerSandbox()
    except Exception:
        pass
    try:
        return PythonSandbox()
    except PermissionError:
        return None


class SuperAgentEngine(NativeEngine):
    id = "zeropark_engines.super_agent"
    name = "Super Agent Engine"
    capabilities = frozenset({Capability.WORKFLOW, Capability.SUPER_AGENT})
    reference = "DeerFlow (MIT), OpenManus (MIT) - design reference only"

    def __init__(
        self,
        store: ArtifactStore,
        llm_client: BaseLLMClient,
        *,
        search_engine: NativeEngine | None = None,
        crawl_engine: NativeEngine | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_iterations: int | None = None,
        mcp_manager: MCPClientManager | None = None,
    ) -> None:
        self.store = store
        self.llm_client = llm_client
        self.search_engine = search_engine
        self.crawl_engine = crawl_engine
        self.model = model or os.environ.get("ZEROPARK_AGENT_MODEL", "gpt-4o")
        self.temperature = temperature
        self.max_iterations = max_iterations or int(
            os.environ.get("ZEROPARK_AGENT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)
        )
        self.sandbox = _build_sandbox()

        # Shared MCP manager: connected once and reused across requests. The
        # config path comes from the environment, not a hardcoded machine path.
        self._mcp_manager = mcp_manager
        self._mcp_connected = mcp_manager is not None and bool(mcp_manager.sessions)
        self._mcp_lock = asyncio.Lock()
        self._mcp_tools: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ MCP

    async def _ensure_mcp(self) -> None:
        if self._mcp_manager is None:
            config_path = os.environ.get("ZEROPARK_MCP_CONFIG", "mcp_servers.json")
            if not os.path.exists(config_path):
                return
            self._mcp_manager = MCPClientManager(config_path)
        async with self._mcp_lock:
            if not self._mcp_connected:
                try:
                    await self._mcp_manager.connect_all()
                    self._mcp_tools = await self._mcp_manager.get_all_tools()
                    self._mcp_connected = True
                except Exception as exc:
                    print(f"Warning: MCP connection failed, continuing without MCP tools: {exc}")
                    self._mcp_manager = None

    # ---------------------------------------------------------------- tools

    def _tool_specs(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self.sandbox is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "python_exec",
                        "description": "Run Python code in an isolated sandbox and return stdout/stderr. Use for math, data manipulation, or file generation.",
                        "parameters": {
                            "type": "object",
                            "properties": {"code": {"type": "string", "description": "Python source code to execute."}},
                            "required": ["code"],
                        },
                    },
                }
            )
        if self.search_engine is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web and return top results (title, url, snippet).",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "limit": {"type": "integer", "description": "Max results (default 5)."},
                            },
                            "required": ["query"],
                        },
                    },
                }
            )
        if self.crawl_engine is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "crawl_url",
                        "description": "Fetch a public URL and return its content as clean markdown.",
                        "parameters": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                            "required": ["url"],
                        },
                    },
                }
            )
        for tool in self._mcp_tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description") or "",
                        "parameters": tool.get("inputSchema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return tools

    async def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "python_exec":
            code = arguments.get("code", "")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.sandbox.execute(code)
            )
        if name == "web_search" and self.search_engine is not None:
            sub_task = TaskRequest(
                prompt=arguments.get("query", ""),
                capability=Capability.SEARCH,
                params={"limit": int(arguments.get("limit", 5))},
            )
            result = await self.search_engine.cap_search(sub_task, task_id="agent_search")
            return json.dumps(
                [
                    {"title": s.title, "url": s.url, "snippet": s.snippet}
                    for s in result.sources
                ],
                ensure_ascii=False,
            )
        if name == "crawl_url" and self.crawl_engine is not None:
            sub_task = TaskRequest(
                prompt="crawl",
                capability=Capability.CRAWL,
                params={"url": arguments.get("url", "")},
            )
            result = await self.crawl_engine.cap_crawl(sub_task, task_id="agent_crawl")
            content = result.artifacts[0].inline if result.artifacts else ""
            return str(content)[:8000]
        if "__" in name and self._mcp_manager is not None:
            server_name, tool_name = name.split("__", 1)
            return await self._mcp_manager.execute_tool(server_name, tool_name, arguments)
        return f"Error: unknown tool '{name}'"

    # ----------------------------------------------------------------- loop

    async def _run(
        self,
        request: TaskRequest,
        task_id: str,
        emit: Callable[[RunEvent], None],
    ) -> TaskResult:
        await self._ensure_mcp()
        tools = self._tool_specs()
        model = request.params.get("model") or self.model
        max_iterations = int(request.params.get("max_iterations") or self.max_iterations)

        total_prompt_tokens = 0
        total_completion_tokens = 0
        start_time = time.time()

        # ----------------------------------------------------- Phase 1: Planner
        emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message="[Planner] Analyzing request and creating execution plan...", data={"phase": "thought", "iteration": 0}))
        plan_messages = [
            ChatMessage(role="system", content=PLANNER_PROMPT),
            ChatMessage(role="user", content=request.prompt),
        ]
        plan_response = await self.llm_client.achat_completion(plan_messages, model=model, temperature=self.temperature)
        total_prompt_tokens += plan_response.prompt_tokens
        total_completion_tokens += plan_response.completion_tokens
        plan_text = plan_response.content or "No plan generated."
        emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message=f"[Planner] Plan created:\n{plan_text}", data={"phase": "observation", "iteration": 0}))

        # -------------------------------------------------- Phase 2: Researcher
        emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message="[Researcher] Executing plan using tools...", data={"phase": "thought", "iteration": 1}))
        research_messages = [
            ChatMessage(role="system", content=f"{RESEARCHER_PROMPT}\n\nExecution Plan:\n{plan_text}"),
            ChatMessage(role="user", content=request.prompt),
        ]
        
        research_notes = ""
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            response = await self.llm_client.achat_completion(
                research_messages, model=model, temperature=self.temperature, tools=tools or None
            )
            total_prompt_tokens += response.prompt_tokens
            total_completion_tokens += response.completion_tokens

            if not response.tool_calls:
                research_notes = response.content or "No findings."
                break

            research_messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )
            )
            if response.content:
                emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message=response.content, data={"phase": "thought", "iteration": iterations}))

            for tool_call in response.tool_calls:
                try:
                    arguments = json.loads(tool_call.arguments) if tool_call.arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
                emit(RunEvent(type="status", task_id=task_id, provider_id=self.id, message=f"tool:{tool_call.name}", data={"phase": "action", "tool": tool_call.name, "arguments": arguments}))
                
                try:
                    observation = await self._execute_tool(tool_call.name, arguments)
                except Exception as exc:
                    observation = f"Tool execution error: {exc}"
                
                emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message=str(observation)[:500], data={"phase": "observation", "tool": tool_call.name}))
                research_messages.append(
                    ChatMessage(
                        role="tool",
                        content=str(observation),
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )

        if not research_notes:
            research_notes = "Max iterations reached. Incomplete research."
        emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message=f"[Researcher] Research finished. Notes compiled ({len(research_notes)} chars).", data={"phase": "observation", "iteration": iterations}))

        # ---------------------------------------------------- Phase 3: Reporter
        emit(RunEvent(type="log", task_id=task_id, provider_id=self.id, message="[Reporter] Writing final response...", data={"phase": "thought", "iteration": iterations+1}))
        report_messages = [
            ChatMessage(role="system", content=f"{REPORTER_PROMPT}\n\nResearch Notes:\n{research_notes}"),
            ChatMessage(role="user", content=request.prompt),
        ]
        report_response = await self.llm_client.achat_completion(report_messages, model=model, temperature=self.temperature)
        total_prompt_tokens += report_response.prompt_tokens
        total_completion_tokens += report_response.completion_tokens
        final_answer = report_response.content or "Failed to generate report."

        artifact = Artifact(
            id=f"{task_id}_agent_result",
            kind="report",
            title="Super Agent Report",
            mime_type="text/markdown",
            inline=final_answer,
        )
        latency_ms = (time.time() - start_time) * 1000
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCEEDED,
            capability=request.capability,
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

    async def _run_capability(self, request: TaskRequest, task_id: str) -> TaskResult:
        events: list[RunEvent] = []
        result = await self._run(request, task_id, events.append)
        result.events = events
        return result

    async def cap_super_agent(self, request: TaskRequest, task_id: str) -> TaskResult:
        return await self._run_capability(request, task_id)

    async def cap_workflow(self, request: TaskRequest, task_id: str) -> TaskResult:
        return await self._run_capability(request, task_id)

    async def stream(self, task: TaskRequest, *, task_id: str) -> AsyncIterator[RunEvent]:
        """Native streaming: yield Thought/Action/Observation events live."""
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
            yield RunEvent(
                type="error", task_id=task_id, provider_id=self.id, message=str(exc)
            )
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
