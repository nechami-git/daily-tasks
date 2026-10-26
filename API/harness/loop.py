"""Agent loop: call the model while stop_reason == 'tool_use'."""
from . import caching, tools
from .log import say

FILE = "loop.py"
MAX_ROUNDS = 10  # safety stop against a model that keeps calling tools forever


def run(client, *, model: str, effort: str, system: list[dict], history, stats) -> str:
    """Run model calls until the model stops asking for tools. Returns the final text."""
    tool_defs = tools.schemas()
    for round_no in range(1, MAX_ROUNDS + 1):
        sys_blocks, messages = caching.apply(system, history.messages)
        say(FILE, f"model call {round_no}")
        response = client.messages.create(
            model=model, max_tokens=16000, system=sys_blocks, tools=tool_defs,
            messages=messages, thinking={"type": "adaptive"},
            output_config={"effort": effort})
        stats.add_usage(response.usage, label=f"call {round_no}")
        # Keep the full content (thinking + text + tool_use) exactly as returned.
        history.append("assistant", response.content)

        if response.stop_reason != "tool_use":
            say(FILE, f"stop_reason={response.stop_reason}, done")
            if response.stop_reason == "refusal":
                return "(the model declined this request)"
            return "".join(b.text for b in response.content if b.type == "text").strip()

        uses = [b for b in response.content if b.type == "tool_use"]
        stats.tools += [b.name for b in uses]
        say(FILE, f"stop_reason=tool_use: {len(uses)} tool call(s)")
        # All results of this round go back together in ONE user message.
        history.append("user", tools.dispatch(uses))

    say(FILE, f"hit MAX_ROUNDS={MAX_ROUNDS}, stopping")
    return "(stopped: too many tool rounds)"
