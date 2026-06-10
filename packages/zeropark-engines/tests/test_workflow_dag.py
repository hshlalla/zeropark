"""DAGOrchestrator: branching, http node, node-run observability."""

import pytest

from zeropark_core.llm import BaseLLMClient, ChatMessage, ChatResponse
from zeropark_core.models_workflow import WorkflowDefinition, WorkflowEdge, WorkflowNode
from zeropark_engines.workflow import DAGOrchestrator


class EchoLLM(BaseLLMClient):
    def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, tools=None, **kwargs):
        return ChatResponse(content=f"LLM({messages[-1].content})")

    def create_embeddings(self, texts, model="x"):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_condition_branching_skips_inactive_branch():
    definition = WorkflowDefinition(
        nodes=[
            WorkflowNode(id="in", type="input", data={"score": "85"}),
            WorkflowNode(id="cond", type="condition", data={"left": "{{score}}", "operator": ">", "right": "60"}),
            WorkflowNode(id="pass_llm", type="llm", data={"prompt": "passed with {{score}}"}),
            WorkflowNode(id="fail_llm", type="llm", data={"prompt": "failed with {{score}}"}),
        ],
        edges=[
            WorkflowEdge(source="in", target="cond"),
            WorkflowEdge(source="cond", target="pass_llm", branch="true"),
            WorkflowEdge(source="cond", target="fail_llm", branch="false"),
        ],
    )
    orchestrator = DAGOrchestrator(definition, llm_client=EchoLLM(), sandbox=False)
    result = await orchestrator.run({})

    assert result.status == "succeeded"
    statuses = {r.node_id: r.status for r in result.node_runs}
    assert statuses["pass_llm"] == "succeeded"
    assert statuses["fail_llm"] == "skipped"
    assert result.context["cond_result"] == "true"
    assert result.context["pass_llm_result"] == "LLM(passed with 85)"


@pytest.mark.asyncio
async def test_node_runs_record_failures_and_skip_descendants():
    definition = WorkflowDefinition(
        nodes=[
            WorkflowNode(id="bad", type="search", data={"query": "x"}),  # no backend configured
            WorkflowNode(id="downstream", type="llm", data={"prompt": "{{bad_result}}"}),
        ],
        edges=[WorkflowEdge(source="bad", target="downstream")],
    )
    orchestrator = DAGOrchestrator(definition, llm_client=EchoLLM(), search_kwargs=None, sandbox=False)
    result = await orchestrator.run({})

    assert result.status == "failed"
    statuses = {r.node_id: r.status for r in result.node_runs}
    assert statuses["bad"] == "failed"
    assert statuses["downstream"] == "skipped"
    bad_run = next(r for r in result.node_runs if r.node_id == "bad")
    assert "not configured" in (bad_run.error or "")


@pytest.mark.asyncio
async def test_missing_llm_fails_node_not_orchestrator():
    definition = WorkflowDefinition(
        nodes=[WorkflowNode(id="llm1", type="llm", data={"prompt": "hi"})],
        edges=[],
    )
    orchestrator = DAGOrchestrator(definition, llm_client=None, sandbox=False)
    result = await orchestrator.run({})
    assert result.status == "failed"
    assert result.node_runs[0].status == "failed"


def test_cycle_detection():
    definition = WorkflowDefinition(
        nodes=[
            WorkflowNode(id="a", type="input", data={}),
            WorkflowNode(id="b", type="input", data={}),
        ],
        edges=[WorkflowEdge(source="a", target="b"), WorkflowEdge(source="b", target="a")],
    )
    with pytest.raises(ValueError, match="cycle"):
        DAGOrchestrator(definition, sandbox=False)
