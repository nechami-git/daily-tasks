"""Offline tests for the API harness, using MockClient (no API key, no network)."""
import json

import pytest

from API import agent as agent_mod
from API.agent import Agent
from API.harness import tokens
from shared.registry import run_tool
from tests.mock_client import MockClient, response, text, thinking, tool_use, usage


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def markers(blocks):
    return [b for b in blocks if isinstance(b, dict) and "cache_control" in b]


# --- loop.py + tools.py ---

def test_loop_runs_tools_until_end_turn(clean_data):
    client = MockClient([
        response(thinking(), tool_use("add_task", {"title": "Gym", "category": "fitness",
                                                   "time": "07:00"}, "t1"), stop="tool_use"),
        response(text("Added Gym at 07:00.")),
    ])
    reply, stats = Agent(client=client).ask("add gym at 7")

    assert reply == "Added Gym at 07:00."
    assert stats["model_calls"] == 2 and stats["tools"] == ["add_task"]
    tasks = json.loads((clean_data / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert tasks[0]["title"] == "Gym"  # the tool really ran and saved to disk


def test_parallel_tool_results_go_back_in_one_message():
    client = MockClient([
        response(tool_use("list_tasks", {}, "a"), tool_use("get_preferences", {}, "b"),
                 stop="tool_use"),
        response(text("ok")),
    ])
    Agent(client=client).ask("what do I have?")

    last = client.requests[1]["messages"][-1]
    assert last["role"] == "user"
    assert [b["tool_use_id"] for b in last["content"]] == ["a", "b"]


def test_tool_error_returns_is_error_and_loop_continues():
    client = MockClient([
        response(tool_use("complete_task", {"task_id": 99}, "x"), stop="tool_use"),
        response(text("There is no task 99.")),
    ])
    reply, _ = Agent(client=client).ask("complete task 99")

    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "no task #99" in result["content"]
    assert reply == "There is no task 99."


def test_max_rounds_stops_endless_tool_calls(monkeypatch):
    from API.harness import loop
    monkeypatch.setattr(loop, "MAX_ROUNDS", 3)
    client = MockClient([response(tool_use("list_tasks", {}, f"id{i}"), stop="tool_use")
                         for i in range(3)])
    reply, stats = Agent(client=client).ask("loop forever")
    assert "too many" in reply and stats["model_calls"] == 3


def test_request_uses_model_effort_and_adaptive_thinking():
    client = MockClient([response(text("hi"))])
    Agent(client=client).ask("hello")
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "medium"}
    assert req["thinking"] == {"type": "adaptive"}
    assert [t["name"] for t in req["tools"]][:3] == ["add_task", "list_tasks", "complete_task"]


# --- history.py ---

def test_history_is_append_only_and_resumable(clean_data):
    client = MockClient([response(thinking("s1"), text("one")), response(text("two"))])
    a = Agent(client=client)
    a.ask("first")
    path = a.history.path
    before = path.read_text(encoding="utf-8")
    a.ask("second")
    after = path.read_text(encoding="utf-8")
    assert after.startswith(before)  # old lines untouched, new lines only appended

    # The thinking block is sent back exactly as received.
    assert client.requests[1]["messages"][1]["content"][0] == {
        "type": "thinking", "thinking": "", "signature": "s1"}

    resumed = Agent(client=MockClient([]), session_id=a.history.session_id)
    assert resumed.history.messages == a.history.messages
    assert len(resumed.history.messages) == 4


# --- caching.py ---

def test_cache_breakpoints_on_system_and_last_message_only():
    client = MockClient([
        response(tool_use("list_tasks", {}, "a"), stop="tool_use"),
        response(text("done")),
    ])
    a = Agent(client=client)
    a.ask("list")
    req = client.requests[1]
    assert "cache_control" in req["system"][-1]
    msgs = req["messages"]
    assert markers(msgs[-1]["content"]) == [msgs[-1]["content"][-1]]
    assert all(not markers(m["content"]) for m in msgs[:-1] if isinstance(m["content"], list))
    # Markers live only in the request copy, never in history on disk.
    assert "cache_control" not in a.history.path.read_text(encoding="utf-8")


def test_system_and_tools_identical_across_requests():
    client = MockClient([response(text("a")), response(text("b"))])
    a = Agent(client=client)
    a.ask("one")
    a.ask("two")
    r1, r2 = client.requests
    assert r1["system"] == r2["system"] and r1["tools"] == r2["tools"]


# --- context.py + memory.py ---

def test_context_has_todays_tasks_and_only_relevant_prefs():
    run_tool("add_task", {"title": "Gym", "category": "fitness", "time": "07:00"})
    run_tool("add_task", {"title": "Laundry", "category": "home", "date": "tomorrow"})
    run_tool("save_preference", {"text": "I work out in the morning", "category": "fitness"})
    run_tool("save_preference", {"text": "No studying after 22:00", "category": "study"})
    run_tool("save_preference", {"text": "Lives in Jerusalem"})

    client = MockClient([response(text("ok"))])
    Agent(client=client).ask("Plan a workout for tonight")
    ctx = client.requests[0]["messages"][0]["content"][0]["text"]

    assert ctx.startswith("<context>")
    assert "Today is 2026-10-25 (Sunday)" in client.requests[0]["system"][0]["text"]
    assert "| Gym" in ctx and "Laundry" not in ctx  # only today's tasks
    assert "work out in the morning" in ctx and "Jerusalem" in ctx
    assert "studying" not in ctx  # study pref is not relevant to a workout request


# --- compaction.py (forced with a tiny threshold) ---

def test_compaction_summarizes_and_restarts_history(clean_data):
    client = MockClient([
        response(thinking("old"), text("Saved."), use=usage(inp=500)),  # turn 1
        response(text("- user works out in the morning (saved)")),       # compaction call
        response(text("Sure.")),                                         # turn 2
    ])
    a = Agent(client=client, compact_threshold=100)
    a.ask("I work out in the morning")
    reply, stats = a.ask("what about tomorrow?")

    summary_req, turn2_req = client.requests[1], client.requests[2]
    assert "tools" not in summary_req  # the summarizer is a plain call
    assert "user: I work out in the morning" in summary_req["messages"][0]["content"]
    # After compaction the model sees ONE user message: summary + context + new request.
    assert len(turn2_req["messages"]) == 1
    blocks = turn2_req["messages"][0]["content"]
    assert blocks[0]["text"].startswith("<summary of earlier conversation>")
    assert "works out in the morning" in blocks[0]["text"]
    assert blocks[-1]["text"] == "what about tomorrow?"
    assert "signature" not in json.dumps(turn2_req["messages"])  # no old thinking replayed

    assert reply == "Sure." and stats["model_calls"] == 2  # compaction call is counted
    kinds = [e["kind"] for e in read_jsonl(a.history.path)]
    assert kinds == ["message", "message", "compaction", "message", "message"]

    resumed = Agent(client=MockClient([]), session_id=a.history.session_id)
    assert len(resumed.history.messages) == 2  # only what came after the marker


def test_no_compaction_below_threshold():
    client = MockClient([response(text("a"), use=usage(inp=500)), response(text("b"))])
    a = Agent(client=client, compact_threshold=10_000)
    a.ask("one")
    a.ask("two")
    assert len(client.requests) == 2 and len(client.requests[1]["messages"]) == 3


# --- tokens.py ---

def test_cost_uses_opus_5_5_prices():
    assert tokens.cost(1_000_000, 0, 0, 0) == pytest.approx(4.00)
    assert tokens.cost(0, 1_000_000, 0, 0) == pytest.approx(5.00)
    assert tokens.cost(0, 0, 1_000_000, 0) == pytest.approx(0.20)
    assert tokens.cost(0, 0, 0, 1_000_000) == pytest.approx(20.00)


def test_turn_stats_sum_all_calls():
    client = MockClient([
        response(tool_use("list_tasks", {}, "a"), stop="tool_use",
                 use=usage(inp=1000, out=50, cache_write=2000)),
        response(text("ok"), use=usage(inp=200, out=30, cache_read=2000)),
    ])
    _, s = Agent(client=client).ask("list")
    assert (s["input"], s["cache_write"], s["cache_read"], s["output"]) == (1200, 2000, 2000, 80)
    assert s["cost_usd"] == pytest.approx(tokens.cost(1200, 2000, 2000, 80), abs=1e-6)
    assert s["seconds"] >= 0


# --- every runtime action names its file ---

def test_every_harness_file_prints_its_name(capsys):
    client = MockClient([
        response(text("x"), use=usage(inp=500)),
        response(text("summary")),
        response(tool_use("list_tasks", {}, "a"), stop="tool_use"),
        response(text("y")),
    ])
    a = Agent(client=client, compact_threshold=100)
    a.ask("first")
    a.ask("workout tomorrow?")
    out = capsys.readouterr().out
    for f in ["loop.py", "tools.py", "history.py", "memory.py", "context.py",
              "compaction.py", "caching.py", "tokens.py", "agent.py"]:
        assert f"[{f}]" in out, f


def test_missing_api_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        agent_mod.make_client()
