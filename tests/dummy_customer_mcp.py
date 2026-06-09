import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
import mcp.types as types
from mcp.server.stdio import stdio_server

logging.basicConfig(level=logging.INFO)

app = Server("dummy-customer-mcp")

# Mock database
EMPLOYEE_DB = {
    "김철수": {"department": "AI연구소", "role": "수석연구원", "email": "chulsoo@customer.com"},
    "이영희": {"department": "영업팀", "role": "팀장", "email": "younghee@customer.com"}
}

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_employee_data",
            description="Search the company ERP for employee details by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the employee"}
                },
                "required": ["name"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "search_employee_data":
        emp_name = arguments.get("name", "")
        if emp_name in EMPLOYEE_DB:
            result = json.dumps(EMPLOYEE_DB[emp_name], ensure_ascii=False)
            return [types.TextContent(type="text", text=f"Employee data found: {result}")]
        else:
            return [types.TextContent(type="text", text=f"Employee {emp_name} not found in ERP.")]
    raise ValueError(f"Unknown tool: {name}")

def main():
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    asyncio.run(run())

if __name__ == "__main__":
    main()
