import json
import uuid
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from zeropark_core import ZeroparkSettings
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.llm import create_llm_client
from zeropark_core.models_db import WorkflowRun
from zeropark_core.models_workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge
from zeropark_engines.workflow import DAGOrchestrator

workflow_router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["workflow"],
)

class ReactFlowNode(BaseModel):
    id: str
    data: Dict[str, Any]
    # ignoring position, measured, etc.

class ReactFlowEdge(BaseModel):
    source: str
    target: str
    branch: str | None = None  # "true"/"false" for condition outputs
    # ignoring id, sourceHandle, etc.

class WorkflowRunRequest(BaseModel):
    nodes: List[ReactFlowNode]
    edges: List[ReactFlowEdge]
    initial_inputs: Dict[str, Any] = {}


def _build_orchestrator(definition: WorkflowDefinition) -> DAGOrchestrator:
    settings = ZeroparkSettings()
    llm_client = None
    if settings.llm.api_key:
        llm_client = create_llm_client(
            settings.llm.provider, settings.llm.api_key, settings.llm.base_url
        )
    return DAGOrchestrator(
        definition,
        llm_client=llm_client,
        default_model=settings.llm.model or "gpt-4o",
        search_kwargs=settings.search_kwargs(),
    )


@workflow_router.post("/run")
async def run_workflow(request: WorkflowRunRequest):
    # Convert React Flow schema to Engine WorkflowDefinition schema
    workflow_nodes = []
    for n in request.nodes:
        # Our frontend stores the actual engine type inside data.type (e.g. 'llm', 'sandbox')
        node_type = n.data.get("type", "unknown")
        if node_type == "sandbox":
            node_type = "python"  # engine uses 'python' for sandbox
        workflow_nodes.append(WorkflowNode(id=n.id, type=node_type, data=n.data))

    workflow_edges = [
        WorkflowEdge(source=e.source, target=e.target, branch=e.branch)
        for e in request.edges
    ]
    definition = WorkflowDefinition(
        name="FrontendTriggeredWorkflow", nodes=workflow_nodes, edges=workflow_edges
    )

    try:
        orchestrator = _build_orchestrator(definition)
    except ValueError as exc:  # cycle detection / bad config
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await orchestrator.run(request.initial_inputs)

    # Persist the run log for observability (admin can audit every execution).
    run_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        session.add(
            WorkflowRun(
                id=run_id,
                workflow_name=definition.name,
                status=result.status,
                node_runs=json.dumps(
                    [r.model_dump(mode="json") for r in result.node_runs], default=str
                ),
                duration_ms=str(result.duration_ms),
            )
        )
        await session.commit()

    return {
        "status": "success" if result.status == "succeeded" else "failed",
        "run_id": run_id,
        "results": result.context,
        "node_runs": [r.model_dump(mode="json") for r in result.node_runs],
        "duration_ms": result.duration_ms,
    }


@workflow_router.get("/runs")
async def list_runs(limit: int = 20):
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(limit)
        )
        runs = rows.scalars().all()
    return {
        "runs": [
            {
                "id": r.id,
                "workflow_name": r.workflow_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@workflow_router.get("/runs/{run_id}")
async def get_run(run_id: str):
    async with AsyncSessionLocal() as session:
        run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "workflow_name": run.workflow_name,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "node_runs": json.loads(run.node_runs) if run.node_runs else [],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
