from __future__ import annotations

import json
import time
from typing import Any

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult, ArtifactStore
from zeropark_core.llm import OpenAILLMClient, ChatMessage
from zeropark_engines.base import NativeEngine
from zeropark_engines.sandbox import PythonSandbox, DockerSandbox
from zeropark_core.mcp_client import MCPClientManager


class SuperAgentEngine(NativeEngine):
    """Deep-think ReAct loop engine for complex task resolution."""

    id = "zeropark_engines.super_agent"
    name = "Super Agent Engine"
    capabilities = {Capability.WORKFLOW, Capability.SUPER_AGENT}

    def __init__(self, store: ArtifactStore, **kwargs: Any) -> None:
        super().__init__(store, **kwargs)
        self.store = store
        
        # Use DockerSandbox for enterprise isolation
        try:
            self.sandbox = DockerSandbox()
        except Exception as e:
            print(f"Warning: Docker not available, falling back to PythonSandbox. Error: {e}")
            self.sandbox = PythonSandbox()
            
        import os
        api_key = os.environ.get("OPENAI_API_KEY", "dummy_key")
        self.llm_client = OpenAILLMClient(api_key=api_key)
        self.default_model = kwargs.get("model", "gpt-4o")
        self.default_temperature = kwargs.get("temperature", 0.0)

    async def execute(self, request: TaskRequest, task_id: str) -> TaskResult:
        """Runs the ReAct (Reasoning + Acting) loop."""
        
        # Initialize MCP Client to load external tools
        import os
        config_path = os.environ.get("MCP_SERVERS_CONFIG", "c:/Users/CNXK/Documents/Zeropark/services/gateway/src/mcp_servers.json")
        mcp_manager = MCPClientManager(config_path)
        await mcp_manager.connect_all()
        
        external_tools = await mcp_manager.get_all_tools()
        tools_desc = ""
        for idx, tool in enumerate(external_tools, start=3):
            tools_desc += f"{idx}. {tool['name']}: {tool['description']}\n"
            tools_desc += f"   Payload: {{\"action\": \"{tool['name']}\", \"arguments\": <json matching {json.dumps(tool['inputSchema'])}>}}\n"

        system_prompt = f"""You are a highly capable AI Super Agent.
You operate in a loop of Thought, Action, PAUSE, Observation.
At the end of the loop you output an Answer.

Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you.
You must return the Action in valid JSON format.

Your available internal actions are:
1. python_exec: Runs python code and returns the output. Use this for math or data manipulation.
   Payload: {{"action": "python_exec", "code": "<python code string>"}}
2. search: Searches the web for information (Mocked for now).
   Payload: {{"action": "search", "query": "<search query>"}}

Your available external (MCP) actions are:
{tools_desc}

When you have a final answer, output:
Final Answer: <the answer text>
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.prompt}
        ]

        max_iterations = 5
        final_answer = ""
        total_prompt_tokens = 0
        total_completion_tokens = 0
        
        start_time = time.time()
        
        for i in range(max_iterations):
            # 1. Thought / Action phase
            chat_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
            response = self.llm.chat_completion(chat_messages, model="gpt-4o")
            content = response.content or ""
            
            total_prompt_tokens += getattr(response, "prompt_tokens", 0)
            total_completion_tokens += getattr(response, "completion_tokens", 0)
            
            messages.append({"role": "assistant", "content": content})
            
            if "Final Answer:" in content:
                final_answer = content.split("Final Answer:", 1)[1].strip()
                break
                
            # Parse action if present
            action_result = "Observation: No valid action json found. Please format your action as JSON."
            
            # Simple heuristic to find JSON block
            if "{" in content and "}" in content:
                try:
                    start = content.find("{")
                    end = content.rfind("}") + 1
                    action_json = json.loads(content[start:end])
                    
                    action_type = action_json.get("action")
                    if action_type == "python_exec":
                        code = action_json.get("code", "")
                        action_result = f"Observation:\n{self.sandbox.execute(code)}"
                    elif action_type == "search":
                        query = action_json.get("query", "")
                        action_result = f"Observation: Found results for '{query}' - (Simulated data)."
                    elif "__" in action_type:
                        # MCP tool execution
                        server_name, tool_name = action_type.split("__", 1)
                        args = action_json.get("arguments", {})
                        mcp_result = await mcp_manager.execute_tool(server_name, tool_name, args)
                        action_result = f"Observation from {server_name}: {mcp_result}"
                    else:
                        action_result = f"Observation: Unknown action '{action_type}'"
                except json.JSONDecodeError:
                    action_result = "Observation: Failed to parse action JSON."
                except Exception as e:
                    action_result = f"Observation: Error executing action: {e}"
            
            # 2. Observation phase
            messages.append({"role": "user", "content": action_result})
            
        await mcp_manager.close()
            
        if not final_answer:
            final_answer = "Max iterations reached without a Final Answer."

        artifact = Artifact(
            id=f"{task_id}_agent_result",
            kind="markdown",
            title="Super Agent Report",
            mime_type="text/markdown",
            inline=final_answer
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return TaskResult(
            task_id=task_id,
            status="completed",
            capability=Capability.WORKFLOW.value,  # or mapped to a new capability SUPER_AGENT
            artifacts=[artifact],
            metrics={
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "iterations": i + 1,
                "latency_ms": round(latency_ms, 2)
            }
        )
