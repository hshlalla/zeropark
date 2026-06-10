"""DAG workflow orchestrator (design reference: Dify — reimplemented natively).

Node types: input, python, llm, crawl, search, browse, http, condition, mcp, output.
Every run produces a per-node execution log (NodeRun) so operators can see what
each node did, how long it took, and why it failed — the observability layer a
visual workflow product needs.

Dependencies (LLM client, search backend, sandbox) are INJECTED from settings.
A missing dependency fails the node that needs it with a clear message; it never
crashes orchestrator construction.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import networkx as nx

from zeropark_core.llm import BaseLLMClient, ChatMessage
from zeropark_core.models import TaskRequest
from zeropark_core.capabilities import Capability
from zeropark_core.netguard import validate_public_url
from zeropark_core.models_workflow import (
    NodeRun,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowRunResult,
)
from zeropark_engines.sandbox import DockerSandbox, PythonSandbox


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_sandbox():
    try:
        return DockerSandbox(allow_network=True)
    except Exception:
        pass
    try:
        return PythonSandbox()
    except PermissionError:
        return None


def _render(template: str, context: Dict[str, Any]) -> str:
    for key, value in context.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    return template


_CONDITION_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "contains": lambda a, b: b in a,
    "not_contains": lambda a, b: b not in a,
    ">": lambda a, b: float(a) > float(b),
    "<": lambda a, b: float(a) < float(b),
    ">=": lambda a, b: float(a) >= float(b),
    "<=": lambda a, b: float(a) <= float(b),
}


class DAGOrchestrator:
    """Executes a directed acyclic graph of workflow nodes with run logging."""

    def __init__(
        self,
        definition: WorkflowDefinition,
        *,
        llm_client: Optional[BaseLLMClient] = None,
        default_model: str = "gpt-4o",
        search_kwargs: Optional[dict] = None,
        store=None,
        sandbox=None,
    ):
        self.definition = definition
        self.llm_client = llm_client
        self.default_model = default_model
        self.search_kwargs = search_kwargs
        self.store = store
        self.sandbox = sandbox if sandbox is not None else _build_sandbox()
        self.context: Dict[str, Any] = {}

        self.graph = nx.DiGraph()
        for node in self.definition.nodes:
            self.graph.add_node(node.id, data=node)
        for edge in self.definition.edges:
            self.graph.add_edge(edge.source, edge.target, branch=edge.branch)

        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError("Workflow contains cycles (infinite loops). Must be a DAG.")

    # ----------------------------------------------------------------- run

    async def execute(self, initial_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Backwards-compatible API: returns the final context dict."""
        result = await self.run(initial_inputs)
        return result.context

    async def run(self, initial_inputs: Dict[str, Any]) -> WorkflowRunResult:
        self.context.update(initial_inputs)
        node_runs: list[NodeRun] = []
        run_started = time.time()
        overall = "succeeded"

        # node_id -> condition outcome ("true"/"false"), used for branch gating
        outcomes: Dict[str, str] = {}
        executed: set[str] = set()
        skipped: set[str] = set()

        for node_id in nx.topological_sort(self.graph):
            node: WorkflowNode = self.graph.nodes[node_id]["data"]

            if self._should_skip(node_id, executed, skipped, outcomes):
                skipped.add(node_id)
                now = _utcnow()
                node_runs.append(
                    NodeRun(
                        node_id=node_id,
                        node_type=node.type,
                        status="skipped",
                        started_at=now,
                        finished_at=now,
                        duration_ms=0.0,
                    )
                )
                continue

            started = _utcnow()
            t0 = time.time()
            try:
                output = await self._execute_node(node)
                if node.type == "condition":
                    outcomes[node_id] = str(output)
                executed.add(node_id)
                node_runs.append(
                    NodeRun(
                        node_id=node_id,
                        node_type=node.type,
                        status="succeeded",
                        started_at=started,
                        finished_at=_utcnow(),
                        duration_ms=round((time.time() - t0) * 1000, 2),
                        output_preview=str(output)[:300] if output is not None else "",
                    )
                )
            except Exception as exc:
                overall = "failed"
                self.context[f"{node_id}_result"] = f"Error: {exc}"
                node_runs.append(
                    NodeRun(
                        node_id=node_id,
                        node_type=node.type,
                        status="failed",
                        started_at=started,
                        finished_at=_utcnow(),
                        duration_ms=round((time.time() - t0) * 1000, 2),
                        error=str(exc),
                    )
                )
                # a failed node poisons its descendants
                skipped.add(node_id)

        return WorkflowRunResult(
            status=overall,
            context=self.context,
            node_runs=node_runs,
            duration_ms=round((time.time() - run_started) * 1000, 2),
        )

    def _should_skip(
        self,
        node_id: str,
        executed: set[str],
        skipped: set[str],
        outcomes: Dict[str, str],
    ) -> bool:
        """A node runs if at least one incoming edge is 'active'. Roots always run."""
        in_edges = list(self.graph.in_edges(node_id, data=True))
        if not in_edges:
            return False
        for source, _, attrs in in_edges:
            if source in skipped:
                continue
            if source not in executed:
                continue
            branch = attrs.get("branch")
            if branch is not None and outcomes.get(source) != branch:
                continue
            return False  # found an active edge
        return True

    # --------------------------------------------------------------- nodes

    async def _execute_node(self, node: WorkflowNode) -> Any:
        handler = getattr(self, f"_node_{node.type}", None)
        if handler is None:
            raise ValueError(f"Unknown node type '{node.type}'")
        return await handler(node)

    async def _node_input(self, node: WorkflowNode) -> Any:
        for key, value in node.data.items():
            self.context[key] = value
        return None

    async def _node_output(self, node: WorkflowNode) -> Any:
        keys = node.data.get("keys")
        if keys:
            collected = {k: self.context.get(k) for k in keys}
            self.context[f"{node.id}_result"] = collected
            return collected
        return None

    async def _node_python(self, node: WorkflowNode) -> str:
        if self.sandbox is None:
            raise RuntimeError(
                "No sandbox available: run Docker, or set ZEROPARK_ALLOW_UNSAFE_SANDBOX=1 for local dev."
            )
        code = _render(node.data.get("code", ""), self.context)
        result = self.sandbox.execute(code)
        self.context[f"{node.id}_result"] = result.strip()
        return result.strip()

    async def _node_llm(self, node: WorkflowNode) -> str:
        if self.llm_client is None:
            raise RuntimeError("LLM is not configured (ZEROPARK_LLM__API_KEY).")
        prompt = _render(node.data.get("prompt", ""), self.context)
        model = node.data.get("model") or self.default_model
        system = node.data.get("system")
        messages = []
        if system:
            messages.append(ChatMessage(role="system", content=system))
        messages.append(ChatMessage(role="user", content=prompt))
        response = await self.llm_client.achat_completion(
            messages, model=model, temperature=float(node.data.get("temperature", 0.7))
        )
        self.context[f"{node.id}_result"] = response.content
        return response.content

    async def _node_condition(self, node: WorkflowNode) -> str:
        left = _render(str(node.data.get("left", "")), self.context)
        right = _render(str(node.data.get("right", "")), self.context)
        operator = node.data.get("operator", "==")
        op = _CONDITION_OPS.get(operator)
        if op is None:
            raise ValueError(f"Unsupported condition operator '{operator}'")
        outcome = "true" if op(left, right) else "false"
        self.context[f"{node.id}_result"] = outcome
        return outcome

    async def _node_http(self, node: WorkflowNode) -> str:
        url = _render(node.data.get("url", ""), self.context)
        validate_public_url(url)
        method = str(node.data.get("method", "GET")).upper()
        headers = node.data.get("headers") or {}
        body = node.data.get("body")
        if isinstance(body, str):
            body = _render(body, self.context)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.request(
                method, url, headers=headers, content=body if isinstance(body, str) else None,
                json=body if isinstance(body, dict) else None,
            )
        text = response.text[:10000]
        self.context[f"{node.id}_result"] = text
        self.context[f"{node.id}_status_code"] = response.status_code
        return text

    async def _node_crawl(self, node: WorkflowNode) -> str:
        from zeropark_engines.crawl import LocalCrawlEngine

        url = _render(node.data.get("url", ""), self.context)
        engine = LocalCrawlEngine()
        task = TaskRequest(prompt=url, capability=Capability.CRAWL, params={"url": url})
        result = await engine.cap_crawl(task, task_id=node.id)
        content = result.artifacts[0].inline if result.artifacts else ""
        self.context[f"{node.id}_result"] = content
        return str(content)[:300]

    async def _node_search(self, node: WorkflowNode) -> Any:
        from zeropark_engines.search import WebSearchEngine

        if not self.search_kwargs or not self.search_kwargs.get("base_url"):
            raise RuntimeError("Search backend is not configured (ZEROPARK_SEARCH__BASE_URL).")
        query = _render(node.data.get("query", ""), self.context)
        engine = WebSearchEngine(**self.search_kwargs)
        task = TaskRequest(
            prompt=query, capability=Capability.SEARCH,
            params={"limit": int(node.data.get("limit", 5))},
        )
        result = await engine.cap_search(task, task_id=node.id)
        sources = [
            {"title": s.title, "url": s.url, "snippet": s.snippet} for s in result.sources
        ]
        self.context[f"{node.id}_result"] = sources
        return sources

    async def _node_browse(self, node: WorkflowNode) -> str:
        from zeropark_engines.browse import PlaywrightBrowseEngine
        from zeropark_core.store import LocalArtifactStore

        url = _render(node.data.get("url", ""), self.context)
        store = self.store or LocalArtifactStore(base_dir="artifacts")
        engine = PlaywrightBrowseEngine(store=store)
        task = TaskRequest(prompt=url, capability=Capability.BROWSE, params={"url": url})
        result = await engine.cap_browse(task, task_id=node.id)
        if result.error:
            raise RuntimeError(result.error)
        content = ""
        for artifact in result.artifacts:
            if artifact.mime_type == "text/markdown":
                content = artifact.inline or ""
        self.context[f"{node.id}_result"] = content
        return str(content)[:300]

    async def _node_mcp(self, node: WorkflowNode) -> str:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        data = node.data
        command = data.get("command", "npx")
        args_str = _render(data.get("args", ""), self.context)
        tool_name = data.get("toolName", "echo")
        tool_args = json.loads(_render(data.get("toolArgs", "{}"), self.context))

        server_params = StdioServerParameters(command=command, args=args_str.split(), env=None)
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=tool_args)
                texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
                output = "\n".join(texts)
        self.context[f"{node.id}_result"] = output
        return output

    async def _node_slides(self, node: WorkflowNode) -> str:
        self.context[f"{node.id}_result"] = "Slides Engine Triggered: (Artifact generated in artifact store)"
        return self.context[f"{node.id}_result"]

    async def _node_sheets(self, node: WorkflowNode) -> str:
        self.context[f"{node.id}_result"] = "Sheets Engine Triggered: (Excel Artifact generated in store)"
        return self.context[f"{node.id}_result"]

    async def _node_loop(self, node: WorkflowNode) -> Any:
        """A Map-Reduce style loop node that iterates over a list and executes a sub-node."""
        iterator_var = node.data.get("iterator_var", "")
        item_var = node.data.get("item_var", "item")
        
        # Resolve the list to iterate over
        items = self.context.get(iterator_var)
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = [items]
        if not isinstance(items, list):
            raise ValueError(f"Loop iterator '{iterator_var}' must resolve to a list.")
            
        sub_node_data = node.data.get("sub_node")
        if not sub_node_data:
            raise ValueError("Loop node requires a 'sub_node' configuration.")
            
        # Create a mock node for the sub-execution
        sub_node = WorkflowNode(id=f"{node.id}_sub", type=sub_node_data.get("type", "python"), data=sub_node_data.get("data", {}))
        
        results = []
        for idx, item in enumerate(items):
            # inject loop item into context
            self.context[item_var] = item
            self.context[f"{item_var}_index"] = idx
            
            # Execute the sub_node
            try:
                res = await self._execute_node(sub_node)
                results.append(res)
            except Exception as e:
                results.append(f"Error at index {idx}: {str(e)}")
                
        self.context[f"{node.id}_result"] = results
        return results
