"""Scenario support used by API/main.py and SDK/main.py: clean state, snapshots, checks, LOC.

Not part of either harness; both runs use exactly the same check code.
"""
import ast
import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from . import storage

ROOT = Path(__file__).resolve().parent.parent
PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]


def say(msg: str) -> None:
    print(f"[scenario.py] {msg}", flush=True)


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare(version: str, scenario: dict) -> Path:
    """Fresh, empty data folder for this run + the pinned scenario date."""
    run_dir = ROOT / ".runs" / version
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    os.environ["DAILY_TASKS_DATA_DIR"] = str(run_dir)
    os.environ["DAILY_TASKS_TODAY"] = scenario["today"]
    say(f"clean data dir {run_dir}, today={scenario['today']}")
    return run_dir


def snapshot() -> dict:
    return {"tasks": storage.load("tasks", {"tasks": []})["tasks"],
            "preferences": storage.load("preferences", {"preferences": []})["preferences"]}


# --- checks -----------------------------------------------------------------

def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _task_matches(task: dict, match: dict) -> bool:
    for key, want in match.items():
        if key == "time_before":
            if not task["time"] or _minutes(task["time"]) >= _minutes(want):
                return False
        elif key == "title_contains":
            if want.lower() not in task["title"].lower():
                return False
        elif key == "date_not":
            if task["date"] == want:
                return False
        elif task.get(key) != want:
            return False
    return True


def _interval(task: dict) -> tuple[datetime, datetime]:
    day = datetime.fromisoformat(task["date"])
    if not task["time"]:  # no time: assume it may happen any time that day
        return day, day + timedelta(days=1)
    start = day + timedelta(minutes=_minutes(task["time"]))
    return start, start + timedelta(minutes=task["duration_min"])


def _fmt(task: dict) -> str:
    return f"#{task['id']} {task['date']} {task['time'] or '--:--'} {task['duration_min']}m {task['category']} {task['title']}"


def evaluate(check: dict, snaps: dict, turns: dict) -> tuple[bool, str]:
    state = snaps[check.get("after", "end")]
    tasks, prefs = state["tasks"], state["preferences"]
    kind = check["type"]

    if kind in ("task_exists", "task_absent"):
        hits = [t for t in tasks if _task_matches(t, check["match"])]
        ok = bool(hits) if kind == "task_exists" else not hits
        return ok, "; ".join(map(_fmt, hits)) or "no matching task"

    if kind == "prefs_exist":
        missing = [m for m in check["match"]
                   if not any(p["category"] == m["category"] and
                              any(s.lower() in p["text"].lower() for s in m["text_any"])
                              for p in prefs)]
        return not missing, f"missing: {missing}" if missing else f"{len(prefs)} prefs saved"

    if kind == "prefs_unchanged":
        def pick(ps):
            return [(p["id"], p["category"], p["text"]) for p in ps if p["category"] == check["category"]]
        before, after = pick(snaps[check["since"]]["preferences"]), pick(prefs)
        return bool(before) and before == after, f"before={before} after={after}"

    if kind == "tool_called":
        used = turns[check["turn"]]["tools"]
        return check["tool"] in used, f"tools: {used}"

    if kind == "reply_contains":
        reply = turns[check["turn"]]["reply"].lower()
        missing = [g for g in check["all_groups"] if not any(s.lower() in reply for s in g)]
        return not missing, f"missing one of: {missing}" if missing else "all found"

    if kind == "tasks_end_before":
        day = [t for t in tasks if t["date"] == check["date"]]
        limit = _minutes(check["time"])
        late = [t for t in day if not t["time"] or _minutes(t["time"]) + t["duration_min"] > limit]
        enough = any(_task_matches(t, check.get("min_tasks", {})) for t in day)
        detail = f"{len(day)} task(s) that day; late: {[_fmt(t) for t in late]}"
        return enough and not late, detail if enough else "no matching task that day"

    if kind == "no_duplicate_tasks":
        seen: dict[tuple, list] = {}
        for t in tasks:
            seen.setdefault(tuple(t[k] for k in check["key"]), []).append(t)
        dups = [g for g in seen.values() if len(g) > 1]
        return not dups, "; ".join(" = ".join(map(_fmt, g)) for g in dups) or f"{len(tasks)} unique tasks"

    if kind == "no_tasks_between":
        lo, hi = datetime.fromisoformat(check["start"]), datetime.fromisoformat(check["end"])
        bad = [t for t in tasks if _interval(t)[0] < hi and _interval(t)[1] > lo]
        return not bad, "; ".join(map(_fmt, bad)) or "none overlap"

    raise ValueError(f"unknown check type {kind}")


