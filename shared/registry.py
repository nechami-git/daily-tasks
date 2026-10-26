"""Single source of truth for the tools: name, description, JSON schema, function.

API/harness/tools.py and SDK/tools.py both build their tool lists from TOOLS,
so the two versions expose exactly the same tools to the model.
"""
from .preferences import get_preferences, save_preference
from .storage import ToolError
from .tasks import PRIORITIES, STATUSES, add_task, complete_task, list_tasks
from .jewish_calendar import get_jewish_calendar

DATE = {"type": "string", "description": "YYYY-MM-DD, 'today' or 'tomorrow'"}

TOOLS = [
    {"name": "add_task",
     "description": "Add a task. Categories: study, fitness, home, personal (a new one is created if needed).",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "category": {"type": "string"},
         "date": DATE,
         "time": {"type": "string", "description": "start time HH:MM (24h), optional"},
         "duration_min": {"type": "integer", "description": "estimated minutes, default 30"},
         "priority": {"type": "string", "enum": PRIORITIES}},
         "required": ["title", "category"]},
     "fn": add_task},
    {"name": "list_tasks",
     "description": "List tasks, one line each, filtered by date, category and/or status.",
     "input_schema": {"type": "object", "properties": {
         "date": DATE,
         "category": {"type": "string"},
         "status": {"type": "string", "enum": STATUSES}}},
     "fn": list_tasks},
    {"name": "complete_task",
     "description": "Mark a task as done by its id.",
     "input_schema": {"type": "object", "properties": {
         "task_id": {"type": "integer"}},
         "required": ["task_id"]},
     "fn": complete_task},
    {"name": "get_jewish_calendar",
     "description": "Shabbat and Jewish holidays for a date or range (max 31 days), with "
                    "candle-lighting and havdalah times in Jerusalem. Lists only special days.",
     "input_schema": {"type": "object", "properties": {
         "start": DATE,
         "end": {"type": "string", "description": "YYYY-MM-DD, optional (default: start)"}},
         "required": ["start"]},
     "fn": get_jewish_calendar},
    {"name": "save_preference",
     "description": "Remember a lasting user preference or decision across sessions.",
     "input_schema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "short rule, e.g. 'works out in the morning'"},
         "category": {"type": "string", "description": "task category it applies to, or 'general'"}},
         "required": ["text"]},
     "fn": save_preference},
    {"name": "get_preferences",
     "description": "Look up saved preferences, optionally by category or keyword.",
     "input_schema": {"type": "object", "properties": {
         "category": {"type": "string"},
         "query": {"type": "string"}}},
     "fn": get_preferences},
]

BY_NAME = {t["name"]: t for t in TOOLS}


def run_tool(name: str, args: dict) -> str:
    """Run a tool by name. Raises ToolError on unknown tool or bad arguments."""
    tool = BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"unknown tool '{name}'")
    try:
        return tool["fn"](**args)
    except TypeError as e:  # missing / unexpected argument names
        raise ToolError(f"bad arguments for {name}: {e}")
