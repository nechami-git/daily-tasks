"""Tool JSON schemas, dispatch, and is_error results."""
from shared.registry import TOOLS, run_tool
from shared.storage import ToolError

from .log import say

FILE = "tools.py"


def schemas() -> list[dict]:
    """Tool definitions for the API. Same order every call, so the cache prefix stays stable."""
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in TOOLS]


def dispatch(tool_uses: list) -> list[dict]:
    """Run every tool_use block; return all tool_result blocks (sent back in ONE user message)."""
    results = []
    for block in tool_uses:
        try:
            out, is_error = run_tool(block.name, dict(block.input)), False
        except ToolError as e:
            out, is_error = str(e), True  # the model sees the message and can fix its call
        except Exception as e:  # a bug in a tool must not kill the loop
            out, is_error = f"internal error in {block.name}: {type(e).__name__}", True
        say(FILE, f"{block.name}({_short(block.input)}) -> "
                  f"{'ERROR ' if is_error else ''}{out.splitlines()[0] if out else ''}")
        result = {"type": "tool_result", "tool_use_id": block.id, "content": out}
        if is_error:
            result["is_error"] = True
        results.append(result)
    return results


def _short(args: dict) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= 80 else text[:77] + "..."
