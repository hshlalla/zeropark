import networkx as nx
from typing import Dict, Any

import os
from zeropark_core.models_workflow import WorkflowDefinition, WorkflowNode
from zeropark_core.llm import OpenAILLMClient, ChatMessage
from zeropark_engines.sandbox import PythonSandbox, DockerSandbox

class DAGOrchestrator:
    """Executes a directed acyclic graph of workflow nodes."""
    
    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self.graph = nx.DiGraph()
        self.context: Dict[str, Any] = {}
        
        # Build the graph
        for node in self.definition.nodes:
            self.graph.add_node(node.id, data=node)
            
        for edge in self.definition.edges:
            self.graph.add_edge(edge.source, edge.target)
            
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError("Workflow contains cycles (infinite loops). Must be a DAG.")
            
        # Initialize secure sandbox environment
        try:
            self.sandbox = DockerSandbox(allow_network=True)
            print("[Workflow] Secured DockerSandbox initialized.")
        except Exception as e:
            print(f"[Workflow] Docker daemon not found, falling back to local PythonSandbox. Reason: {e}")
            self.sandbox = PythonSandbox()
        api_key = os.environ.get("OPENAI_API_KEY", "dummy_key")
        self.llm = OpenAILLMClient(api_key=api_key)

    async def execute(self, initial_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the workflow following topological sort."""
        self.context.update(initial_inputs)
        
        # Get execution order
        execution_order = list(nx.topological_sort(self.graph))
        
        for node_id in execution_order:
            node_obj: WorkflowNode = self.graph.nodes[node_id]['data']
            await self._execute_node(node_obj)
            
        return self.context

    async def _execute_node(self, node: WorkflowNode):
        node_type = node.type
        data = node.data
        
        print(f"[Workflow] Executing node: {node.id} (Type: {node_type})")
        
        if node_type == "input":
            # Just pass values to context
            for k, v in data.items():
                self.context[k] = v
                
        elif node_type == "python":
            code_template = data.get("code", "")
            # Inject context variables natively by executing code
            # For simplicity, we just format strings, but in real scenarios,
            # we inject the context dict into locals.
            
            # Simple template replacement
            for k, v in self.context.items():
                code_template = code_template.replace(f"{{{{{k}}}}}", str(v))
                
            result = self.sandbox.execute(code_template)
            self.context[f"{node.id}_result"] = result.strip()
            
        elif node_type == "llm":
            prompt_template = data.get("prompt", "")
            for k, v in self.context.items():
                prompt_template = prompt_template.replace(f"{{{{{k}}}}}", str(v))
                
            # Execute LLM (chat_completion is synchronous in this mock setup)
            response = self.llm.chat_completion(
                messages=[ChatMessage(role="user", content=prompt_template)],
                model="gpt-4o"
            )
            self.context[f"{node.id}_result"] = response.content
            
        elif node_type == "crawl":
            from zeropark_engines.crawl import LocalCrawlEngine
            from zeropark_core.models import TaskRequest
            
            url_template = data.get("url", "")
            for k, v in self.context.items():
                url_template = url_template.replace(f"{{{{{k}}}}}", str(v))
                
            engine = LocalCrawlEngine()
            task = TaskRequest(mode="crawl", prompt=url_template, params={"url": url_template})
            
            try:
                result = await engine.cap_crawl(task, task_id=node.id)
                self.context[f"{node.id}_result"] = result.artifacts[0].inline if result.artifacts else "Crawl failed"
            except Exception as e:
                self.context[f"{node.id}_result"] = f"Crawl Error: {e}"

        elif node_type == "search":
            from zeropark_engines.search import WebSearchEngine
            from zeropark_core.models import TaskRequest
            
            query_template = data.get("query", "")
            for k, v in self.context.items():
                query_template = query_template.replace(f"{{{{{k}}}}}", str(v))
                
            # For demonstration, we use a mock/public permissive endpoint or just echo if no key
            # In a real scenario, base_url and api_key would be injected from settings
            engine = WebSearchEngine(base_url="https://dummyjson.com/products/search", query_param="q", results_key="products")
            task = TaskRequest(mode="search", prompt=query_template)
            
            try:
                result = await engine.cap_search(task, task_id=node.id)
                self.context[f"{node.id}_result"] = result.artifacts[0].inline if result.artifacts else "Search failed"
            except Exception as e:
                self.context[f"{node.id}_result"] = f"Search Error: {e}"
                
        elif node_type == "slides":
            self.context[f"{node.id}_result"] = "Slides Engine Triggered: (Artifact generated in artifact store)"

        elif node_type == "output":
            # Output node aggregates or logs results
            pass
        else:
            print(f"Warning: Unknown node type '{node_type}'")
