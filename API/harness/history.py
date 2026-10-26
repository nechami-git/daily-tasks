"""Conversation history persisted to disk, append-only.

One JSONL file per session in <data>/sessions/<id>.jsonl. Each line is either
  {"kind": "message", "message": {...}}   a user or assistant message, exactly as sent
  {"kind": "compaction", "summary": "..."} everything before this line was summarized
Lines are never edited or deleted. Append-only also matters to the API: thinking blocks
are bound to the exact prefix that produced them, and an unchanged prefix keeps the cache hot.
"""
import json
import uuid
from pathlib import Path

from shared import storage

from .log import say

FILE = "history.py"


def _to_dict(block) -> dict:
    # SDK blocks (from a response) -> plain dicts we can write to disk and send back unchanged.
    return block if isinstance(block, dict) else block.to_dict(exclude_none=True)


class History:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        folder = storage.data_dir() / "sessions"
        folder.mkdir(exist_ok=True)
        self.path: Path = folder / f"{self.session_id}.jsonl"
        self.messages: list[dict] = []  # what the model sees (after the last compaction)
        if self.path.exists():
            self._load()
        else:
            say(FILE, f"new session {self.session_id}")

    def _load(self) -> None:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            entry = json.loads(line)
            if entry["kind"] == "compaction":
                self.messages = []  # the summary travels inside the next user message
            else:
                self.messages.append(entry["message"])
        say(FILE, f"resumed session {self.session_id}: {len(lines)} lines, "
                  f"{len(self.messages)} live messages")

    def _write(self, entry: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def append(self, role: str, content) -> None:
        if not isinstance(content, str):
            content = [_to_dict(b) for b in content]
        msg = {"role": role, "content": content}
        self.messages.append(msg)
        self._write({"kind": "message", "message": msg})
        say(FILE, f"appended {role} message (#{len(self.messages)})")

    def mark_compaction(self, summary: str) -> None:
        self._write({"kind": "compaction", "summary": summary})
        self.messages = []
        say(FILE, "compaction marker written; live history cleared")
