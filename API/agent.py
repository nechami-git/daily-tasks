"""Wires the harness modules together into one agent instance."""
import os

from API.harness import compaction, context, loop
from API.harness.history import History
from API.harness.log import say
from API.harness.tokens import TurnStats

FILE = "agent.py"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
COMPACT_THRESHOLD = 30_000  # prompt tokens; low on purpose so it is visible in a short demo


def make_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set. Set it in the terminal, never in code.")
    import anthropic  # imported here so offline tests never pay for it

    return anthropic.Anthropic()  # reads the key from the environment


class Agent:
    def __init__(self, client=None, session_id: str | None = None,
                 compact_threshold: int = COMPACT_THRESHOLD):
        self.client = client or make_client()
        self.history = History(session_id)
        self.system = context.system_blocks()  # frozen for the whole session
        self.compact_threshold = compact_threshold
        self.last_context = 0
        say(FILE, f"agent ready: model={MODEL} effort={EFFORT} session={self.history.session_id}")

    def ask(self, user_text: str) -> tuple[str, dict]:
        """One user turn. Returns (reply text, per-turn stats)."""
        stats = TurnStats()
        summary = None
        if self.history.messages and compaction.needs_compaction(self.last_context,
                                                                 self.compact_threshold):
            summary = compaction.summarize(self.client, MODEL, self.history.messages, stats)
            self.history.mark_compaction(summary)

        self.history.append("user", context.build_user_content(user_text, summary))
        reply = loop.run(self.client, model=MODEL, effort=EFFORT, system=self.system,
                         history=self.history, stats=stats)
        self.last_context = stats.last_context
        return reply, stats.finish()
