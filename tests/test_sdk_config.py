"""Offline checks of the SDK configuration. Nothing here starts Claude Code."""
import asyncio
import json

from shared.registry import TOOLS, run_tool
from SDK import tools as sdk_tools
from SDK.agent import SdkAgent


def test_options_are_restricted():
    o = SdkAgent().options
    assert o.model == "claude-opus-5-5" and o.effort == "medium"
    assert o.fallback_model is None
    assert o.tools == []  # no built-in tools at all
    assert o.allowed_tools == [f"mcp__tasks__{t['name']}" for t in TOOLS]
    assert o.strict_mcp_config is True
    assert o.permission_mode == "dontAsk"
    assert o.setting_sources == ["project"]
    assert "daily task manager" in o.system_prompt  # our own prompt, not Claude Code's


def test_claude_md_holds_preferences(clean_data):
    run_tool("save_preference", {"text": "I work out in the morning", "category": "fitness"})
    agent = SdkAgent()
    md = (agent.workspace / "CLAUDE.md").read_text(encoding="utf-8")
    assert "#1 [fitness] I work out in the morning" in md


def test_both_versions_get_the_same_pinned_date():
    from API.harness.context import system_blocks
    from shared.prompt import date_rule
    line = date_rule()
    assert line.startswith("Today is 2026-10-25 (Sunday).")  # from DAILY_TASKS_TODAY, not the clock
    assert line in system_blocks()[0]["text"]
    assert line in SdkAgent().options.system_prompt


def test_tool_wrappers_call_shared_tools_and_flag_errors(clean_data):
    wrapped = {t["name"]: sdk_tools._wrap(t) for t in TOOLS}
    ok = asyncio.run(wrapped["add_task"].handler({"title": "Gym", "category": "fitness"}))
    assert ok["content"][0]["text"].startswith("added #1") and "is_error" not in ok
    assert json.loads((clean_data / "tasks.json").read_text(encoding="utf-8"))["tasks"]

    bad = asyncio.run(wrapped["complete_task"].handler({"task_id": 42}))
    assert bad["is_error"] is True and "no task #42" in bad["content"][0]["text"]


def test_same_schemas_as_api_version():
    from API.harness.tools import schemas
    api = {s["name"]: s["input_schema"] for s in schemas()}
    sdk = {t["name"]: sdk_tools._wrap(t).input_schema for t in TOOLS}
    assert api == sdk
