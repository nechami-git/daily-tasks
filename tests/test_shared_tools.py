"""Basic offline tests for the domain tools in shared/."""
import json

import pytest

from shared import jewish_calendar
from shared.registry import TOOLS, run_tool
from shared.storage import ToolError


def read(dir_, name):
    return json.loads((dir_ / f"{name}.json").read_text(encoding="utf-8"))


# --- tasks ---

def test_add_task_saves_to_disk(clean_data):
    out = run_tool("add_task", {"title": "Run 5k", "category": "fitness",
                                "time": "07:00", "duration_min": 40, "priority": "high"})
    assert out == "added #1 2026-10-25 07:00 40m fitness high todo | Run 5k"
    task = read(clean_data, "tasks")["tasks"][0]
    assert task["category"] == "fitness" and task["status"] == "todo"


def test_new_category_is_remembered(clean_data):
    out = run_tool("add_task", {"title": "Call bank", "category": "Finance"})
    assert "new category 'finance'" in out
    assert "finance" in read(clean_data, "tasks")["categories"]


def test_list_tasks_is_compact_and_filtered():
    run_tool("add_task", {"title": "Exam prep", "category": "study", "time": "10:00"})
    run_tool("add_task", {"title": "Gym", "category": "fitness", "time": "07:00"})
    run_tool("add_task", {"title": "Laundry", "category": "home", "date": "tomorrow"})

    today = run_tool("list_tasks", {"date": "today"}).splitlines()
    assert [l.split("| ")[1] for l in today] == ["Gym", "Exam prep"]  # sorted by time
    assert not any("{" in l for l in today)  # plain lines, no JSON
    assert run_tool("list_tasks", {"category": "home"}).endswith("| Laundry")
    assert run_tool("list_tasks", {"date": "2026-01-01"}) == "no tasks"


def test_complete_task(clean_data):
    run_tool("add_task", {"title": "Gym", "category": "fitness"})
    assert run_tool("complete_task", {"task_id": 1}) == "done #1 Gym"
    assert run_tool("complete_task", {"task_id": 1}).startswith("already done")
    assert read(clean_data, "tasks")["tasks"][0]["status"] == "done"
    assert run_tool("list_tasks", {"status": "done"}).startswith("#1 ")
    kinds = [e["kind"] for e in read(clean_data, "history")["events"]]
    assert kinds == ["task_added", "task_completed"]


@pytest.mark.parametrize("name,args", [
    ("complete_task", {"task_id": 99}),
    ("add_task", {"title": "", "category": "home"}),
    ("add_task", {"title": "x", "category": "home", "time": "25:00"}),
    ("add_task", {"title": "x", "category": "home", "date": "next week"}),
    ("add_task", {"title": "x", "category": "home", "priority": "urgent"}),
    ("add_task", {"title": "x"}),  # missing required argument
    ("list_tasks", {"status": "maybe"}),
    ("no_such_tool", {}),
])
def test_bad_input_raises_tool_error(name, args):
    with pytest.raises(ToolError):
        run_tool(name, args)


# --- preferences (memory) ---

def test_preferences_persist_and_filter(clean_data):
    run_tool("save_preference", {"text": "I work out in the morning", "category": "fitness"})
    run_tool("save_preference", {"text": "No studying after 22:00", "category": "study"})
    run_tool("save_preference", {"text": "Lives in Jerusalem"})
    assert run_tool("save_preference", {"text": "i work out in the morning"}).startswith("already")

    fitness = run_tool("get_preferences", {"category": "fitness"})
    assert "morning" in fitness and "Jerusalem" in fitness  # general prefs always included
    assert "studying" not in fitness
    assert run_tool("get_preferences", {"query": "22:00"}) == "#2 [study] No studying after 22:00"
    assert len(read(clean_data, "preferences")["preferences"]) == 3


# --- Jewish calendar (network mocked; items trimmed from real Hebcal responses) ---

