"""Summarizes the conversation once it passes a size threshold.

"Simple compaction": between turns (never inside a tool round), if the last prompt
was larger than the threshold, summarize the WHOLE live history into one text,
write a compaction marker to history, and start the next request from just
summary + new user turn. No earlier turns or thinking blocks are replayed, so
nothing sent afterwards is tied to the old transcript.
"""
from .log import say

FILE = "compaction.py"

SUMMARY_PROMPT = """\
Summarize the conversation above so it can continue without it. Keep:
- decisions the user made and preferences they stated (and whether they were saved),
- task ids that were added, changed or completed in this conversation,
- open questions or conflicts that are still waiting for the user.
Plain lines, no preamble, at most 150 words."""


def _as_text(messages: list[dict]) -> str:
    """Flatten history to plain text for the summarizer (thinking blocks are left out)."""
    lines = []
    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in blocks:
            if b["type"] == "text":
                lines.append(f"{m['role']}: {b['text']}")
            elif b["type"] == "tool_use":
                lines.append(f"assistant called {b['name']}({b['input']})")
            elif b["type"] == "tool_result":
                lines.append(f"tool result: {b['content']}")
    return "\n".join(lines)


def needs_compaction(last_context_tokens: int, threshold: int) -> bool:
    if last_context_tokens > threshold:
        say(FILE, f"context {last_context_tokens} > threshold {threshold}: compacting")
        return True
    return False


def summarize(client, model: str, messages: list[dict], stats) -> str:
    response = client.messages.create(
        model=model, max_tokens=2000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": _as_text(messages) + "\n\n" + SUMMARY_PROMPT}])
    stats.add_usage(response.usage, label="compaction call")
    summary = "".join(b.text for b in response.content if b.type == "text").strip()
    say(FILE, f"{len(messages)} messages -> summary of {len(summary)} chars")
    return summary
