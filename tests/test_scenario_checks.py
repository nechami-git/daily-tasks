"""Offline tests for the scenario check logic and the LOC counter (shared/scenario.py)."""
from shared import scenario as sc


def task(id_, date, time, dur, cat="study", status="todo", prio="medium"):
    return {"id": id_, "title": f"t{id_}", "category": cat, "date": date, "time": time,
            "duration_min": dur, "priority": prio, "status": status}


def snap(tasks=(), prefs=()):
    return {"tasks": list(tasks), "preferences": list(prefs)}


def ev(check, snaps, turns=None):
    return sc.evaluate(check, snaps, turns or {})[0]


def test_task_exists_and_absent():
    s = {"end": snap([task(1, "2026-10-29", "10:00", 120, prio="high")])}
    match = {"category": "study", "date": "2026-10-29", "time": "10:00", "priority": "high"}
    assert ev({"type": "task_exists", "match": match}, s)
    assert not ev({"type": "task_absent", "match": match}, s)
    assert ev({"type": "task_exists", "match": {"time_before": "11:00"}}, s)
    assert not ev({"type": "task_exists", "match": {"time_before": "09:00"}}, s)


def test_friday_tasks_must_end_before_candles():
    check = {"type": "tasks_end_before", "date": "2026-10-30", "time": "16:11",
             "min_tasks": {"category": "study"}}
    ok = {"end": snap([task(1, "2026-10-30", "09:00", 180)])}            # ends 12:00
    late = {"end": snap([task(1, "2026-10-30", "14:00", 180)])}          # ends 17:00
    no_time = {"end": snap([task(1, "2026-10-30", None, 180)])}
    none = {"end": snap([])}
    assert ev(check, ok)
    assert not ev(check, late) and not ev(check, no_time) and not ev(check, none)


def test_nothing_on_shabbat():
    check = {"type": "no_tasks_between", "start": "2026-10-30T16:11", "end": "2026-10-31T17:28"}
    assert ev(check, {"end": snap([task(1, "2026-10-30", "13:00", 180),     # ends 16:00
                                   task(2, "2026-10-31", "18:00", 180),     # after havdalah
                                   task(3, "2026-11-01", None, 180)])})
    assert not ev(check, {"end": snap([task(1, "2026-10-31", "10:00", 60)])})
    assert not ev(check, {"end": snap([task(1, "2026-10-30", "15:30", 60)])})  # runs into Shabbat
    assert not ev(check, {"end": snap([task(1, "2026-10-31", None, 60)])})     # no time on Sat


def test_saturday_replacement_not_booked_without_asking():
    check = {"type": "task_absent", "match": {"title_contains": "algo", "date_not": "2026-10-30"}}
    friday = dict(task(3, "2026-10-30", "10:00", 180), title="Review for Algorithms exam")
    sat_night = dict(task(4, "2026-10-31", "18:00", 180), title="Review for Algorithms exam (part 2)")
    other = task(1, "2026-10-29", "10:00", 120)  # not an Algorithms task
    assert ev(check, {"end": snap([friday, other])})        # booking Friday right away is fine
    assert not ev(check, {"end": snap([friday, sat_night])})  # Saturday part booked unasked


def test_no_duplicate_tasks():
    check = {"type": "no_duplicate_tasks", "key": ["date", "time", "category"]}
    friday = task(1, "2026-10-30", "09:00", 180)
    assert ev(check, {"end": snap([friday, task(2, "2026-10-31", "18:00", 180)])})
    assert not ev(check, {"end": snap([friday, task(2, "2026-10-30", "09:00", 180)])})  # re-booked


def test_preference_checks():
    p1 = {"id": 1, "category": "fitness", "text": "Workouts only in the morning, before 9:00"}
    p2 = {"id": 2, "category": "study", "text": "No studying after 22:00"}
    snaps = {"s1-4": snap(prefs=[p1, p2]), "end": snap(prefs=[p1, p2])}
    exist = {"type": "prefs_exist", "match": [
        {"category": "fitness", "text_any": ["morning"]}, {"category": "study", "text_any": ["22"]}]}
    assert ev(exist, snaps)
    unchanged = {"type": "prefs_unchanged", "since": "s1-4", "category": "fitness"}
    assert ev(unchanged, snaps)
    changed = dict(p1, text="Workouts in the evening")
    assert not ev(unchanged, {"s1-4": snaps["s1-4"], "end": snap(prefs=[changed, p2])})


def test_turn_checks():
    turns = {"s1-3": {"tools": ["get_jewish_calendar", "add_task"], "reply": "בשבת אי אפשר"}}
    s = {"end": snap()}
    assert ev({"type": "tool_called", "turn": "s1-3", "tool": "get_jewish_calendar"}, s, turns)
    assert ev({"type": "reply_contains", "turn": "s1-3", "all_groups": [["שבת", "Shabbat"]]}, s, turns)
    assert not ev({"type": "reply_contains", "turn": "s1-3", "all_groups": [["10:00"]]}, s, turns)


def test_real_scenario_checks_all_evaluate():
    scenario = sc.load("scenario.json")
    ids = [t["id"] for s in scenario["sessions"] for t in s["turns"]]
    assert 6 <= len(ids) <= 8 and len(scenario["sessions"]) == 2
    snaps = {i: snap() for i in ids + ["end"]}
    turns = {i: {"tools": [], "reply": ""} for i in ids}
    results = sc.run_checks(scenario, snaps, turns)
    assert len(results) >= 5  # every check type is known and runs


def test_loc_report_counts_parts():
    loc = sc.loc_report()
    assert set(loc["per_part"]) == set(sc.PARTS)
    assert all(v["api"] > 0 for v in loc["per_part"].values())
    assert loc["per_part"]["tools"]["sdk"] > 0  # marked code lines in SDK/tools.py
    assert loc["per_part"]["compaction"]["sdk_note"] == "automatic"
    # The simulation helper is a test tool: listed separately, never in the API counts.
    assert not any("simulated_client" in k for k in loc["api_files"])
    assert "API/simulated_client.py" in loc["test_tools_not_counted"]
    assert loc["harness_total"]["api"] == sum(v["api"] for v in loc["per_part"].values())
