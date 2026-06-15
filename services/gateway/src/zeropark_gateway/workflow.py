import json
import uuid
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from zeropark_gateway.auth import get_current_user

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


def _definition_from_payload(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], name: str
) -> WorkflowDefinition:
    """Convert a React Flow {nodes, edges} payload to the engine schema."""
    workflow_nodes = []
    for n in nodes:
        data = n.get("data", {})
        node_type = data.get("type", "unknown")
        if node_type == "sandbox":
            node_type = "python"  # engine uses 'python' for sandbox
        workflow_nodes.append(WorkflowNode(id=n["id"], type=node_type, data=data))
    workflow_edges = [
        WorkflowEdge(source=e["source"], target=e["target"], branch=e.get("branch"))
        for e in edges
    ]
    return WorkflowDefinition(name=name, nodes=workflow_nodes, edges=workflow_edges)


async def _execute_and_log(
    definition: WorkflowDefinition, initial_inputs: Dict[str, Any]
) -> Dict[str, Any]:
    """Build, run, and persist a workflow execution. Shared by ad-hoc runs and
    saved-workflow / app-published runs so observability is identical."""
    try:
        orchestrator = _build_orchestrator(definition)
    except ValueError as exc:  # cycle detection / bad config
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await orchestrator.run(initial_inputs)

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


@workflow_router.post("/run")
async def run_workflow(request: WorkflowRunRequest):
    definition = _definition_from_payload(
        [n.model_dump() for n in request.nodes],
        [e.model_dump() for e in request.edges],
        "FrontendTriggeredWorkflow",
    )
    return await _execute_and_log(definition, request.initial_inputs)


class SavedRunRequest(BaseModel):
    initial_inputs: Dict[str, Any] = {}
    prompt: str | None = None  # convenience: surfaced into the context as `prompt`


@workflow_router.post("/saved/{workflow_id}/run")
async def run_saved_workflow(
    workflow_id: str, body: SavedRunRequest, current_user: dict = Depends(get_current_user)
):
    """Run a workflow that was saved/published — the path an App uses when its
    mode is 'workflow' and params.workflow_id points at a saved definition."""
    from zeropark_core.models_db import SavedWorkflow

    async with AsyncSessionLocal() as session:
        row = await session.get(SavedWorkflow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    saved = json.loads(row.definition)
    definition = _definition_from_payload(
        saved.get("nodes", []), saved.get("edges", []), row.name
    )
    inputs = dict(body.initial_inputs)
    if body.prompt is not None:
        inputs.setdefault("prompt", body.prompt)
    return await _execute_and_log(definition, inputs)


# --------------------------------------------------- saved workflows (CRUD)
# The editor saves/loads React Flow JSON as-is; export/import is the same doc.

class SavedWorkflowRequest(BaseModel):
    name: str
    definition: Dict[str, Any]  # {nodes: [...], edges: [...]}


@workflow_router.post("/saved")
async def save_workflow(body: SavedWorkflowRequest, current_user: dict = Depends(get_current_user)):
    from zeropark_core.models_db import SavedWorkflow

    row = SavedWorkflow(
        name=body.name,
        definition=json.dumps(body.definition, ensure_ascii=False),
        created_by=current_user.get("user_id"),
    )
    async with AsyncSessionLocal() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"id": row.id, "name": row.name}


@workflow_router.put("/saved/{workflow_id}")
async def update_saved_workflow(workflow_id: str, body: SavedWorkflowRequest, current_user: dict = Depends(get_current_user)):
    from zeropark_core.models_db import SavedWorkflow

    async with AsyncSessionLocal() as session:
        row = await session.get(SavedWorkflow, workflow_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        row.name = body.name
        row.definition = json.dumps(body.definition, ensure_ascii=False)
        await session.commit()
    return {"id": workflow_id, "name": body.name}


@workflow_router.get("/saved")
async def list_saved_workflows(current_user: dict = Depends(get_current_user)):
    from zeropark_core.models_db import SavedWorkflow

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(SavedWorkflow).order_by(SavedWorkflow.updated_at.desc()).limit(100)
        )
        items = rows.scalars().all()
    return {
        "workflows": [
            {"id": w.id, "name": w.name,
             "updated_at": w.updated_at.isoformat() if w.updated_at else None}
            for w in items
        ]
    }


@workflow_router.get("/saved/{workflow_id}")
async def get_saved_workflow(workflow_id: str, current_user: dict = Depends(get_current_user)):
    from zeropark_core.models_db import SavedWorkflow

    async with AsyncSessionLocal() as session:
        row = await session.get(SavedWorkflow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"id": row.id, "name": row.name, "definition": json.loads(row.definition)}


@workflow_router.delete("/saved/{workflow_id}")
async def delete_saved_workflow(workflow_id: str, current_user: dict = Depends(get_current_user)):
    from zeropark_core.models_db import SavedWorkflow

    async with AsyncSessionLocal() as session:
        row = await session.get(SavedWorkflow, workflow_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        await session.delete(row)
        await session.commit()
    return {"status": "deleted"}


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
