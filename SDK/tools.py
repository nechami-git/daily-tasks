"""Wraps shared/ tools with @tool and create_sdk_mcp_server."""
import asyncio

from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.registry import TOOLS, run_tool
from shared.storage import ToolError

SERVER = "tasks"
# Claude Code exposes MCP tools as mcp__<server>__<tool>.
TOOL_NAMES = [f"mcp__{SERVER}__{t['name']}" for t in TOOLS]


def _wrap(spec: dict):  # replaces: tools.py (schemas, dispatch, is_error)
    @tool(spec["name"], spec["description"], spec["input_schema"])
    async def handler(args: dict) -> dict:
        try:
            out = await asyncio.to_thread(run_tool, spec["name"], args)
            return {"content": [{"type": "text", "text": out}]}
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "is_error": True}

    return handler


def build_server():  # replaces: tools.py (registration)
    return create_sdk_mcp_server(SERVER, tools=[_wrap(t) for t in TOOLS])
