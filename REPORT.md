# Daily Task Manager: API vs SDK

Authors: נחמי אשלג, אפרת שטראוס

> **The API run is SIMULATED. No real model calls were made.**
>
> **Why:** a real API run requires a paid Anthropic API key, and we chose not to pay for one.
> The SDK version runs on a Claude Code login at no extra cost, so its run is real.
>
> **What the simulation shows:** the API harness works end to end.
> `API/simulated_client.py` replaces only the model, with scripted responses modelled on what
> the real model did in the SDK run. Everything else ran for real:
> - all 8 harness files (loop, tools, history, memory, context, compaction, caching, tokens),
>   each printing its file name;
> - all shared tools, including the live Hebcal call;
> - all 13 scenario checks, which pass;
> - the 52 offline tests, which pass.
>
> **What is missing:** real API numbers. We have no real API tokens, cache rate or cost, and no
> real model behavior for the API version. **The numeric API vs SDK comparison therefore cannot
> be made.** The API numbers in the tables are estimates that illustrate the harness mechanics
> only:
> - Tokens are counted as characters / 4, with a simple prefix-cache model.
> - The tool calls are scripted, not model decisions.
> - The API's 13/13 shows that the harness carries out the scripted behavior correctly, not how
>   the model would behave.
> - Line counts are real for both versions. The simulation helper is not counted.
> - The compaction threshold was lowered from 30,000 to 2,400 for the simulated run only, so
>   that compaction runs once.
> - `results/api.json` is marked `"simulated": true`.
>
> **Real run, once a key is available:** one command, which runs the scenario twice and reports
> the second (warm-cache) run, matching how the SDK result was measured:
> `python API/main.py --scenario scenario.json --out results/api.json --warm`
>
> The SDK numbers are real, from run C (2026-10-25), which **ran with a warm prompt cache** (see
> "Cross-run caching").
>
> The code and most of this report were written with Claude Code under our direction. We made
> the design decisions (agent, tools, Hebcal, scenario, simulated API run) and wrote section 5
> ourselves.

## Setup

- **Agent:** plans a student's day. Tasks have a category (study, fitness, home, personal, ...),
  date, start time, duration, priority and status.
- **Tools (`shared/`, used by both versions):**
  - `add_task`, `list_tasks`, `complete_task`
  - `save_preference`, `get_preferences` (memory)
  - `get_jewish_calendar`: the external tool. It calls Hebcal for Shabbat and holidays with
    candle-lighting and havdalah times, so the agent avoids Shabbat and ends Friday tasks before
    candle lighting.
- **Memory:** preferences are saved to `preferences.json` and loaded in a new session.
  - API: the relevant preferences are injected into each turn's `<context>` block.
  - SDK: all preferences are written to `CLAUDE.md`, loaded with `setting_sources=["project"]`.
- **Model:** `claude-opus-5-5`, effort `medium`, adaptive thinking, in both versions. No model
  fallback is configured in either.
- **Libraries:** `anthropic==2.3.0`, `claude-agent-sdk==0.2.174` (bundled Claude Code
  2.1.310), `requests==2.34.2`, `truststore==0.10.5`.
- **Scenario (`scenario.json`):** 8 turns in 2 sessions, 13 pass/fail checks, of which 10 check
  saved state. The date is pinned to 2026-10-28 (Wednesday) so both runs see the same calendar
  data. Session 2 runs on a new agent instance that knows only what is on disk.

## 1. Results: API vs SDK

**No numeric API vs SDK comparison is possible here.** The API run is simulated, because a real
run requires a paid API key and we chose not to pay for one. Its token, cache and cost numbers
are estimates and its tool calls are scripted. Only the SDK column holds real measurements.

| Metric | API (**simulated**) | SDK (real, warm cache) |
|---|---|---|
| Input tokens (uncached) | 829 _(est., not comparable)_ | 2,461 |
| Cache read tokens | 26,973 _(est., not comparable)_ | 70,155 |
| Cache write tokens | 3,413 _(est., not comparable)_ | 4,036 |
| Output tokens | 3,196 _(est., not comparable)_ | 3,638 |
| Cache hit (% of prompt tokens) | 86.4% _(est., not comparable)_ | 91.5% |
| Model calls | 18 _(scripted; includes 1 compaction call)_ | 18 |
| Tool calls | 11 _(scripted)_ | 16 |
| Cost (USD) | $0.0897 _(from estimates, not comparable)_ | $0.1075 |
| Wall time | 1.4 s _(no model latency, not comparable)_ | 55.3 s |
| Checks passed | 13/13 _(scripted behavior, see note)_ | 13/13 |

The SDK costs come from `total_cost_usd`. The SDK ran on a personal Claude Code login, so this is the
cost Claude Code reports, not money charged to an API key. The SDK totals also include Claude
Code's own `claude-haiku-5-5` calls (see section 3).

