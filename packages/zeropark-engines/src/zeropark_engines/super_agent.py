from __future__ import annotations

import json
from typing import Any

from zeropark_core import Artifact, Capability, TaskRequest, TaskResult
from zeropark_core.llm import LLMClient
from zeropark_engines.native import NativeEngine
from zeropark_engines.sandbox import PythonSandbox


class SuperAgentEngine(NativeEngine):
    """Deep-think ReAct loop engine for complex task resolution."""

    id = "zeropark_engines.super_agent"
    name = "Super Agent Engine"
    capabilities = {Capability.WORKFLOW, Capability.SUPER_AGENT}

    def __init__(self, output_dir: str, **kwargs: Any) -> None:
        self.output_dir = output_dir
        self.sandbox = PythonSandbox()
        # You would typically inject a global LLM client or ToolRegistry here.
        # For simplicity in this implementation, we initialize a local client.
        self.llm = LLMClient()

    async def execute(self, request: TaskRequest, task_id: str) -> TaskResult:
        """Runs the ReAct (Reasoning + Acting) loop."""
        
        system_prompt = """You are a highly capable AI Super Agent.
You operate in a loop of Thought, Action, PAUSE, Observation.
At the end of the loop you output an Answer.

Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you.
You must return the Action in valid JSON format.

Your available actions are:
1. python_exec: Runs python code and returns the output. Use this for math or data manipulation.
   Payload: {"action": "python_exec", "code": "<python code string>"}
2. search: Searches the web for information (Mocked for now).
   Payload: {"action": "search", "query": "<search query>"}

When you have a final answer, output:
Final Answer: <the answer text>
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.prompt}
        ]

        max_iterations = 5
        final_answer = ""
        
        for i in range(max_iterations):
            # 1. Thought / Action phase
            response = await self.llm.generate(messages)
            content = response.content or ""
            
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
                        # Mock search
                        action_result = f"Observation: Found results for '{query}' - (Simulated data)."
                    else:
                        action_result = f"Observation: Unknown action '{action_type}'"
                except json.JSONDecodeError:
                    action_result = "Observation: Failed to parse action JSON."
            
            # 2. Observation phase
            messages.append({"role": "user", "content": action_result})
            
        if not final_answer:
            final_answer = "Max iterations reached without a Final Answer."

        artifact = Artifact(
            id=f"{task_id}_agent_result",
            kind="markdown",
            title="Super Agent Report",
            mime_type="text/markdown",
            inline=final_answer
        )
        
        return TaskResult(
            task_id=task_id,
            status="completed",
            capability=Capability.WORKFLOW.value,  # or mapped to a new capability SUPER_AGENT
            artifacts=[artifact]
        )
