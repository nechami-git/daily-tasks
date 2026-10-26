"""ClaudeAgentOptions + client. Every line that takes over a harness file is marked # replaces: <file>."""
import time

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              ResultMessage, ToolUseBlock)

from shared import storage
from shared.preferences import find_preferences
from shared.prompt import system_prompt
from SDK import tools

MODEL = "claude-opus-5-5"
EFFORT = "medium"


def say(msg: str) -> None:
    print(f"[SDK/agent.py] {msg}", flush=True)


def write_memory_file(workspace) -> None:  # replaces: memory.py
    """CLAUDE.md in the session's cwd, loaded by Claude Code at session start."""
    prefs = find_preferences()
    lines = ["# Memory for the daily task manager", "", "## Saved preferences"]
    lines += [f"- #{p['id']} [{p['category']}] {p['text']}" for p in prefs] or ["- none yet"]
    (workspace / "CLAUDE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"CLAUDE.md written with {len(prefs)} preferences")


class SdkAgent:
    def __init__(self, session_id: str | None = None):
        # Clean, dedicated cwd: no stray CLAUDE.md, .mcp.json or settings get picked up.
        self.workspace = storage.data_dir() / "sdk_workspace"
        self.workspace.mkdir(exist_ok=True)
        write_memory_file(self.workspace)
        self.session_id = session_id
        self.options = ClaudeAgentOptions(
            model=MODEL,
            fallback_model=None,                 # no model switching: same model as API/
            effort=EFFORT,
            thinking={"type": "adaptive"},
            system_prompt=system_prompt("sdk"),  # replaces: context.py (stable part, incl. date)
            tools=[],                            # no built-in tools (Bash, Read, ...)
            mcp_servers={tools.SERVER: tools.build_server()},  # replaces: tools.py
            allowed_tools=tools.TOOL_NAMES,      # only our 6 tools, auto-approved
            permission_mode="dontAsk",           # anything else is denied, never prompted
            strict_mcp_config=True,              # ignore any other MCP config on the machine
            setting_sources=["project"],         # replaces: memory.py (loads CLAUDE.md)
            cwd=str(self.workspace),
            resume=session_id,                   # replaces: history.py
            # replaces: compaction.py -> Claude Code auto-compacts near the context limit
            # replaces: caching.py    -> Claude Code places cache_control itself
            # replaces: loop.py       -> Claude Code runs the tool_use loop (client.query below)
        )
        self.client = ClaudeSDKClient(self.options)
        self._prev_total = 0.0  # running totals from the previous ResultMessage
        self._prev_mu: dict = {}

    async def start(self) -> None:
        await self.client.connect()
        say(f"connected: model={MODEL} effort={EFFORT} resume={self.session_id}")

    async def close(self) -> None:
        await self.client.disconnect()

    async def ask(self, user_text: str) -> tuple[str, dict]:
        start = time.perf_counter()
        await self.client.query(user_text)                  # replaces: loop.py
        calls: dict[str, dict] = {}  # message_id -> usage; one API call can stream several messages
        models, used_tools, reply, result = set(), [], "", None
        async for msg in self.client.receive_response():   # replaces: loop.py
            if isinstance(msg, AssistantMessage):
                models.add(msg.model)
                if msg.message_id and msg.usage:
                    calls[msg.message_id] = msg.usage
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        used_tools.append(block.name.removeprefix(f"mcp__{tools.SERVER}__"))
            elif isinstance(msg, ResultMessage):
                result = msg
                reply = msg.result or ""

        if result is None:
            raise RuntimeError("Claude Code ended the turn without a ResultMessage")
        self.session_id = result.session_id                 # replaces: history.py
        stats = self._turn_stats(result, calls, used_tools, models)  # replaces: tokens.py
        stats["seconds"] = round(time.perf_counter() - start, 2)
        say(f"turn: {stats['model_calls']} calls, tools {used_tools or '-'}, "
            f"${stats['cost_usd']:.4f}, {stats['seconds']}s, models {stats['models_seen']}")
        other = set(stats["model_usage"]) - {MODEL}
        if other:
            say(f"NOTE: models other than {MODEL} were used: {sorted(other)}")
        return reply, stats

    def _turn_stats(self, result, calls: dict, used_tools: list, models: set) -> dict:  # replaces: tokens.py
        """Per-turn numbers. total_cost_usd is a running total for the connection (SDK docs),
        so this turn's cost is the difference from the previous turn. model_usage is treated
        the same way when its costs add up to that running total."""
        total = result.total_cost_usd or 0.0
        cost = total - self._prev_total if total >= self._prev_total else total
        self._prev_total = total

        mu = result.model_usage or {}
        cumulative = abs(sum(u.get("costUSD", 0) for u in mu.values()) - total) < 1e-6
        prev_mu = self._prev_mu if cumulative else {}
        self._prev_mu = mu
        keys = {"input": "inputTokens", "cache_read": "cacheReadInputTokens",
                "cache_write": "cacheCreationInputTokens", "output": "outputTokens"}
        per_model = {}
        for model, u in mu.items():
            before = prev_mu.get(model, {})
            row = {k: u.get(src, 0) - before.get(src, 0) for k, src in keys.items()}
            row["cost_usd"] = round(u.get("costUSD", 0) - before.get("costUSD", 0), 6)
            if any(row.values()):
                per_model[model] = row

        # Main loop only, summed per API call (one per message_id).
        main = {k: sum(c.get(src, 0) or 0 for c in calls.values()) for k, src in {
            "input": "input_tokens", "cache_read": "cache_read_input_tokens",
            "cache_write": "cache_creation_input_tokens", "output": "output_tokens"}.items()}

        return {
            # All models Claude Code ran this turn (main loop + its own helper calls).
            **{k: sum(r[k] for r in per_model.values()) for k in keys},
            "model_calls": len(calls),
            "tools": used_tools,
            "cost_usd": round(cost, 6),
            "num_turns": result.num_turns,
            "models_seen": sorted(models),
            "model_usage": per_model,
            "main_loop_tokens": main,
            "model_usage_was_cumulative": cumulative,
            "result_usage_raw": result.usage,
            "is_error": result.is_error,
        }
