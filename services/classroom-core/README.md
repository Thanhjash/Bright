# classroom-core

The centre of the system: **the only writer of state**, and the tier that keeps
teaching when the model is gone (NS-1). It holds the Scene, the LessonPosition
and the Mode, owns the WebSocket event bus, grades interactions, and plays a
compiled `lesson_run.json` from beginning to end.

**No LLM call is made anywhere in this service.** The agent is a seam
(`scheduler.AgentSeam`) whose callables default to no-ops and are injected at
startup by whoever owns `services/agent`.

Wire format: [`packages/contracts/PROTOCOL.md`](../../packages/contracts/PROTOCOL.md).
Models are imported from `bright_contracts`, never redefined.

---

## Run it

```bash
cd services/classroom-core
uv sync                       # creates .venv, installs deps + dev group
uv run python app.py          # http://127.0.0.1:8004
```

With plain pip:

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install "fastapi>=0.115" "uvicorn[standard]>=0.32" websockets "pydantic>=2.9" "apscheduler>=3.10,<4"
pip install pytest pytest-asyncio httpx      # tests only
python app.py                 # or: uvicorn app:app --host 127.0.0.1 --port 8004
```

Tests:

```bash
uv run pytest -q              # 88 tests, ~12s, no mocked sqlite
```

The service binds `127.0.0.1` only — that is not configurable.

`bright_contracts` lives at `packages/contracts/python`, which has no
`pyproject.toml`, so `config.py` puts it on `sys.path` at import time (override
with `BRIGHT_CONTRACTS_PATH`). Import `config` before `bright_contracts` in any
new module. `pytest` gets the same path from `[tool.pytest.ini_options]`.

---

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | `{status, mode, stateVersion}` |
| `WS` | `/ws` | the event bus — see below |
| `GET` | `/assets/{path}` | serves `ASSETS_DIR`; traversal and misses are a clean 404 |
| `POST` | `/dev/scene` | **dev** push a Scene straight onto the board |
| `POST` | `/dev/say` | **dev** push a `speech.say` (+ optional `avatar.act`) |
| `POST` | `/dev/cancel?turn_id=` | **dev** push `speech.cancel` |
| WS event | `lesson.start` | **production**, Control-only `{requestId,index?,studentId?,studentName?}`; idempotent reply `lesson.started` |
| `POST` | `/dev/lesson/start` | **dev** HTTP shortcut for the same start behavior |
| `POST` | `/dev/lesson/control` | **dev** `{cmd, arg?}` — pause/resume/skip/repeat/back/takeover/goto |
| `POST` | `/dev/interaction` | **dev** `{type, payload}` — grade an interaction over HTTP |
| `POST` | `/dev/mode` | **dev** `{mode, reason?}` — force FULL/DEGRADED/OFFLINE |
| `GET` | `/dev/lesson` | **dev** the loaded `LessonRun` as camelCase JSON |
| `GET` | `/dev/state` | **dev** mode, stateVersion, runner position, jobs, last 20 frames |
| `GET` | `/dev/recall?q=&k=` | **dev** FTS recall, the read side of `classroom_recall` |
| `GET` | `/dev/agent/actions` | **dev** the option set core would offer right now — no model involved |
| `POST` | `/dev/agent/turn` | **dev** `{lastInteraction?, studentId?, recallQuery?, only?}` — one turn by hand |
| `POST` | `/dev/session/summarize` | **dev** `{sessionId}` — run `summarize_session` now instead of in 30 s |

`/dev/*` exists so the UI can be built before the agent does. Set `CORE_DEV=0`
to remove the routes entirely (they 404).

The production boundary is exercised without a TestClient or API secret by:

```bash
./scripts/product-smoke.sh
```

It starts Core with `CORE_DEV=0`, performs the Control-only `lesson.start`,
checks Stage-only playback acknowledgements, and requires the authored lesson
to finish while Hermes is absent. See the
[product smoke runbook](../../docs/archive/product-smoke-runbook.md).

### `/ws`

1. Connect. The client sends `client.hello` **first** — anything else, or a
   `v` that is not `2`, closes the socket (`4400` / `4426`); silence for
   `CORE_HELLO_TIMEOUT_S` closes it with `4408`.
2. The server replies `scene.snapshot` = `{scene, lesson}`, always a full
   snapshot. A `stateVersion` in the hello is a reason to *take* a snapshot,
   never a reason to skip one.
3. Everything after that is a stream of envelopes. `seq` is monotonic **per
   connection** starting at 1 and never has a gap: if a client's outbound queue
   overflows the socket is closed (`1011`) so it reconnects and re-snapshots.
4. Client→server: `interaction.choice` / `.point` / `.drag`,
   `student.speech.final`, `control.command`, and `client.hello` again (which
   re-sends the snapshot). Unknown types get an `error` frame, not a close.

Everything on the wire is camelCase (`model_dump(by_alias=True)`), including
models nested inside `payload`.

### Dev examples

```bash
curl -s localhost:8004/health

curl -s localhost:8004/dev/scene -H 'content-type: application/json' -d '{
  "kind": "vocabulary",
  "props": {"items":[{"id":"cat","text":"cat","asset":"asset://animals/cat.svg"}],
            "interaction":"tap"}}'

curl -s localhost:8004/dev/say -H 'content-type: application/json' \
     -d '{"text":"Hello everyone!","act":{"emotion":"happy","motion":"Happy"}}'

curl -s -XPOST localhost:8004/dev/lesson/start -H 'content-type: application/json' -d '{"index":2}'
curl -s localhost:8004/dev/interaction -H 'content-type: application/json' \
     -d '{"type":"interaction.choice","payload":{"optionId":"cat"}}'
```

> `/dev/scene` and the lesson runner both write the Scene. If the runner is
> mid-lesson its next activity overwrites your hand-pushed scene — that is
> expected. Push scenes with the runner stopped, or drive the runner instead.

---

## Environment

Read from `os.environ` with defaults; the process manager loads `.env`, this
service never reads it. Paths are resolved against the repo root when relative.

| Var | Default | Meaning |
|---|---|---|
| `CORE_PORT` | `8004` | listen port (host is always `127.0.0.1`) |
| `ASSETS_DIR` | `services/classroom-core/assets` | served at `/assets/{path}` |
| `DATA_DIR` | `services/classroom-core/data` | writable data root |
| `CORE_DB_PATH` | `$DATA_DIR/bright.db` | SQLite file (WAL) |
| `CORE_LESSON_RUN` | `data/sample_lesson_run.json` | the `LessonRun` to play |
| `CORE_DEV` | `1` | expose `/dev/*` |
| `CORE_AUTOSTART_LESSON` | `0` | start the runner at boot |
| `CORE_MODE` | *(unset)* | pin `FULL`/`DEGRADED`/`OFFLINE`, disables probing |
| `CORE_HELLO_TIMEOUT_S` | `10` | how long to wait for `client.hello` |
| `CORE_QUEUE_MAXSIZE` | `512` | per-connection outbound queue |
| `CORE_SILENCE_TIMEOUT_S` | `15` | idle wait before a `silence` outcome |
| `CORE_REVEAL_HOLD_S` | `1.2` | how long the answer reveal stays before branching |
| `CORE_FULL_MAX_LATENCY_S` | `3` | below this the agent drives (FULL) |
| `CORE_DEGRADED_MAX_LATENCY_S` | `10` | above this it is OFFLINE |
| `CORE_RECOVER_AFTER` | `2` | consecutive good probes needed to improve mode |
| `CORE_PROBE_INTERVAL_S` | `60` | `health_probe` period |
| `CORE_SUMMARY_DELAY_S` | `30` | delay before `summarize_session` |
| `AGENT_TURN_TIMEOUT_S` | `6` | how long a graded outcome waits for the agent before taking the authored branch |
| `AGENT_GREETING_TIMEOUT_S` | `2 x` the above | bound on the greeting turn, which nobody is waiting on a board for |
| `BRIGHT_AGENT` | `off` | `hermes` = Option B primary; `scripted` = rehearsal; `direct` = compatibility; `off` = authored lesson (legacy `1` maps to `direct`) |
| `AGENT_CONTEXT_POLICY` | `hosted-minimal` | pseudonymous current-turn context; use `local-trusted` only after the model endpoint is local |
| `BRIGHT_MCP_TOKEN` | empty | enables the authenticated Hermes→Core MCP surface when non-empty |
| `CORE_PLAYBACK_ACK_TIMEOUT_S` | `10` | fail-safe release when Stage never acknowledges authored playback |
| `CORE_PREPARE_NEXT_HOUR` | `3` | UTC hour for the nightly `prepare_next` |
| `CORE_CORS_ORIGINS` | localhost `$UI_PORT`+`5173` | comma-separated |
| `BRIGHT_CONTRACTS_PATH` | *(auto)* | override the contracts import path |

`TTS_*` and `HERMES_*` from `.env.example` are deliberately unused here. `LLM_*`
is read by `services/agent`, not by this service: classroom-core still makes no
model call of its own — everything model-shaped goes through the object
`agent_bridge` is handed at startup.

---

## Modules

| File | Role |
|---|---|
| `app.py` | FastAPI: health, `/ws`, assets, dev endpoints, lifespan wiring |
| `bus.py` | pub/sub; per-connection `seq`, global `stateVersion`, camelCase framing |
| `state.py` | the store: Scene + LessonPosition + Mode, one writer, `snapshot()` |
| `db.py` | SQLite schema (docs/archive/phase-1-plan.md §5) + FTS5 `recall()` |
| `runner.py` | the reflex tier: render, narrate, grade, branch, auto-advance |
| `modes.py` | FULL/DEGRADED/OFFLINE from measured agent latency |
| `scheduler.py` | apscheduler jobs + `AgentSeam` (the only place an agent plugs in) |
| `agent_bridge.py` | the seam: option set, `TurnContext`, tool executor, the automatic turn, the real summariser |
| `data/sample_lesson_run.json` | throwaway A1 animals lesson, 6 activities |
| `assets/animals/*.svg` | placeholder art so `asset://` resolves to something |

### The agent seam

```python
from scheduler import AgentSeam

core = app.state.core                      # set during lifespan
core.set_agent_seam(AgentSeam(
    summarize_session=my_summarizer,       # (session_id, observations) -> dict | None
    prepare_next=my_planner,               # (context) -> dict | None
    probe=my_latency_probe,                # () -> seconds | None
))
```

`summarize_session` returning `{summary, weakPoints, nextFocus, studentId?,
skills?}` is written to `session_summaries` and indexed for recall. Every seam
call is wrapped: an exploding agent degrades the mode, it never kills a job or
the class.

### The automatic turn

With `BRIGHT_AGENT=hermes` the runner gains a **decision gate**. After it grades an
interaction it gives the agent one bounded turn to decide what happens next,
instead of following the authored branch blind.

```
student answers
    ↓  ~0.5 ms          grade → reveal frame → immediate feedback   (reflex, NS-2)
    ↓                   ── the agent is not in this path ──
    ↓  ≤ AGENT_TURN_TIMEOUT_S
    │   agent chose a legal action  → apply it, drop the branch
    │   agent chose `say_only`      → speak, DEFER the branch behind a fresh
    │                                 silence window (never cancel it)
    └─  slow / crashed / illegal / stale / busy / mode ≠ FULL
                                    → the authored branch, exactly as before
```

The turn is started *before* the `CORE_REVEAL_HOLD_S` reveal hold, so the model
thinks during a second the class was already spending looking at the answer;
added latency is `max(0, turn − hold)`, not `turn`.

Turns are serialised — one classroom, one teacher. A turn that arrives while
another is in flight is **skipped, not queued**: a queued turn would be
answering a question the class has already moved past.

`silence` and `timeout` go through the same gate. A child who says nothing
needs a different answer from one who answers wrongly. Auto-advance (an
activity with `durationS` and no `expect`) does not — nothing was graded, so
there is no pedagogical decision to make.

With `BRIGHT_AGENT=off`, `runner.decide_next` is `None` and none of the above
code path exists. Not "a hook that returns early" — absent (NS-1).

Counters are in `/dev/state` under `agent`: turns, applied, timeouts, errors,
skippedNotFull, skippedBusy, mean latency.

### Background jobs (docs/archive/phase-1-plan.md §6)

| Job | Trigger |
|---|---|
| `health_probe` | every `CORE_PROBE_INTERVAL_S`, immediately at boot |
| `prepare_next` | cron, `CORE_PREPARE_NEXT_HOUR:00` UTC, or call `jobs.prepare_next()` |
| `summarize_session` | one-shot, `CORE_SUMMARY_DELAY_S` after a session ends |

A session row opens on `/dev/lesson/start` and closes when the runner reaches
the end of the run, which is also what queues `summarize_session`. In OFFLINE
mode core is the only thing that can close it, so this does not wait for an
agent.

`agent_bridge.build_agent_seam()` supplies the real `summarize_session` and
`probe` over whatever agent object was injected. The summariser asks for one
JSON object, repairs a truncated tail (observed live: a valid object minus its
closing brace, `finish_reason: "stop"`), counts skill estimates itself rather
than asking the model for numbers, and falls back to a deterministic note if
the model is unreachable — NS-1 applies to memory too, and next week's greeting
needs *something* to remember.

### The memory loop

```
lesson start (studentId)  →  upsert student, recall into the greeting prompt
graded interaction        →  observations row (runner) + observations row (agent)
lesson ends               →  session closes, summarize_session queued
summarize_session         →  session_summaries row, indexed for FTS recall
next lesson start         →  that summary is the first line of MEMORY
```

`build_turn_context(recall_query=...)` reserves the top slot for a session
summary before filling the rest with observations. bm25 rewards short
documents, so raw `{'optionId': 'six'} -> wrong` rows otherwise crowd out the
paragraph written about them and `summarize_session` becomes a job nobody reads.

### Lesson timing semantics

`PROTOCOL.md` §4 does not say when `timeout` versus `silence` fires. This
service reads it as:

| activity | on timer expiry |
|---|---|
| `durationS`, no `expect` | auto-advance: `always` branch if present, else the next activity |
| `durationS` + `expect` | outcome `timeout` |
| `expect`, no `durationS` | outcome `silence` after `CORE_SILENCE_TIMEOUT_S` |
| neither | waits for a `control.command` |

Every `_enter` bumps a generation token, so an answer that lands just before
its own auto-advance timer can never advance the lesson twice.
