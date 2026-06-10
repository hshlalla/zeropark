from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from zeropark_core.database import AsyncSessionLocal
from zeropark_core.models_db import WorkflowRun
from zeropark_gateway.auth import get_current_user
from typing import Any
import json

observability_router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

@observability_router.get("/runs")
async def list_runs(limit: int = 50, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Get the execution history of workflows (Observability dashboard)."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(WorkflowRun)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
        runs = []
        for r in rows.scalars():
            runs.append({
                "id": r.id,
                "workflow_name": r.workflow_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None
            })
        return {"runs": runs}

@observability_router.get("/runs/{run_id}")
async def get_run_details(run_id: str, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Get node-by-node execution details (NodeRun) for a specific run."""
    async with AsyncSessionLocal() as session:
        run = await session.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
            
        return {
            "id": run.id,
            "workflow_name": run.workflow_name,
            "status": run.status,
            "duration_ms": run.duration_ms,
            "node_runs": json.loads(run.node_runs) if run.node_runs else []
        }