**Compaction threshold: lowered to 2,400 for the simulated run only.** The harness default
(`COMPACT_THRESHOLD` in `API/agent.py`) is 30,000 prompt tokens, and a real API run uses that
value. A run of this scenario stays far below 30,000 and would not compact. In the simulation
the threshold was set to 2,400 estimated tokens (`SIMULATED_COMPACT_THRESHOLD` in `API/main.py`),
so `compaction.py` runs once, before s1-5. `results/api.json` records the value used as
`compact_threshold`.

### Per turn

API columns are **simulated** (scripted tool calls, estimated tokens). SDK columns are real.
As in the table above, the two sides cannot be compared turn by turn.

| Turn | Request | API* in / cache read / cache write / out | API* calls | API* tools | SDK in / cache read / cache write / out | SDK calls | SDK $ | SDK s | SDK tools |
|---|---|---|---|---|---|---|---|---|---|
| s1-1 | add two study tasks | 0 / 1,363 / 1,573 / 414 | 2 | add_task ×2 | 1,239 / 8,558 / 885 / 1,321 | 3 | 0.0239 | 11.0 | get_jewish_calendar, list_tasks, add_task ×2 |
| s1-2 | save two preferences | 0 / 3,281 / 303 / 367 | 2 | save_preference ×2 | 4 / 7,421 / 514 / 238 | 2 | 0.0104 | 4.0 | save_preference ×2 |
| s1-3 | Algorithms review Fri + Sat | 0 / 5,989 / 353 / 544 | 3 | get_jewish_calendar, add_task | 6 / 13,104 / 961 / 799 | 3 | 0.0263 | 10.0 | get_jewish_calendar, list_tasks ×2, add_task |
| s1-4 | "Yes, go ahead." | 0 / 4,589 / 249 / 340 | 2 | add_task | 4 / 10,459 / 584 / 353 | 2 | 0.0138 | 4.6 | add_task |
| s1-5 | mark Statistics review done | 829 / 4,249 / 341 / 659 | 4 (incl. compaction) | list_tasks, complete_task | 4 / 11,509 / 267 / 110 | 2 | 0.0067 | 3.5 | complete_task |
| s2-1 | recall plan + preferences | 0 / 2,643 / 195 / 347 | 2 | list_tasks | 1,196 / 5,745 / 0 / 271 | 2 | 0.0062 | 6.4 | list_tasks, get_preferences |
| s2-2 | 20:00 workout (conflict) | 0 / 1,474 / 147 / 178 | 1 | - | 2 / 3,023 / 205 / 179 | 1 | 0.0058 | 3.7 | - |
| s2-3 | confirm one-time exception | 0 / 3,385 / 252 / 347 | 2 | add_task | 6 / 10,336 / 620 / 367 | 3 | 0.0144 | 12.2 | get_jewish_calendar, add_task |

\* Simulated. The API tool sequences were written by hand and are not model decisions. For
example, the simulated s2-1 skips `get_preferences` because the API's `<context>` block
already carries the relevant preferences; a real model might still call it.

The SDK token columns cover every model Claude Code ran in that turn. The large uncached input
in s1-1 and s2-1 is the Haiku call (about 1.2k tokens each); Opus itself had 4-6 uncached
tokens in every turn.

## 2. Lines of code per harness part

Counted by `shared/scenario.py`: non-blank lines, excluding comments and docstrings. For the
SDK, a part's count is the code lines marked `# replaces: <part>.py`, where a marker on a `def`
line counts the whole function.

| Part | API (`API/harness/`) | SDK | Notes |
|---|---|---|---|
| loop | 26 | 2 | `client.query()` + `receive_response()` |
| tools | 26 | 12 | `@tool` wrappers + `create_sdk_mcp_server`; the schemas come from `shared/registry.py` in both versions |
| history | 43 | 2 | `resume=session_id`; Claude Code keeps the transcript |
| memory | 22 | 7 | writes `CLAUDE.md` from `preferences.json` at session start |
| context | 24 | 1 | system prompt only; the model fetches tasks with tools |
| compaction | 33 | 0 | automatic |
| caching | 14 | 0 | automatic |
| tokens | 44 | 34 | Claude Code reports running totals across several models, so per-turn numbers need almost as much code as `tokens.py` |
| **Total** | **232** | **58** | |

The API total covers only the 8 files in `API/harness/`.

**Glue code outside the parts:**
- API: `agent.py` 35 + `main.py` 92 + `harness/log.py` 2.
- SDK: `agent.py` 106 + `main.py` 123 + `tools.py` 17. These include the marked lines above.
- `shared/` (domain code, identical for both): 312 lines, not counting the scenario runner.

**Not counted anywhere:** `API/simulated_client.py` (137 lines). It is a test tool for the
simulated run without an API key, not part of the API harness or its glue code. `results/api.json`
lists it separately under `loc.test_tools_not_counted`.

