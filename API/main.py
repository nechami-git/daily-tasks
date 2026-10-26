"""CLI entry point: interactive chat, or run the scenario and write results/api.json.

Real run (needs ANTHROPIC_API_KEY; --warm runs the scenario twice and reports the second run,
matching the warm-cache SDK result):
    python API/main.py --scenario scenario.json --out results/api.json --warm

Simulated run (no key, no model calls; scripted responses, estimated tokens):
    python API/main.py --scenario scenario.json --out results/api.json --simulate
"""
import argparse
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

import shared  # noqa: E402,F401  (first: installs the OS cert store before any HTTPS client)
from API.agent import COMPACT_THRESHOLD, EFFORT, MODEL, Agent, make_client  # noqa: E402
from shared import scenario as sc  # noqa: E402

# In the simulation, compaction is forced once (session 1 never reaches 30k tokens) so that
# compaction.py runs too. With the estimated sizes, the prompt is ~2,230 tokens after s1-3 and
# ~2,480 after s1-4, so 2,400 compacts exactly once: before s1-5, after the Algorithms plan is
# settled. The real run keeps the normal threshold.
SIMULATED_COMPACT_THRESHOLD = 2_400

SIMULATION_NOTE = (
    "SIMULATED RUN: no model was called. API/simulated_client.py returned scripted responses "
    "modelled on the real SDK run, while every harness file and every shared tool ran for real "
    "(including the Hebcal call). Token counts are estimates (characters / 4) with a simple "
    "prefix-cache model; cost is computed from those estimates. Token, cache and cost numbers "
    "are NOT comparable with the SDK's real numbers. Checks show that the harness handles the "
    "scripted behavior correctly, not how the model behaves. Compaction threshold lowered to "
    f"{SIMULATED_COMPACT_THRESHOLD} so compaction runs once.")


def run_scenario(path: str, out: str | None, simulate: bool) -> None:
    scenario = sc.load(path)
    if simulate:
        from API.simulated_client import PrefixCache, ScriptedClient
        cache = PrefixCache()  # one "server" cache for the whole run
        new_client, threshold = (lambda: ScriptedClient(cache)), SIMULATED_COMPACT_THRESHOLD
    else:
        make_client()  # fail fast if the key is missing, before touching any state
        new_client, threshold = make_client, COMPACT_THRESHOLD
    sc.prepare("api", scenario)
    started = datetime.now().isoformat(timespec="seconds")
    snaps, turns, records = {}, {}, []

    for session in scenario["sessions"]:
        # New instance per session: only the files on disk carry over.
        agent = Agent(client=new_client(), compact_threshold=threshold)
        sc.say(f"session {session['id']} -> agent session {agent.history.session_id}")
        for turn in session["turns"]:
            sc.say(f"--- {turn['id']}: {turn['prompt']}")
            reply, stats = agent.ask(turn["prompt"])
            stats.pop("last_context", None)
            rec = {"session": session["id"], "turn": turn["id"], "prompt": turn["prompt"],
                   "reply": reply, **stats}
            records.append(rec)
            turns[turn["id"]] = rec
            snaps[turn["id"]] = sc.snapshot()
    snaps["end"] = sc.snapshot()

    checks = sc.run_checks(scenario, snaps, turns)
    payload = {
        "version": "api",
        "simulated": simulate,
        **({"simulation_note": SIMULATION_NOTE} if simulate else {}),
        "model": "none (simulated)" if simulate else MODEL, "effort": EFFORT,
        "compact_threshold": threshold,
        "scenario": scenario["name"], "today": scenario["today"], "started": started,
        "libraries": {p: version(p) for p in ["anthropic", "requests", "truststore"]},
        "turns": records,
        "totals": sc.totals(records),
        "checks": checks,
        "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "loc": sc.loc_report(),
        "final_state": snaps["end"],
    }
    sc.write(out, payload)


def chat(session: str | None) -> None:
    agent = Agent(session_id=session)
    print("Type a request (empty line to quit).")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if not text:
            break
        reply, _ = agent.ask(text)
        print(reply)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily task manager (raw Messages API)")
    parser.add_argument("--scenario", help="scenario JSON to run")
    parser.add_argument("--out", default="results/api.json")
    parser.add_argument("--simulate", action="store_true",
                        help="no API key: scripted model, estimated tokens (marked simulated)")
    parser.add_argument("--warm", action="store_true",
                        help="real run: run twice, report the second (warm cache) run")
    parser.add_argument("--session", help="chat mode: resume this session id")
    args = parser.parse_args()
    if not args.scenario:
        chat(args.session)
        return
    if args.warm and not args.simulate:
        sc.say("warm-up run (saved only under results/runs/)")
        run_scenario(args.scenario, None, simulate=False)
        sc.say("reported run")
    run_scenario(args.scenario, args.out, simulate=args.simulate)


if __name__ == "__main__":
    main()
