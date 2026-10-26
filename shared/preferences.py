"""Memory tools: save_preference, get_preferences (persisted in preferences.json)."""
from datetime import datetime

from . import storage
from .storage import ToolError

EMPTY = {"next_id": 1, "preferences": []}


def save_preference(text: str, category: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        raise ToolError("text is required")
    category = category.lower() if category else "general"
    data = storage.load("preferences", EMPTY)
    for p in data["preferences"]:
        if p["text"].lower() == text.lower():  # don't store the same rule twice
            return f"already saved pref #{p['id']}"
    pref = {"id": data["next_id"], "text": text, "category": category,
            "saved_at": datetime.now().isoformat(timespec="seconds")}
    data["preferences"].append(pref)
    data["next_id"] += 1
    storage.save("preferences", data)
    storage.log_event("preference_saved", pref_id=pref["id"])
    return f"saved pref #{pref['id']} [{category}] {text}"


def find_preferences(category: str | None = None, query: str | None = None) -> list[dict]:
    """Shared by the tool and by harness context code. 'general' prefs always match a category."""
    prefs = storage.load("preferences", EMPTY)["preferences"]
    if category:
        prefs = [p for p in prefs if p["category"] in (category.lower(), "general")]
    if query:
        prefs = [p for p in prefs if query.lower() in p["text"].lower()]
    return prefs


def get_preferences(category: str | None = None, query: str | None = None) -> str:
    prefs = find_preferences(category, query)
    if not prefs:
        return "no preferences"
    return "\n".join(f"#{p['id']} [{p['category']}] {p['text']}" for p in prefs)