## 3. Where did the SDK use more tokens, where fewer, and why?

**The numeric comparison is not available.** Answering this question needs real API numbers:
tokens, cache rate, cost and model behavior. Our API run is simulated, because a real run
requires a paid API key and we chose not to pay for one. With a key, the single command in
the top note (`--warm`) would produce those numbers. The findings below are from the real SDK
run.

- **Prompt per call.** Each Opus call in the SDK read about 3-5k prompt tokens: system
  prompt + 6 tool schemas + `CLAUDE.md` + Claude Code's own additions (s2-2, a single call,
  read 3,230 tokens). The API version's real prompt size per call is not available (simulated
  run).
- **Extra model.** Claude Code adds one `claude-haiku-5-5` call on the first turn of every new
  session (about 1.2k input, 25-588 output, under $0.0005). It runs outside the conversation
  stream (no `AssistantMessage`), so it is a background helper, not a fallback.
- **Context strategy.** In s1-1 the SDK agent called `list_tasks` and `get_jewish_calendar`
  before adding tasks. In the SDK the model has to fetch tasks itself. The API version pushes
  today's tasks and the relevant preferences into each turn instead. Whether that saves model
  calls cannot be measured from the simulated run, whose API tool calls are hand-written.
- **Caching.** 91.5% of the SDK's prompt tokens were cache reads. Part of this comes from
  earlier runs (see "Cross-run caching" below), so this figure is not a pure property of the SDK.

## 4. What control did we have in the API that we lost in the SDK?

These points come from the real SDK runs and from the API code. None of them depends on API
token numbers, so the simulated API run does not limit them.

- **Injected context.** Claude Code added the machine's real date (2026-10-25) to the
  conversation as an `attachment` of type `date`, next to the pinned scenario date
  (2026-10-28) in our system prompt. We could not turn this off. The agent still followed the
  system prompt: in every reply, "tomorrow" was Thursday 2026-10-29. This was found by
  scanning Claude Code's transcript files; we cannot see the full request Claude Code sends,
  so other additions may exist.
- **Extra model calls.** The Haiku calls above are made and billed without being requested.
- **Caching and compaction.** In the API we choose the `cache_control` breakpoints and the
  compaction threshold, and we can test compaction offline with a low threshold (a test does
  this). In the SDK both are automatic and not configurable from the options we used.
- **Usage reporting.** The API returns usage per call. The SDK returns running totals per
  connection across models, and `AssistantMessage.usage` undercounts output tokens (it is read
  mid-stream: 13 output tokens recorded vs 799 actual in s1-3). Getting correct per-turn numbers
  took 34 lines of code.
- **Per-turn context.** In the API we decide exactly what each turn contains (today's tasks and
  only the preferences relevant to the message). In the SDK, `CLAUDE.md` is loaded once per
  session with all preferences, and anything else the model must fetch with tools.

## 5. Which version would we choose for this agent, and why?

<div dir="rtl">

**היינו בוחרות בגרסת ה-API.**

הסיבה העיקרית היא שליטה. בריצות ה-SDK ראינו ש-Claude Code מקבל החלטות בעצמו: הוא הפעיל מודל נוסף (Haiku) שלא ביקשנו, והכניס לקונטקסט את התאריך האמיתי של המחשב, למרות שקבענו תאריך אחר. בגרסת ה-API שום דבר לא נשלח למודל בלי שהקוד שלנו שלח אותו, ואנחנו יודעות בדיוק מה המודל רואה בכל תור.

סיבה נוספת היא שאולי גם אחרים ישתמשו בסוכן. ה-SDK רץ על ה-login האישי שלנו, ולכן הוא מתאים לשימוש אישי. API עם מפתח מאפשר לשתף את הסוכן.

הוויתור הוא בכמות הקוד: 232 שורות ב-harness של ה-API מול 58 ב-SDK, ואת compaction ו-caching צריך לכתוב ולתחזק בעצמנו. אנחנו מוכנות לשלם את המחיר הזה תמורת השליטה.

אם הסוכן היה מיועד רק לנו, או אם היינו רוצות לבנות אב-טיפוס מהר, היינו בוחרות ב-SDK. הוא עבר את כל 13 הבדיקות עם רבע מכמות הקוד, ורץ על המנוי בלי עלות נוספת.

</div>

## Methodology notes

### Scenario and check revisions

The scenario and its checks changed during development. Each change was made to both versions
at once. The final results in `results/api.json` (simulated) and `results/sdk.json` (real)
come from the same final scenario. Runs A-C below are SDK runs.

