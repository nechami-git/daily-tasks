"""SIMULATED model for running the scenario without an API key. Not part of the harness.

ScriptedClient stands in for anthropic.Anthropic(): it answers each scenario request with a
fixed, hand-written sequence of tool calls and texts (modelled on what the real model did in
the SDK run), so every harness file runs for real: loop, tools (real shared/ tools, real
Hebcal), history, memory, context, compaction, caching and tokens.

The usage numbers are ESTIMATES (characters / 4), with a simple prefix-cache model driven by
the cache_control breakpoints caching.py places. They are not real token counts and must not
be compared with the SDK's real numbers.
"""
import hashlib
import json
from types import SimpleNamespace

CHARS_PER_TOKEN = 4
TOOL_PROMPT_OVERHEAD = 286  # system tokens the API adds when tools are present (pricing docs)
MIN_CACHEABLE = 512         # minimum cacheable prefix on Opus 5.5
THINKING_TOKENS = 120       # pretend each response thought this much


class Block(SimpleNamespace):
    def to_dict(self, exclude_none: bool = True) -> dict:
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def _call(name: str, args: dict) -> tuple:
    return ("tool", name, args)


def _say(text: str) -> tuple:
    return ("text", text)


# One list per scenario turn: each inner list is one model response.
# A response with tool calls ends in stop_reason=tool_use; a text-only one ends the turn.
SCRIPT = {
    "Add two study tasks for tomorrow": [
        [_call("add_task", {"title": "Submit Assignment 3 (AI Agents course)", "category": "study",
                            "date": "tomorrow", "time": "10:00", "duration_min": 120,
                            "priority": "high"}),
         _call("add_task", {"title": "Statistics exam review", "category": "study",
                            "date": "tomorrow", "time": "14:00", "duration_min": 90})],
        [_say("Added both for tomorrow (Thu 29 Oct):\n- #1 10:00-12:00 Submit Assignment 3 "
              "(AI Agents course), high priority\n- #2 14:00-15:30 Statistics exam review")],
    ],
    "Two things to remember long-term": [
        [_call("save_preference", {"text": "Workouts only in the morning, before 9:00",
                                   "category": "fitness"}),
         _call("save_preference", {"text": "No studying after 22:00", "category": "study"})],
        [_say("Saved both preferences: workouts only before 9:00, and no studying after 22:00.")],
    ],
    "Schedule 3 hours of review for the Algorithms exam": [
        [_call("get_jewish_calendar", {"start": "2026-10-30", "end": "2026-10-31"})],
        [_call("add_task", {"title": "Algorithms exam review", "category": "study",
                            "date": "2026-10-30", "time": "09:00", "duration_min": 180})],
        [_say("Booked Friday 09:00-12:00, which ends well before candle lighting at 16:11.\n"
              "Saturday is Shabbat until havdalah at 17:28, so I didn't book it. I can do "
              "Saturday night 18:00-21:00 (before your 22:00 cutoff) or Sunday. Which one?")],
    ],
    "Yes, go ahead.": [
        [_call("add_task", {"title": "Algorithms exam review (part 2)", "category": "study",
                            "date": "2026-10-31", "time": "18:00", "duration_min": 180})],
        [_say("Booked Saturday night 18:00-21:00, after havdalah and before 22:00.")],
    ],
    "I already finished tomorrow's Statistics review": [
        [_call("list_tasks", {"date": "tomorrow"})],
        [_call("complete_task", {"task_id": 2})],
        [_say("Marked #2 Statistics exam review as done.")],
    ],
    "What's planned for me tomorrow": [
        [_call("list_tasks", {"date": "tomorrow"})],
        [_say("Tomorrow (Thu 29 Oct): 10:00 Submit Assignment 3 (high priority); the 14:00 "
              "Statistics review is already done.\nPreferences: workouts only in the morning, "
              "before 9:00; no studying after 22:00.")],
    ],
    "Schedule a 30-minute home workout": [
        [_say("That conflicts with your saved preference: workouts only in the morning, before "
              "9:00. Is 20:00 a one-time exception, or should I change the preference?")],
    ],
    "It's a one-time thing": [
        [_call("add_task", {"title": "Home workout", "category": "fitness", "date": "tomorrow",
                            "time": "20:00", "duration_min": 30})],
        [_say("Booked a one-time home workout tomorrow at 20:00. Your morning preference is "
              "unchanged. Good luck with the exams!")],
    ],
}