def run_checks(scenario: dict, snaps: dict, turns: dict) -> list[dict]:
    results = []
    for c in scenario["checks"]:
        ok, detail = evaluate(c, snaps, turns)
        results.append({"id": c["id"], "description": c["description"], "passed": ok, "detail": detail})
        say(f"{'PASS' if ok else 'FAIL'} {c['id']}: {detail}")
    return results


# --- lines of code -----------------------------------------------------------

def code_lines(path: Path) -> set[int]:
    """Line numbers holding real code: no blank lines, comments or docstrings."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            doc.update(range(body[0].lineno, body[0].end_lineno + 1))
    return {i for i, line in enumerate(src.splitlines(), 1)
            if line.strip() and not line.strip().startswith("#") and i not in doc}


def loc_report() -> dict:
    harness = ROOT / "API" / "harness"
    api = {p: len(code_lines(harness / f"{p}.py")) for p in PARTS}

    sdk = {p: set() for p in PARTS}  # (file, line) pairs, so nothing is counted twice
    automatic = set()
    for f in sorted((ROOT / "SDK").glob("*.py")):
        code = code_lines(f)
        lines = f.read_text(encoding="utf-8").splitlines()
        # A marker on a `def` line covers the whole function body.
        funcs = {n.lineno: range(n.lineno, n.end_lineno + 1)
                 for n in ast.walk(ast.parse("\n".join(lines)))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for i, line in enumerate(lines, 1):
            for part in re.findall(r"replaces: (\w+)\.py", line):
                if i in funcs:
                    sdk[part].update((f.name, j) for j in funcs[i] if j in code)
                elif i in code:
                    sdk[part].add((f.name, i))
                else:
                    automatic.add(part)  # comment-only marker: Claude Code does it, no code
    sdk = {p: len(v) for p, v in sdk.items()}
    # simulated_client.py is a test tool for runs without an API key, not part of the API version.
    test_tools = {"simulated_client.py"}
    files = lambda folder: {p.name: len(code_lines(p)) for p in sorted(folder.glob("*.py"))
                            if p.name != "__init__.py" and p.name not in test_tools}
    return {
        "per_part": {p: {"api": api[p], "sdk": sdk[p],
                         "sdk_note": "automatic" if p in automatic and not sdk[p] else ""}
                     for p in PARTS},
        "harness_total": {"api": sum(api.values()), "sdk": sum(sdk.values())},
        "api_files": {**{f"harness/{k}": v for k, v in files(harness).items()},
                      **files(ROOT / "API")},
        "test_tools_not_counted": {f"API/{n}": len(code_lines(ROOT / "API" / n))
                                   for n in sorted(test_tools) if (ROOT / "API" / n).exists()},
        "sdk_files": files(ROOT / "SDK"),
        "shared_files": {k: v for k, v in files(ROOT / "shared").items() if k != "scenario.py"},
        "counting_rule": "non-blank lines, excluding comments and docstrings; SDK per part = "
                         "code lines marked '# replaces: <part>.py' (a marker on a def line "
                         "counts the whole function)",
    }


# --- output ------------------------------------------------------------------

def totals(turns: list[dict]) -> dict:
    keys = ["input", "cache_read", "cache_write", "output", "model_calls", "cost_usd", "seconds"]
    t = {k: round(sum(x.get(k) or 0 for x in turns), 6) for k in keys}
    prompt = t["input"] + t["cache_read"] + t["cache_write"]
    t["cache_hit_pct"] = round(100 * t["cache_read"] / prompt, 1) if prompt else 0.0
    t["tool_calls"] = sum(len(x["tools"]) for x in turns)
    return t


def write(path: str | None, payload: dict) -> Path:
    """Always keep a timestamped copy in results/runs/; also write `path` when given."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = "-simulated" if payload.get("simulated") else ""
    copy = ROOT / "results" / "runs" / f"{payload['version']}{tag}-{stamp}.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(text, encoding="utf-8")
    say(f"wrote {copy.relative_to(ROOT)}")
    if path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        say(f"wrote {out}")
    return copy
