# Bright — integration suite

> 293 unit tests passed while four real bugs sat in the seams between
> components. Every bug was at a boundary, and three of the four were silent —
> no exception, plausible-looking output.
>
> — [state of the project](../docs/4-build/state-of-the-project.md) §4

This suite tests the seams. It starts the **real services as real processes**,
talks to them over **real sockets**, and drives the **real UI in a real
browser**. There is no `TestClient`, no in-process app object and no fake
WebSocket anywhere in it — those are exactly the tools that let the four bugs
through.

It implements I1–I10 from [the integration test plan](../docs/4-build/tracker.md#integration-test-plan).

---

## Run it

```bash
./scripts/product-smoke.sh             # process/socket Core wire path; no browser audio
python3 tests/run.py                  # everything, ~9 min
python3 tests/run.py I1 I6            # just those
python3 tests/run.py --fast           # skip tests that play a lesson in real time
python3 tests/run.py --no-browser     # skip anything needing Chromium
python3 tests/run.py -- -k rapid      # anything after `--` goes to pytest
```

Plain `pytest` works too (`cd tests && python3 -m pytest`); the pass/fail table
is printed by a `conftest.py` hook, not by `run.py`.

The product smoke is the fastest production Core wire check: real Core with
`CORE_DEV=0`, Vite route checks, deterministic fake speech, and Python
protocol-v2 Stage + Control clients with fabricated playback ACKs. It does not
execute browser/AIRI/TTS/ASR and is not release proof. See the
[product smoke runbook](../docs/4-build/product-smoke-runbook.md). The I1-I10
suite remains the deeper seam/browser suite.

Output ends with:

```
ID    GATE  RESULT     TIME  WHAT IT PROTECTS
----------------------------------------------------------------------------
I1    GATE  PASS      55.5s  Sample lesson plays start to finish with no agent
I2    GATE  FAIL      68.2s  Agent killed mid-lesson: class continues, ...
                        ↳ test_repeats_are_capped (call)
...
RELEASE GATES FAILING: I2
```

Logs, screenshots and the raw browser results land in `tests/.artifacts/`.

### It will not disturb a running demo

Every process the suite starts binds a **freshly allocated port**; `:3000`,
`:8001`, `:8004` and `:8642` are in `RESERVED_PORTS` and are never bound and
never killed. The suite's cores write to their own SQLite files under
`tests/.artifacts/`, so the demo's memory is never touched.

Processes are stopped by the PID we spawned, or by resolving the PID from the
port. **Never `pkill -f`** — the pattern matches the suite's own command line
and kills the shell running it. Two agents lost their shell that way.

### Requirements

| | |
|---|---|
| Python | the interpreter running pytest needs `pytest`, `pytest-asyncio`, `httpx`, `websockets`, `fastapi`, `uvicorn` |
| classroom-core | `services/classroom-core/.venv` — used to run core itself (it is the only interpreter with `apscheduler`) |
| UI | `apps/classroom-ui/node_modules` installed (`pnpm install`) |
| Browser | `playwright-core` in `.tools/node_modules`, Chromium at `~/.cache/ms-playwright/chromium-1228/…` (override with `BRIGHT_CHROME`) |

No API key is needed. Nothing in the suite reaches the internet.

---

## What is actually running

```
                    ┌──────────── fake TTS ◄────── the UI's speech pipeline
   Chromium ──► UI ─┤                              (I6 reads what it was asked to say)
                    └── TCP proxy ──► core ──► TCP proxy ──► fake LLM
                          (I9 cuts)              (I9 cuts)   ("the agent")
```

Four pieces of the harness deserve an explanation, because each one exists to
make a specific test honest rather than convenient.

**`harness/servers/fake_llm.py` — the agent.** An OpenAI-compatible
chat-completions server whose SSE output a test controls frame by frame. Core
runs with `BRIGHT_AGENT=1` and `LLM_BASE_URL` pointing at it, so the real
`DirectAgent` makes real HTTP requests and the real validation and rejection
paths run. This is what lets I6 put half an ACT token in one SSE frame and half
in the next — something no mocked client can do — and what lets I2 *kill the
agent* by killing a process. Tool arguments may contain `"__STATE_VERSION__"`,
which the server replaces with the version core actually sent in the tool
schema, so a script can answer many turns as the board moves.

**`harness/servers/fake_tts.py` — what the class hears.** The UI's speech
pipeline ends at `POST /audio/speech`. This server records every such request.
"An ACT token must never be spoken aloud" is therefore assertable literally,
instead of by scraping a subtitle and hoping. It also keeps the suite off the
real Piper service.

**`harness/proxy.py` — the cable.** A raw TCP proxy with three modes: pass,
`cut()` (close everything, refuse new), and `blackhole()` (bytes are read and
dropped; **nothing is closed**). The blackhole is the important one: a cut
socket reports itself, a black-holed one does not, and only the second
resembles school wifi. It carries a small HTTP control surface so a browser
scenario can pull its own cable mid-run.

**`harness/bus.py` — a second opinion on the protocol.** A WebSocket client
written from `PROTOCOL.md` rather than copied from the UI's, so a shared
misreading cannot agree with itself. It checks on every frame that `seq` is
gap-free and that `stateVersion` never goes backwards, which means every test
that plays a lesson is also a test that the bus stayed honest for its duration.

Browser work is Node (`tests/node/*.mjs`) because playwright-core is a Node
package; each scenario prints one `@@RESULT@@ {json}` line and pytest asserts
on it.

---

## What each test protects

| # | Gate | What it protects | How it would otherwise fail |
|---|---|---|---|
| **I1** | ● | The sample lesson plays hook → vocabulary → question → wrong answer → authored scaffold → question → right answer → DONE, with **no agent object in existence** | NS-1 dies quietly: the product stops working in exactly the schools it is for |
| **I2** | ● | Killing the model endpoint mid-lesson: the class finishes, the mode degrades, a turn against a dead endpoint fails fast, and every broken-agent path falls through to the authored branch | "the facilitator console reported a healthy agent while the agent was unreachable" — §4, already shipped once |
| I3 | | A tab reloaded mid-activity resnapshots to **the same activity**, core's position does not move, and one page load opens exactly **one** WebSocket | "two WS connections, stage frozen" — §4, React lifecycle ↔ socket lifecycle |
| I4 | | An `action_id` core never offered is rejected, logged, not applied, and **not retried** (exactly one upstream call) | a repair loop in front of thirty children |
| I5 | | A decision carrying a stale `state_version` is discarded — including one that goes stale *during* the turn | the agent acts on a board that has already changed. Silent |
| **I6** | ● | An ACT token split across two SSE frames never reaches the synthesiser, and its emotion still lands | PROTOCOL §5.4.1 calls this "the single most common bug in reimplementations" |
| I7 | | Two rapid answers do not desync or double-advance; stage and console end on the same `stateVersion` | the lesson skips an activity and nobody can say why |
| I8 | | An observation written in session 1 survives a process restart and reaches session 2's greeting prompt — by name — and the class hears it | "it remembers" is the claim that separates this from courseware |
| I9 | | A silent network bounds the turn instead of hanging it; the reflex tier stays instant; the stage says something rather than freezing | risk register: "offline promise quietly dies" |
| I10 | | Tap → painted press feedback under 100 ms, measured around a real input event | NS-2's reflex tier is the whole reason the two-tier design exists |

Every test file's docstring says the same thing at more length, next to the
code.

### Deliberate design choices worth knowing

* **I1 gets its own core** with `BRIGHT_AGENT` unset. Not the shared core with
  the model unplugged — NS-1's claim is that the lesson runs when there is
  nothing to unplug, and the test asserts `/dev/agent/turn` returns 503 before
  it starts, so a future change that quietly wires an agent in cannot make it
  pass for the wrong reason.
* **Positive controls.** `test_i4` applies a *legal* action first and
  `test_i2_agent_fallbacks` proves a *healthy* agent can change the branch.
  Without them, every rejection test would also pass on a system where
  `classroom_choose_next` never works at all.
* **Non-vacuity checks.** I6 asserts TTS was called *at least once* before
  asserting nothing leaked; a pipeline that silently did nothing would
  otherwise pass.
* **Module identity.** I6's parser probe resolves the URL from the page's own
  request list. An earlier diagnostic on this project imported
  `pixi-live2d-display_cubism4.js` without the `?v=` query the app used, got a
  different module instance, and reported a working patch as broken.
  `resolveModuleUrl()` in `node/lib.mjs` exists so that cannot recur.
* **`tests/fixtures/lesson_answer_kinds.json`** is a lesson that grades
  `speech` and `drag`. The sample lesson only ever asks a `choice`, so those
  two paths had never run end to end. Nothing under `content/` or `services/`
  is modified.
* **The mode is an input, not a race.** The shared core runs with
  `CORE_PROBE_INTERVAL_S=3600`, so a background health probe can never move the
  mode in the middle of an unrelated test — and since the decision gate only
  runs in `FULL`, that would otherwise decide whether the agent participates at
  all, by wall-clock luck. Tests that care about the mode either pin it
  (`/dev/mode`) or take their own core with a live probe interval
  (`probing_core`). The `core` fixture also resets the mode and the scripted
  model reply between tests, so nothing leaks forward.

---

## Layout

```
tests/
  run.py                     one command, one table
  conftest.py                fixtures + the pass/fail table
  pytest.ini
  harness/
    procs.py                 Core / Ui / FakeLLM / FakeTTS — real processes
    net.py                   free ports, health waits, kill-by-port
    proxy.py                 the cuttable TCP link
    bus.py                   protocol-correct WS client, seq/version invariants
    browser.py               pytest → node scenario bridge
    llm_script.py            readable builders for scripted SSE
    servers/fake_llm.py      the scriptable model endpoint
    servers/fake_tts.py      what the class hears
  node/
    lib.mjs                  launch, store(), resolveModuleUrl()
    i3_reload.mjs  i6_act_split.mjs  i9_ui_offline.mjs  i10_feedback_latency.mjs
  fixtures/
    lesson_answer_kinds.json a lesson that grades speech and drag
  test_i1…test_i10           one file per plan item
  .artifacts/                logs, browser results, prompts (wiped per run)
```

## Adding a test

1. Put it in the file for the plan item it belongs to, or make a new one.
2. Tag it: `@pytest.mark.itest(id="I4", title="…", gate=False)`. The table
   groups by `id` and an id passes only when all of its tests pass.
3. Add `@pytest.mark.slow` if it plays a lesson in real time, and
   `@pytest.mark.browser` if it needs Chromium.
4. Assert on state (`window.__bright`, `/dev/state`, the recorded request), not
   on pixels or on log text — except where the log *is* the contract, as with
   the structured rejection records I4 checks for.
5. Take a `client.cursor()` before the thing you are waiting for and pass it as
   `since=`. Without it, "wait for a vocabulary scene" is satisfied by a
   vocabulary scene from three activities ago, the test races ahead of the
   lesson, and it fails only when some earlier test happens to have left one on
   the wire. That exact bug cost an afternoon here.
6. If a test fails against code you are sure you changed, clear
   `__pycache__`. The repo lives on a Windows drive under WSL and mtime
   granularity is coarse enough to match a stale `.pyc`; `run.py` sets
   `PYTHONDONTWRITEBYTECODE=1` for this reason.

---

## Known failures at time of writing (2026-08-11)

These are product defects the suite found, not suite problems. Each is
deliberately left failing — a red test is the only durable form of a bug
report.

| Test | Defect |
|---|---|
| `test_i7_rapid_interactions::test_two_different_answers_do_not_both_grade`<br>`…::test_tap_during_the_reveal_hold_does_not_advance_again` | A second tap on an already-answered question **re-grades it**. `runner.handle_interaction` sets `self.answered = True` but nothing ever reads it. The last tap wins: the board re-reveals, a second observation is written, and the branch taken is the one for the *later* answer. |
| `test_i2_agent_fallbacks::test_repeats_are_capped` | Nothing counts consecutive `repeat_activity` decisions. An agent stuck on "again" repeats the same activity forever, ~1,500 prompt tokens a cycle. Reproduced 6/6 with the lesson never moving. |
| `test_i5_stale_state_version::test_every_graded_answer_moves_the_state_version` | A graded `drag` does not move `state_version`, so an agent decision computed for the previous answer still validates as current. `runner._reveal` bumps the version only for `choice` and `vocabulary/point`. |

Two things the suite found that are **not** test failures, and are worth knowing:

* `/dev/agent/turn` reports every rejection as `"agent reported error"`. The
  structured reason (`unknown_action_id`, `stale_state_version`, …) survives
  only in core's log, so nothing downstream — including the facilitator console
  — can say *why* a proposal was refused. I4 asserts on the log for this reason.
* The stage has **no liveness check of its own**. On a link that goes silent it
  keeps reporting `connection.state === 'open'` until the server's ping timeout
  closes the socket and that close reaches it — measured at ~32 s of frozen
  board. On a route that also swallows the FIN, nothing in the client would ever
  fire.
