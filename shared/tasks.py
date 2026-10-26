"""Task tools: add_task, list_tasks, complete_task."""
from . import storage
from .storage import ToolError

DEFAULT_CATEGORIES = ["study", "fitness", "home", "personal"]
PRIORITIES = ["high", "medium", "low"]
STATUSES = ["todo", "done"]
EMPTY = {"next_id": 1, "categories": DEFAULT_CATEGORIES, "tasks": []}


def _load() -> dict:
    return storage.load("tasks", EMPTY)


def format_task(t: dict) -> str:
    """One compact line per task, e.g. '#3 2026-10-25 07:00 60m fitness high todo | Run 5k'."""
    return (f"#{t['id']} {t['date']} {t['time'] or '--:--'} {t['duration_min']}m "
            f"{t['category']} {t['priority']} {t['status']} | {t['title']}")


def add_task(title: str, category: str, date: str = "today", time: str | None = None,
             duration_min: int = 30, priority: str = "medium") -> str:
    title = (title or "").strip()
    if not title:
        raise ToolError("title is required")
    category = (category or "").strip().lower()
    if not category:
        raise ToolError("category is required")
    if priority not in PRIORITIES:
        raise ToolError(f"priority must be one of {PRIORITIES}")
    if not isinstance(duration_min, int) or not 1 <= duration_min <= 720:
        raise ToolError("duration_min must be an integer between 1 and 720")

    data = _load()
    note = ""
    if category not in data["categories"]:  # new categories are allowed and remembered
        data["categories"].append(category)
        note = f" (new category '{category}')"
    task = {"id": data["next_id"], "title": title, "category": category,
            "date": storage.resolve_date(date),
            "time": storage.check_time(time) if time else None,
            "duration_min": duration_min, "priority": priority, "status": "todo"}
    data["tasks"].append(task)
    data["next_id"] += 1
    storage.save("tasks", data)
    storage.log_event("task_added", task_id=task["id"])
    return "added " + format_task(task) + note


def list_tasks(date: str | None = None, category: str | None = None,
               status: str | None = None, limit: int = 20) -> str:
    if status is not None and status not in STATUSES:
        raise ToolError(f"status must be one of {STATUSES}")
    day = storage.resolve_date(date) if date else None
    cat = category.lower() if category else None

    rows = [t for t in _load()["tasks"]
            if (day is None or t["date"] == day)
            and (cat is None or t["category"] == cat)
            and (status is None or t["status"] == status)]
    rows.sort(key=lambda t: (t["date"], t["time"] or "99:99", t["id"]))
    if not rows:
        return "no tasks"
    lines = [format_task(t) for t in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more")
    return "\n".join(lines)


def complete_task(task_id: int) -> str:
    data = _load()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ToolError(f"no task #{task_id}")
    if task["status"] == "done":
        return f"already done #{task_id} {task['title']}"
    task["status"] = "done"
    storage.save("tasks", data)
    storage.log_event("task_completed", task_id=task_id)
    return f"done #{task_id} {task['title']}"
