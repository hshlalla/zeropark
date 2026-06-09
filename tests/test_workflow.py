import asyncio
import json
from zeropark_core.models_workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge
from zeropark_engines.workflow import DAGOrchestrator

async def main():
    # 1. Define nodes simulating a React Flow frontend payload
    nodes = [
        WorkflowNode(id="node_input", type="input", data={"user_query": "Calculate 10+20 and explain the meaning of that number."}),
        WorkflowNode(id="node_python", type="python", data={"code": "x = 10; y = 20; print(f'The sum is {x+y}')"}),
        WorkflowNode(id="node_llm", type="llm", data={"prompt": "User query: {{user_query}}\nPython Tool Output: {{node_python_result}}\nBased on the python output, write a fun 1-sentence explanation of that number."})
    ]
    
    # 2. Define edges (Dependencies)
    edges = [
        WorkflowEdge(id="e1", source="node_input", target="node_python"),
        WorkflowEdge(id="e2", source="node_python", target="node_llm")
    ]
    
    workflow_def = WorkflowDefinition(nodes=nodes, edges=edges)
    
    print("Initializing DAG Orchestrator...")
    orchestrator = DAGOrchestrator(workflow_def)
    
    print("\nExecuting Pipeline...")
    final_context = await orchestrator.execute({})
    
    print("\n--- Execution Finished ---")
    print("Context Memory Dump:")
    print(json.dumps(final_context, indent=2, ensure_ascii=False))
    print(f"\nFinal LLM Output:\n{final_context.get('node_llm_result')}")

if __name__ == "__main__":
    asyncio.run(main())
