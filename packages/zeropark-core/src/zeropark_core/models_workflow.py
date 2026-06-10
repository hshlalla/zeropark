from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class WorkflowNode(BaseModel):
    id: str
    type: str = Field(
        description="Node type: 'input', 'llm', 'python', 'crawl', 'search', 'browse', 'http', 'condition', 'mcp', 'output'"
    )
    data: Dict[str, Any] = Field(default_factory=dict, description="Configuration or prompt templates")


class WorkflowEdge(BaseModel):
    id: str | None = None
    source: str
    target: str
    # For condition nodes: this edge is followed only when the condition node's
    # outcome matches ("true" / "false"). None = unconditional edge.
    branch: Optional[Literal["true", "false"]] = None


class WorkflowDefinition(BaseModel):
    name: str | None = None
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]


class NodeRun(BaseModel):
    """Per-node execution record — the observability unit a run log is made of."""

    node_id: str
    node_type: str
    status: Literal["succeeded", "failed", "skipped"]
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    output_preview: str = ""
    error: str | None = None


class WorkflowRunResult(BaseModel):
    """Full result of one workflow execution: final context + per-node log."""

    status: Literal["succeeded", "failed"]
    context: Dict[str, Any] = Field(default_factory=dict)
    node_runs: List[NodeRun] = Field(default_factory=list)
    duration_ms: float = 0.0
