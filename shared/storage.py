"""JSON file storage for the domain data (tasks, preferences, history)."""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).parent / "data"


class ToolError(ValueError):
    """Bad tool input or state. Harnesses send it back to the model as is_error."""


def data_dir() -> Path:
    # Read on every call so a run (or a test) can point at its own clean folder.
    d = Path(os.environ.get("DAILY_TASKS_DATA_DIR", DEFAULT_DATA_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(name: str, default: dict) -> dict:
    path = data_dir() / f"{name}.json"
    if not path.exists():
        return json.loads(json.dumps(default))  # fresh copy of the default
    return json.loads(path.read_text(encoding="utf-8"))


def save(name: str, obj: dict) -> None:
    # Write to a temp file first so a crash never leaves half a JSON file.
    path = data_dir() / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def today() -> date:
    # DAILY_TASKS_TODAY pins "today" for tests and reproducible scenarios.
    fixed = os.environ.get("DAILY_TASKS_TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()


def resolve_date(value: str | None) -> str:
    """Accept YYYY-MM-DD, 'today' or 'tomorrow'; return YYYY-MM-DD."""
    if value is None or value == "today":
        return today().isoformat()
    if value == "tomorrow":
        return (today() + timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolError(f"bad date '{value}': use YYYY-MM-DD, 'today' or 'tomorrow'")


def check_time(value: str) -> str:
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ToolError(f"bad time '{value}': use HH:MM (24h)")


def log_event(kind: str, **fields) -> None:
    """Append one line to history.json (a domain log of what happened)."""
    hist = load("history", {"events": []})
    hist["events"].append({"at": datetime.now().isoformat(timespec="seconds"),
                           "kind": kind, **fields})
    save("history", hist)