COMPACTION_SUMMARY = (
    "- Thu 29 Oct: #1 Submit Assignment 3 10:00 (high), #2 Statistics review 14:00.\n"
    "- Saved prefs: workouts only before 9:00 (fitness); no studying after 22:00 (study).\n"
    "- Algorithms review: #3 Fri 09:00-12:00 booked; #4 Sat 18:00-21:00 booked after the user "
    "confirmed.")


def _tokens(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, sort_keys=True)) // CHARS_PER_TOKEN


def _strip_marks(obj):
    if isinstance(obj, dict):
        return {k: _strip_marks(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_marks(v) for v in obj]
    return obj


class PrefixCache:
    """Server-side prompt cache, simplified: prefixes up to each breakpoint are stored by hash;
    a later request reads the longest stored prefix that matches it at a block boundary."""

    def __init__(self):
        self.store: set[str] = set()

    def usage(self, kw: dict) -> tuple[int, int, int]:
        tools, system, messages = kw.get("tools", []), kw.get("system", []), kw["messages"]
        # Prefix units in render order: tools, system, then each message.
        units = [("tools", tools)] + [("system", system)] + [(f"m{i}", m) for i, m in enumerate(messages)]
        marked = [i for i, (_, u) in enumerate(units) if "cache_control" in json.dumps(u)]
        overhead = TOOL_PROMPT_OVERHEAD if tools else 0
        sizes, keys, total, h = [], [], overhead, hashlib.sha256()
        for _, u in units:
            clean = _strip_marks(u)
            h.update(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode())
            total += _tokens(clean)
            sizes.append(total)
            keys.append(h.hexdigest())

        read = max((sizes[i] for i, k in enumerate(keys) if k in self.store), default=0)
        last = marked[-1] if marked else -1
        end_cached = sizes[last] if last >= 0 and sizes[last] >= MIN_CACHEABLE else 0
        write = max(0, end_cached - read)
        for i in marked:
            if sizes[i] >= MIN_CACHEABLE:
                self.store.add(keys[i])
        return sizes[-1] - max(read, end_cached), read, write  # (uncached input, read, write)


class ScriptedClient:
    def __init__(self, cache: PrefixCache | None = None):
        self.cache = cache or PrefixCache()  # share one across sessions, like the real server
        self.messages = SimpleNamespace(create=self._create)
        self._n = 0

    def _turn(self, messages: list[dict]) -> tuple[str, int]:
        """Which script entry is active, and how many responses into it we are."""
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m["role"] != "user" or isinstance(m["content"], str):
                continue
            texts = [b.get("text", "") for b in m["content"] if b.get("type") == "text"]
            for key in SCRIPT:
                if any(t.startswith(key) for t in texts):
                    step = sum(1 for x in messages[i + 1:] if x["role"] == "assistant")
                    return key, step
        raise AssertionError("simulated client: request does not match any scenario turn")

    def _create(self, **kw):
        self._n += 1
        inp, read, write = self.cache.usage(kw)
        if "tools" not in kw:  # compaction.py's summarizer call
            content = [Block(type="text", text=COMPACTION_SUMMARY)]
            stop = "end_turn"
        else:
            key, step = self._turn(kw["messages"])
            content = [Block(type="thinking", thinking="", signature=f"sim-{self._n}")]
            for part in SCRIPT[key][step]:
                if part[0] == "tool":
                    content.append(Block(type="tool_use", id=f"toolu_sim_{self._n}_{len(content)}",
                                         name=part[1], input=part[2]))
                else:
                    content.append(Block(type="text", text=part[1]))
            stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        out = THINKING_TOKENS + sum(_tokens(b.to_dict()) for b in content)
        usage = SimpleNamespace(input_tokens=inp, output_tokens=out,
                                cache_read_input_tokens=read, cache_creation_input_tokens=write)
        return SimpleNamespace(content=content, stop_reason=stop, usage=usage)
