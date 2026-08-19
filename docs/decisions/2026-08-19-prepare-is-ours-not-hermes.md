# PREPARE runs on our own clock, not the harness's

**2026-08-19.** Fills the BEFORE box of NORTH-STAR §2, which had never once run.

## The plan said to use Hermes' `cron` and `delegate_task`. The source says don't.

Both were verified in `references/hermes-agent` rather than assumed, and three
findings killed that route:

**1. `bright_live` is per-process, not per-request.** The profile that pins the
terminal tool and the system prompt is built once at gateway start
(`gateway/platforms/api_server.py:1377`) and applied to every agent that
platform creates (`:2955`). Preparation cannot share the classroom gateway,
because on that gateway every request is forced through the single-terminal-tool
wire policy. It would need a second Hermes process with its own config.

**2. An MCP server is unioned in by default, silently.** In
`_get_platform_tools` (`hermes_cli/tools_config.py:2495-2500`): if a platform's
toolset list names no MCP server, **every globally-enabled MCP server is union'd
in**. So a cron platform configured as `[cronjob, delegation]` — naming no MCP
server, because neither of those *is* one — would be handed `bright-classroom`,
and `say` with it. Nothing upstream blocks an MCP tool by name for a child agent
or a scheduled job; `DELEGATE_BLOCKED_TOOLS` covers Hermes' own tool names only,
and MCP toolsets are explicitly *preserved* for children by default
(`tools/delegate_tool.py:808-816`, `inherit_mcp_toolsets` defaults true).

The guarantee we need — *a preparation agent can never speak* — is therefore not
achievable by configuring Hermes. It is only achievable structurally, by running
preparation somewhere `bright-classroom` does not exist.

**3. We had the precedence backwards.** `agent.disabled_toolsets` is applied
**last** and subtracts (`tools_config.py:2502-2510`, *"This runs last so it
overrides everything above"*). It does not lose to `platform_toolsets`; it wins
over it. What actually keeps the classroom narrow is that `bright-classroom` is
an MCP server name and not a registered builtin toolset key, so zero builtin
tools resolve.

While checking, found that `disabled_toolsets` contained **`delegate`**, which
is not a registered key — the toolset is `delegation`
(`hermes_cli/tools_config.py:116`). An unknown name resolves to nothing and
warns about nothing, so that guard had been doing nothing. Fixed.

## What we did instead

Core already owns a day clock: `scheduler.py`, APScheduler, a nightly
`prepare_next` at 03:00 behind `AgentSeam`. It was a no-op. It is now wired.

`prepare_period(core, unit_id)` runs one turn with the system event
`[prepare]`. The guarantee lives in `teacher_os.execute`, in our code, as a
test:

```python
PREPARE_TOOLS = frozenset({"read_library", "search_library", "read_board", "plan"})
```

Anything else is refused. She cannot speak, cannot put anything on the board,
cannot record evidence about a child who is not in the room. *"The Stage is the
only loudspeaker"* is not a thing to ask an agent nicely for.

A prepare turn succeeds on having written a **plan**, not on having said
something — which is what preparing means. It refuses to run while a class is in
progress: a second teacher thinking out loud during a lesson is the one thing
the turn lock exists to prevent.

The plan is stored under `prepare:<unit>`, and `start_teacher_session` copies it
onto the morning's real session. Copies, not references — revising it tonight
must not rewrite what she actually did this morning.

`POST /teacher/prepare` runs it on demand. A highland classroom loses power;
preparation that can only happen at 03:00 would silently never happen. The
route goes through `BackgroundJobs`, the same path the scheduled trigger takes,
so a hand-run is not testing something the appliance never does.

The outcome — good or bad — lands on `/teacher/status` as `lastPrepare`. A job
that fails at 03:00 and tells nobody is exactly the papered-over failure the
doctrine calls a defect.

## First run, live

```
census  event=prepare  ok=True  tools=7  board_touched=False
        read_library ×5, plan, say        refusals=say:other
```

Five library files, because nobody was waiting — this is the only place an
offline 4B model is allowed to be slow, and therefore the only place it is
allowed to be thorough. She then tried to `say` and **was refused**, which is
the guard firing in production rather than in a test.

The plan she drafted:

> 1. Open & review: greeting + wellbeing (greet-and-name, ask-wellbeing,
>    answer-wellbeing). 2. Introduce take-leave (Goodbye / Bye) with audio/panel
>    model. 3. Choral and pair practice of the full exchange. 4. First-sounds
>    awareness (hear-h-and-b) using track-12 / track-13. 5. Close with chant
>    review and exit check.

A cold room opened the next morning with exactly that plan in hand, and the
cold-room e2e still passed 7/7.

## One scope bug found by running it

The MCP turn registry binds a turn to `(session_id, student_id)` and refuses a
tool whose scope has drifted (`mcp_server.py:135`). Preparation had no
`student_id`, so every `read_library` came back *"turn learner scope is stale"*.
Preparation now **declares** its scope rather than being exempted from the
check — the check should stay strict during a live class, which is what it is
for.
