import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
import mcp.types as types
from mcp.server.stdio import stdio_server

from zeropark_core.models import TaskRequest
from zeropark_core.capabilities import Capability
from zeropark_engines.loader import build_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zeropark_mcp")

# Build the registry once globally
registry = build_registry()

# Initialize the MCP Server
app = Server("zeropark-mcp")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Expose zeropark engines as MCP tools."""
    return [
        types.Tool(
            name="zeropark_research",
            description="Deep research engine. Use this to search the web and generate a cited report on any topic.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The research query or topic"}
                },
                "required": ["prompt"]
            }
        ),
        types.Tool(
            name="zeropark_super_agent",
            description="Super Agent ReAct loop. Use this for complex tasks requiring python code execution or long-horizon planning.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The complex task description"}
                },
                "required": ["prompt"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle incoming tool calls from MCP clients."""
    prompt = arguments.get("prompt", "")
    
    if name == "zeropark_research":
        providers = registry.for_capability(Capability.RESEARCH)
        if not providers:
            return [types.TextContent(type="text", text="Error: Research engine not configured.")]
        
        provider = providers[0]
        request = TaskRequest(prompt=prompt, capability=Capability.RESEARCH)
        result = await provider.execute(request, "mcp_task")
        
        # Extract markdown report
        if result.artifacts:
            content = result.artifacts[0].inline or f"Result saved at {result.artifacts[0].uri}"
            return [types.TextContent(type="text", text=content)]
        return [types.TextContent(type="text", text="Task completed but no artifact returned.")]
        
    elif name == "zeropark_super_agent":
        providers = registry.for_capability(Capability.SUPER_AGENT)
        if not providers:
            return [types.TextContent(type="text", text="Error: Super Agent engine not configured.")]
        
        provider = providers[0]
        request = TaskRequest(prompt=prompt, capability=Capability.SUPER_AGENT)
        result = await provider.execute(request, "mcp_agent_task")
        
        if result.artifacts:
            content = result.artifacts[0].inline or f"Result saved at {result.artifacts[0].uri}"
            return [types.TextContent(type="text", text=content)]
        return [types.TextContent(type="text", text="Task completed but no artifact returned.")]
        
    raise ValueError(f"Unknown tool: {name}")


def main():
    """Run the stdio MCP server."""
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )

    asyncio.run(run())

if __name__ == "__main__":
    main()
