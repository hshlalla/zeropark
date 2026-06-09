from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class WorkflowNode(BaseModel):
    id: str
    type: str = Field(description="Node type: 'llm', 'python', 'tool', 'input', 'output'")
    data: Dict[str, Any] = Field(default_factory=dict, description="Configuration or prompt templates")

class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str

class WorkflowDefinition(BaseModel):
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
