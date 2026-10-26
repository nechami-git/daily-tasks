"""Decides what goes into the context on each turn.

Stable part (system prompt + tools) never changes during a session -> cacheable.
Per-turn part is a small <context> block at the start of the new user message:
today's tasks and only the preferences relevant to this message.
It is appended once and never edited later (history stays append-only).
Anything else (other days, other categories) the model fetches with tools.
"""
from shared import storage
from shared.prompt import system_prompt
from shared.tasks import list_tasks

from . import memory
from .log import say

FILE = "context.py"


def system_blocks() -> list[dict]:
    # The date lives in the system prompt (same line as in SDK/), fixed for the session.
    return [{"type": "text", "text": system_prompt("api")}]


def build_user_content(user_text: str, summary: str | None = None) -> list[dict]:
    tasks = list_tasks(date=storage.today().isoformat())
    prefs = memory.relevant(user_text)
    pref_lines = "\n".join(f"#{p['id']} [{p['category']}] {p['text']}" for p in prefs) or "none"
    ctx = (f"<context>\ntoday's tasks:\n{tasks}\n"
           f"relevant preferences:\n{pref_lines}\n</context>")

    content = []
    if summary:  # first turn after compaction: the summary replaces the old conversation
        content.append({"type": "text", "text": f"<summary of earlier conversation>\n"
                                                 f"{summary}\n</summary of earlier conversation>"})
    content.append({"type": "text", "text": ctx})
    content.append({"type": "text", "text": user_text})
    n_tasks = 0 if tasks == "no tasks" else len(tasks.splitlines())
    say(FILE, f"turn context: {n_tasks} tasks today, {len(prefs)} prefs, ~{len(ctx) // 4} tokens"
              + (", + compaction summary" if summary else ""))
    return content
