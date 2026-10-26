"""Per-turn token usage and cost.

One "turn" = one user request; it can take several model calls (one per tool round).
"""
import time
from dataclasses import asdict, dataclass, field

from .log import say

FILE = "tokens.py"

# claude-opus-5-5, USD per million tokens, global endpoint (no inference_geo surcharge).
# Source: https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-10-25).
# Cache write = 5-minute TTL (1.25x input); cache read = 0.05x input on Opus 5.5.
PRICE = {"input": 4.00, "cache_write": 5.00, "cache_read": 0.20, "output": 20.00}


def cost(input_t: int, cache_write: int, cache_read: int, output: int) -> float:
    return (input_t * PRICE["input"] + cache_write * PRICE["cache_write"]
            + cache_read * PRICE["cache_read"] + output * PRICE["output"]) / 1_000_000


@dataclass
class TurnStats:
    input: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    model_calls: int = 0
    tools: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    seconds: float = 0.0
    last_context: int = 0  # prompt size of the latest call; compaction.py checks it
    _start: float = field(default_factory=time.perf_counter, repr=False)

    def add_usage(self, usage, label: str = "call") -> None:
        i = usage.input_tokens or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        o = usage.output_tokens or 0
        c = cost(i, cw, cr, o)
        self.input += i
        self.cache_read += cr
        self.cache_write += cw
        self.output += o
        self.model_calls += 1
        self.cost_usd += c
        self.last_context = i + cr + cw
        say(FILE, f"{label}: in {i} | cache read {cr} | cache write {cw} | out {o} | ${c:.4f}")

    def finish(self) -> dict:
        self.seconds = round(time.perf_counter() - self._start, 2)
        prompt = self.input + self.cache_read + self.cache_write
        hit = 100 * self.cache_read / prompt if prompt else 0
        say(FILE, f"turn total: {self.model_calls} calls, {prompt} prompt tokens "
                  f"({hit:.0f}% from cache), {self.output} out, ${self.cost_usd:.4f}, {self.seconds}s")
        d = asdict(self)
        d.pop("_start")
        d["cost_usd"] = round(d["cost_usd"], 6)
        return d
