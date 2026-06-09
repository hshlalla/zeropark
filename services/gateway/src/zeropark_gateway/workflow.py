from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

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
    # ignoring id, sourceHandle, etc.

class WorkflowRunRequest(BaseModel):
    nodes: List[ReactFlowNode]
    edges: List[ReactFlowEdge]
    initial_inputs: Dict[str, Any] = {}

@workflow_router.post("/run")
async def run_workflow(request: WorkflowRunRequest):
    try:
        # Convert React Flow schema to Engine WorkflowDefinition schema
        workflow_nodes = []
        for n in request.nodes:
            # Our frontend stores the actual engine type inside data.type (e.g. 'llm', 'sandbox')
            node_type = n.data.get("type", "unknown")
            # Map frontend types to backend types if necessary
            if node_type == "sandbox":
                node_type = "python" # engine uses 'python' for sandbox
                
            workflow_nodes.append(WorkflowNode(
                id=n.id,
                type=node_type,
                data=n.data
            ))
            
        workflow_edges = [
            WorkflowEdge(source=e.source, target=e.target)
            for e in request.edges
        ]
        
        definition = WorkflowDefinition(
            name="FrontendTriggeredWorkflow",
            nodes=workflow_nodes,
            edges=workflow_edges
        )
        
        orchestrator = DAGOrchestrator(definition)
        results = await orchestrator.execute(request.initial_inputs)
        
        return {
            "status": "success",
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