| Run | Scenario | Result (SDK) | What happened in s1-3 | Change made afterwards |
|---|---|---|---|---|
| A | Hebrew prompts, 7 turns, 11 checks | 10/11 | Called `get_jewish_calendar`, proposed Fri 09:00-12:00 and Sat 18:00-21:00 (after havdalah), booked nothing and asked for confirmation. `friday_prep_before_candles` failed. | Prompts translated to English (same meaning). Added a fixed turn s1-4 "Yes, go ahead." so a proposal can be confirmed, and a `no_duplicates` check so the confirmation cannot re-book. |
| B | English prompts, 8 turns, 13 checks | 12/13 | Booked Friday 10:00-13:00 right away (ends before candle lighting at 16:11) and asked only about the Saturday part. After "Yes, go ahead." it booked Sat 18:00-21:00. `asked_before_booking` failed. | `asked_before_booking` revised (see below). |
| C | English prompts, 8 turns, 13 checks (final) | **13/13** | Booked Friday 09:00-12:00 right away and asked only about the Saturday part. After "Yes, go ahead." it booked Sat 18:00-21:00 (after havdalah at 17:28, before the 22:00 study cutoff). No duplicates. | None. Run C is the reported SDK result. |

**Why `asked_before_booking` was revised.** Its first version required that *no* Friday task
exist after s1-3. That was stricter than the agent's actual rule. Friday before candle lighting
is an allowed time, so booking it immediately breaks nothing. The rule ("if a requested time
falls on Shabbat, say so and offer the nearest allowed time instead of booking it") applies
only to the Saturday part. The revised check tests exactly that: after s1-3, and before the
confirmation, no Algorithms task exists outside Friday.

The revised check matches on the task title (`"algo"`). This works because the system
prompt makes the agent name tasks in English.

### Non-determinism

Under the same model (`claude-opus-5-5`), effort (`medium`) and system prompt, the agent chose
two different, equally valid policies for s1-3:
- run A: propose everything and ask first;
- runs B and C: book what is allowed now and ask only about the conflicting part.

Even between B and C, which had identical inputs, the Friday slot differed (10:00 vs 09:00).

Runs A and B are not a clean repeat of each other: A used Hebrew prompts and B used English
ones, so part of that difference may come from the language. Even so, the checks are written to
accept any behavior that follows the rules rather than one specific path, because a single run
of each version cannot show which behavior is typical. Each version was run once on the final
scenario, so differences between API and SDK on these turns may be partly run-to-run variance.

### Cross-run caching

In run C, s2-1 cost $0.0062, about a third of the same turn in run B. (Run B's results file was
overwritten by run C, so B's exact numbers are not reproduced here.) The cause is the prompt
cache, not anything the agent did differently:

- s2-1 is the first request of a brand-new Claude Code session, yet it wrote **0** tokens to
  the cache and Opus had only 4 uncached input tokens. Everything else (5,745 tokens over 2
  calls) was a cache read.
- That is only possible if an identical prefix had already been cached: the system prompt,
  tools, the session-2 `CLAUDE.md`, the first message and even the second call's tool results.
  Run B's session 2 produced exactly that prefix shortly before, from the same saved state and
  the same tool calls.
- The same effect shows in s1-1:
  - Run A (cold, because the system prompt had changed since the previous run): 2,731 cache
    read and 3,463 cache write.
  - Run C: 8,558 cache read and 885 cache write.

Implication: the numbers depend on what ran shortly before. "Each run starts from a clean
state" holds for the data on disk, not for the server-side prompt cache.

**Decision: warm cache for both versions.** Run C is reported as-is and ran warm (run B had run
just before it with the same scenario). A real API run uses `--warm`: it runs the scenario
twice and reports the second run, so both versions are measured the same way.

### Simulated API run

`python API/main.py --scenario scenario.json --out results/api.json --simulate`

- **The model is replaced, nothing else.** `API/simulated_client.py` stands in for
  `anthropic.Anthropic()`. For each scenario request it returns a fixed sequence of responses
  (thinking block, tool calls, final text), written to match what the real model did in SDK
  run C. The harness then runs unchanged: tool calls go through `tools.py` to the real shared
  tools, history is written and replayed, context and memory are built per turn, and
  `caching.py` places the breakpoints.
- **Token estimates.** Usage is estimated as characters / 4, plus the 286-token tool overhead
  from the pricing page and 120 pretend thinking tokens per response. A simple server-cache
  model stores prefixes at the breakpoints `caching.py` sets (512-token minimum) and reports
  reads and writes from them. That is why the estimated cache hit is high: the mechanism is
  real, but the token counts are not.
- **Compaction forced once.** The threshold was lowered to 2,400 so `compaction.py` summarizes
  session 1 before s1-5. A real run would not compact.

### Run files

Every run also writes a timestamped copy under `results/runs/` (e.g.
`sdk-<time>.json`, `api-simulated-<time>.json`), so earlier runs are no longer overwritten.
Runs A and B predate this and are not kept.
