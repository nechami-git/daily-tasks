"""Places cache_control breakpoints.

The API caches by prefix in the order tools -> system -> messages.
Breakpoint 1: last system block. Caches tools + system prompt (identical every request).
Breakpoint 2: last block of the last message. Caches the whole conversation so far,
so the next request (next tool round or next turn) reads it from the cache.
Markers are added to a copy at request time and never written to history;
moving a marker is not an edit of the conversation.
"""
import copy

from .log import say

FILE = "caching.py"
MARK = {"type": "ephemeral"}  # 5-minute TTL; on Opus 5.5 write = 1.25x input, read = 0.05x


def apply(system: list[dict], messages: list[dict]) -> tuple[list[dict], list[dict]]:
    system = copy.deepcopy(system)
    messages = copy.deepcopy(messages)
    system[-1]["cache_control"] = MARK

    last = messages[-1]
    if isinstance(last["content"], str):
        last["content"] = [{"type": "text", "text": last["content"]}]
    last["content"][-1]["cache_control"] = MARK
    say(FILE, f"breakpoints: system, message #{len(messages)}")
    return system, messages