SHABBAT_ITEMS = [
    {"title": "Candle lighting: 16:11", "date": "2026-10-30T16:11:00+02:00", "category": "candles",
     "memo": "Parashat Vayera"},
    {"title": "Parashat Vayera", "date": "2026-10-31", "category": "parashat",
     "leyning": {"torah": "Genesis 18:1-22:24"}},
    {"title": "Havdalah: 17:28", "date": "2026-10-31T17:28:00+02:00", "category": "havdalah"},
]
PESACH_ITEMS = [
    {"title": "Biur Chametz", "date": "2027-04-21T11:33:00+03:00", "category": "zmanim"},
    {"title": "Erev Pesach", "date": "2027-04-21", "category": "holiday", "subcat": "major"},
    {"title": "Candle lighting: 18:31", "date": "2027-04-21T18:31:00+03:00", "category": "candles"},
    {"title": "Pesach I", "date": "2027-04-22", "category": "holiday", "subcat": "major",
     "yomtov": True},
    {"title": "Havdalah: 19:51", "date": "2027-04-22T19:51:00+03:00", "category": "havdalah"},
]


def fake_hebcal(items):
    calls = []

    def fetch(url, params):
        calls.append(params)
        return {"items": items}
    return fetch, calls


def test_calendar_week_with_shabbat(monkeypatch):
    fetch, calls = fake_hebcal(SHABBAT_ITEMS)
    monkeypatch.setattr(jewish_calendar, "fetch_json", fetch)
    out = run_tool("get_jewish_calendar", {"start": "2026-10-28", "end": "2026-11-01"})
    assert out.splitlines() == [
        "Jerusalem times.",
        "2026-10-30 Fri: candle lighting 16:11: tasks must end before it",
        "2026-10-31 Sat: Shabbat (Vayera), no tasks until havdalah 17:28",
        "other 3 day(s): regular",
    ]
    assert calls[0]["start"] == "2026-10-28" and calls[0]["geonameid"] == 281184


def test_calendar_holiday_eve_and_yom_tov(monkeypatch):
    monkeypatch.setattr(jewish_calendar, "fetch_json", fake_hebcal(PESACH_ITEMS)[0])
    out = run_tool("get_jewish_calendar", {"start": "2027-04-21", "end": "2027-04-22"})
    assert out.splitlines()[1:] == [
        "2027-04-21 Wed: Erev Pesach, candle lighting 18:31: tasks must end before it",
        "2027-04-22 Thu: Pesach I - yom tov, no tasks until havdalah 19:51",
    ]


def test_calendar_is_compact(monkeypatch):
    raw = [dict(i, leyning={"torah": "x" * 500}, memo="y" * 500) for i in SHABBAT_ITEMS]
    monkeypatch.setattr(jewish_calendar, "fetch_json", fake_hebcal(raw)[0])
    out = run_tool("get_jewish_calendar", {"start": "2026-10-28", "end": "2026-11-01"})
    assert len(out) < 200 and "Genesis" not in out and "xxx" not in out


def test_calendar_regular_day_and_saturday_default(monkeypatch):
    monkeypatch.setattr(jewish_calendar, "fetch_json", fake_hebcal([])[0])
    assert run_tool("get_jewish_calendar", {"start": "today"}) == "Jerusalem times. all days regular"
    # Even with no data, a Saturday is Shabbat.
    assert "Shabbat, no tasks all day" in run_tool("get_jewish_calendar", {"start": "2026-10-31"})


@pytest.mark.parametrize("args,msg", [
    ({"start": "2026-11-05", "end": "2026-11-01"}, "before start"),
    ({"start": "2026-10-01", "end": "2026-12-01"}, "too long"),
])
def test_calendar_bad_range(monkeypatch, args, msg):
    monkeypatch.setattr(jewish_calendar, "fetch_json", fake_hebcal([])[0])
    with pytest.raises(ToolError, match=msg):
        run_tool("get_jewish_calendar", args)


def test_calendar_service_error(monkeypatch):
    monkeypatch.setattr(jewish_calendar, "fetch_json", lambda url, params: {"error": "bad geonameid"})
    with pytest.raises(ToolError, match="calendar error"):
        run_tool("get_jewish_calendar", {"start": "today"})


def test_every_tool_has_schema():
    for t in TOOLS:
        assert t["input_schema"]["type"] == "object" and t["description"]
