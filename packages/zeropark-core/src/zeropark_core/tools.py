import abc
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

class ToolParameter(BaseModel):
    name: str
    type: str # e.g. "string", "integer"
    description: str
    required: bool = True

class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter] = Field(default_factory=list)

class BaseTool(abc.ABC):
    """Abstract interface for a tool/skill that an agent can execute."""
    
    @abc.abstractproperty
    def spec(self) -> ToolSpec:
        pass

    @abc.abstractmethod
    def execute(self, **kwargs) -> Any:
        pass

class ToolRegistry:
    """Registry to hold and invoke tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        
    def register(self, tool: BaseTool):
        self._tools[tool.spec.name] = tool
        
    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)
        
    def get_all_specs(self) -> List[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]
        
    def execute_tool(self, name: str, **kwargs) -> Any:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool {name} not found in registry.")
        return tool.execute(**kwargs)
