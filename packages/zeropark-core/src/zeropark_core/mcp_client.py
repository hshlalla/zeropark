import json
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClientManager:
    """Manages connections to external MCP servers."""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.servers_config = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        
        self._load_config()
        
    def _load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.servers_config = data.get("mcpServers", {})
        except Exception as e:
            print(f"Error loading MCP config: {e}")

    async def connect_all(self):
        """Connects to all configured MCP servers."""
        for name, config in self.servers_config.items():
            if "command" in config:
                # stdio based
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env", None)
                )
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                read, write = stdio_transport
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions[name] = session

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """Fetch all tools from all connected servers."""
        all_tools = []
        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    # Inject server_name internally so we know where to route
                    tool_meta = {
                        "name": f"{server_name}__{tool.name}",
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                        "_server": server_name,
                        "_original_name": tool.name
                    }
                    all_tools.append(tool_meta)
            except Exception as e:
                print(f"Error getting tools from {server_name}: {e}")
        return all_tools

    async def execute_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """Execute a specific tool on a specific server."""
        if server_name not in self.sessions:
            return f"Error: Server {server_name} not connected."
        
        session = self.sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments)
            if not result.content:
                return "Tool executed but returned no content."
            
            # Combine content texts
            texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
            return "\n".join(texts)
        except Exception as e:
            return f"Error executing tool: {e}"

    async def close(self):
        """Close all connections."""
        await self.exit_stack.aclose()
