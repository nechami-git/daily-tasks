"""External tool: get_jewish_calendar via Hebcal (free, no API key).

Hebcal returns long JSON (Torah readings, memos, links). We keep only what a
planner needs and return one line per special day.
"""
from datetime import date, timedelta

import requests

from . import storage
from .storage import ToolError

HEBCAL_URL = "https://www.hebcal.com/hebcal"
JERUSALEM = 281184  # GeoNames id; Hebcal applies Jerusalem's 40-minute candle-lighting custom
MAX_DAYS = 31


def fetch_json(url: str, params: dict) -> dict:
    """The only network call. Tests replace this function."""
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        # Short message: this text goes back to the model, so keep it cheap.
        raise ToolError(f"calendar service unavailable ({type(e).__name__})")


def _parse(items: list[dict]) -> dict[str, dict]:
    days: dict[str, dict] = {}
    for it in items:
        d = days.setdefault(it["date"][:10], {"events": [], "yomtov": False})
        cat = it.get("category")
        if cat == "candles":
            d["candles"] = it["date"][11:16]
        elif cat == "havdalah":
            d["havdalah"] = it["date"][11:16]
        elif cat == "parashat":
            d["parasha"] = it["title"].removeprefix("Parashat ")
        elif cat == "holiday":
            d["events"].append(it.get("title_orig", it["title"]))
            d["yomtov"] |= bool(it.get("yomtov"))
    return days


def _line(day: date, info: dict) -> str | None:
    shabbat = day.weekday() == 5
    rest = shabbat or info["yomtov"]
    parts = []
    if shabbat:
        parts.append("Shabbat" + (f" ({info['parasha']})" if info.get("parasha") else ""))
    parts += [e + (" - yom tov" if info["yomtov"] else "") for e in info["events"]]
    if rest:
        if info.get("havdalah"):
            parts.append(f"no tasks until havdalah {info['havdalah']}")
        else:
            parts.append("no tasks all day")
    if info.get("candles"):
        parts.append(f"candle lighting {info['candles']}" +
                     (" (rest continues)" if rest else ": tasks must end before it"))
    if not parts:
        return None
    return f"{day.isoformat()} {day.strftime('%a')}: " + ", ".join(parts)


def get_jewish_calendar(start: str = "today", end: str | None = None) -> str:
    first = date.fromisoformat(storage.resolve_date(start))
    last = date.fromisoformat(storage.resolve_date(end)) if end else first
    if last < first:
        raise ToolError("end is before start")
    if (last - first).days >= MAX_DAYS:
        raise ToolError(f"range too long: at most {MAX_DAYS} days")

    data = fetch_json(HEBCAL_URL, {
        "v": 1, "cfg": "json", "maj": "on", "min": "on", "mod": "off", "nx": "off",
        "ss": "off", "mf": "off", "c": "on", "s": "on", "M": "on",
        "geo": "geoname", "geonameid": JERUSALEM,
        "start": first.isoformat(), "end": last.isoformat()})
    if "error" in data:
        raise ToolError(f"calendar error: {data['error']}")

    days = _parse(data.get("items", []))
    lines, regular = [], 0
    n = (last - first).days + 1
    for i in range(n):
        day = first + timedelta(days=i)
        line = _line(day, days.get(day.isoformat(), {"events": [], "yomtov": False}))
        if line:
            lines.append(line)
        else:
            regular += 1
    if not lines:
        return "Jerusalem times. all days regular"
    if regular:
        lines.append(f"other {regular} day(s): regular")
    return "Jerusalem times.\n" + "\n".join(lines)
