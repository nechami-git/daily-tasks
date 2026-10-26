"""CLI entry point: interactive chat, or run the scenario and write results/sdk.json.

    python SDK/main.py --scenario scenario.json --out results/sdk.json
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, datetime
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

import shared  # noqa: E402,F401  (OS cert store for the in-process tools, e.g. Hebcal)
from SDK.agent import EFFORT, MODEL, SdkAgent  # noqa: E402
from shared import scenario as sc  # noqa: E402


def check_env() -> None:
    # The SDK must bill to the Claude Code login, not to an API key.
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is set: the SDK run would bill the key instead of "
                         "your Claude Code login. Run:  Remove-Item Env:ANTHROPIC_API_KEY")
    if not os.environ.get("NODE_EXTRA_CA_CERTS"):
        print("[SDK/main.py] warning: NODE_EXTRA_CA_CERTS not set; behind an HTTPS filter "
              "Claude Code may fail to connect", flush=True)


def cli_version() -> str:
    import claude_agent_sdk
    exe = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
    try:
        return subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                              timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def date_injection_report(session_ids: list[str], pinned: str) -> dict:
    """Did Claude Code put the machine's real date into the conversation?

    We can only see what Claude Code writes to its transcript files, not the full request,
    so 'not found' is not proof of absence.
    """
    real = date.today().isoformat()
    if real == pinned:
        return {"real_date": real, "result": "inconclusive: real date equals the pinned date"}
    def strip_timestamps(obj):
        # Every transcript line has a "timestamp" field with the real date; that is
        # bookkeeping, not model context, so leave it out of the search.
        if isinstance(obj, dict):
            return {k: strip_timestamps(v) for k, v in obj.items() if k != "timestamp"}
        if isinstance(obj, list):
            return [strip_timestamps(v) for v in obj]
        return obj

    found = []
    projects = Path.home() / ".claude" / "projects"
    for sid in session_ids:
        for f in projects.glob(f"*/{sid}.jsonl"):
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    text = json.dumps(strip_timestamps(json.loads(line)), ensure_ascii=False)
                except json.JSONDecodeError:
                    continue
                for variant in {real, real.replace("-", "/")}:
                    i = text.find(variant)
                    if i >= 0:
                        found.append({"file": str(f), "snippet": text[max(0, i - 120): i + 40]})
    return {"real_date": real, "pinned_date": pinned,
            "result": "real date FOUND in transcript" if found else "real date not found in transcript",
            "hits": found[:3]}


async def run_scenario(path: str, out: str) -> None:
    scenario = sc.load(path)
    sc.prepare("sdk", scenario)
    started = datetime.now().isoformat(timespec="seconds")
    snaps, turns, records, session_ids = {}, {}, [], []

    for session in scenario["sessions"]:
        agent = SdkAgent()  # new instance + new Claude Code session: only files on disk carry over
        await agent.start()
        try:
            for turn in session["turns"]:
                sc.say(f"--- {turn['id']}: {turn['prompt']}")
                reply, stats = await agent.ask(turn["prompt"])
                rec = {"session": session["id"], "turn": turn["id"], "prompt": turn["prompt"],
                       "reply": reply, **stats}
                records.append(rec)
                turns[turn["id"]] = rec
                snaps[turn["id"]] = sc.snapshot()
        finally:
            await agent.close()
        session_ids.append(agent.session_id)
        sc.say(f"session {session['id']} -> Claude Code session {agent.session_id}")
    snaps["end"] = sc.snapshot()

    checks = sc.run_checks(scenario, snaps, turns)
    other_models = sorted({m for r in records for m in r["model_usage"]} - {MODEL})
    sc.write(out, {
        "version": "sdk",
        "model": MODEL, "effort": EFFORT,
        "scenario": scenario["name"], "today": scenario["today"], "started": started,
        "libraries": {**{p: version(p) for p in ["claude-agent-sdk", "requests", "truststore"]},
                      "claude_code_cli": cli_version()},
        "turns": records,
        "totals": sc.totals(records),
        "checks": checks,
        "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "loc": sc.loc_report(),
        "final_state": snaps["end"],
        "observations": {
            "claude_code_sessions": session_ids,
            "models_other_than_main": other_models,
            "real_date_injection": date_injection_report(session_ids, scenario["today"]),
        },
    })


async def chat(session: str | None) -> None:
    agent = SdkAgent(session_id=session)
    await agent.start()
    try:
        print("Type a request (empty line to quit).")
        while True:
            text = (await asyncio.to_thread(input, "> ")).strip()
            if not text:
                break
            reply, _ = await agent.ask(text)
            print(reply)
    finally:
        await agent.close()
        print(f"[SDK/main.py] session id: {agent.session_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily task manager (Claude Agent SDK)")
    parser.add_argument("--scenario", help="scenario JSON to run")
    parser.add_argument("--out", default="results/sdk.json")
    parser.add_argument("--session", help="chat mode: resume this session id")
    args = parser.parse_args()
    check_env()
    if args.scenario:
        asyncio.run(run_scenario(args.scenario, args.out))
    else:
        asyncio.run(chat(args.session))


if __name__ == "__main__":
    main()
