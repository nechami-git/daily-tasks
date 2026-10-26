"""The simulated API run must cover every scenario request and drive the real harness."""
from API.agent import Agent
from API.simulated_client import SCRIPT, PrefixCache, ScriptedClient
from shared import scenario as sc


def test_every_scenario_prompt_has_exactly_one_script_entry():
    prompts = [t["prompt"] for s in sc.load("scenario.json")["sessions"] for t in s["turns"]]
    for p in prompts:
        assert sum(p.startswith(k) for k in SCRIPT) == 1, p


def test_scripted_turn_runs_tools_and_caches():
    cache = PrefixCache()
    agent = Agent(client=ScriptedClient(cache))
    reply, stats = agent.ask("Two things to remember long-term: workouts only in the morning, "
                             "before 9:00. And no studying after 22:00.")
    assert stats["tools"] == ["save_preference", "save_preference"]
    assert "Saved both" in reply
    assert stats["cache_write"] > 0 and stats["cache_read"] > 0  # 2nd call reads the 1st's prefix
