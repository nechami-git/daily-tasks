"""Where long-term memory is stored and how it is retrieved.

Storage: shared/preferences.py writes <data>/preferences.json, so it survives across
sessions and both versions read the same format. The model writes to it with the
save_preference tool. Retrieval here is for context.py: given the user's message,
return only the preferences that are relevant to it, not all of them.
"""
from shared.preferences import find_preferences

from .log import say

FILE = "memory.py"

# Words (English + Hebrew) that point to a category. Cheap keyword match, no model call.
KEYWORDS = {
    "fitness": ["workout", "work out", "gym", "run", "exercise", "training", "yoga", "swim",
                "אימון", "להתאמן", "ריצה", "כושר", "חדר כושר", "יוגה"],
    "study": ["study", "exam", "homework", "course", "lecture", "assignment",
              "ללמוד", "לימוד", "מבחן", "שיעורי בית", "קורס", "הרצאה", "מטלה"],
    "home": ["clean", "laundry", "dishes", "groceries", "cook",
             "לנקות", "ניקיון", "כביסה", "כלים", "קניות", "לבשל"],
    "personal": ["call", "doctor", "birthday", "friend", "family",
                 "להתקשר", "רופא", "יום הולדת", "חבר", "משפחה"],
}


def categories_in(text: str) -> list[str]:
    low = text.lower()
    return [cat for cat, words in KEYWORDS.items() if any(w in low for w in words)]


def relevant(user_text: str) -> list[dict]:
    """General preferences always; category preferences only when the message touches that category."""
    cats = categories_in(user_text)
    everything = find_preferences()
    prefs = [p for p in everything if p["category"] == "general" or p["category"] in cats]
    say(FILE, f"categories {cats or '-'}: {len(prefs)} of {len(everything)} preferences are relevant")
    return prefs
