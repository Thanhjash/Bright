# Flat tools, and the round-trip we were actually paying for

**2026-08-19.** Superseded a merge attempt made the same day. Reverted in
`e080f93`; the surface hygiene and telemetry below landed after it.

## What happened

Turns cost 2–4 model round-trips at ~6–9 s each, and the board did not always
change at the moment she spoke. I diagnosed this as a **tool-boundary** problem
and merged five tools — `write_board`, `show_image`, `show_exercise`,
`play_clip`, `say` — into one `teach` with a nested `board` union.

It failed three ways:

1. `board: {}` was refused, the model repeated the identical call three times,
   and the Hermes circuit breaker took the whole MCP server out of the turn.
2. The terminal exit condition still named `say`, so every turn burned
   `api_calls=8/8`.
3. With both fixed, **the board stayed empty on all three test turns.** No
   error. The model simply avoided the nested union.

(1) and (2) were my bugs. (3) is not fixable — it is the model's capability
speaking, and the deployment target is a *smaller* model.

## What was actually wrong

Merging tools reduces **tool count**. Latency is **round-trips**. Those are
different axes, and she still needs a separate call to read the library either
way. What reduces round-trips is bundling several tool calls into one message —
which the `0002-teacher-multi-tool` patch already enabled.

Measured after the revert, with flat tools:

```
api_calls=  4/8   3/8   1/8   2/8   2/8   2/8   3/8
```

The `1/8` turn executed board + image + speech in a single round-trip. **The
merge was never needed for synchronisation.**

The model bake-off inverted the fear that drove the merge:

```
model                              p50     tools/msg   turn_id ok
google/gemma-4-26b-a4b-it         9.06s       3.0         5/5
google/gemini-3.7-flash           6.02s       1.4         3/5
```

The Gemma family — the one that ships to the miniPC — bundles *better* than the
development model. Flat + bundling is the safer bet on E4B, not the riskier one.

`docs/design/tool-surface.md` §5 had already argued this, under "Why flat, and
not one `board(action=…)` tool". The answer was written down and I overrode it.

## The principle

> **A tool is one independently-refusable intent.** Anything Core can refuse —
> a missing asset, a malformed exercise, a script the classroom does not read —
> gets its own tool, so a refusal costs one move and never the turn.
> **`say` is the tool that must never fail**, so anything riding on `say` must
> degrade on invalid input rather than hard-fail.

This is why a merged tool loses on the axis that matters here: with flat tools a
malformed `show_image` still lets her speak and the lesson limps forward; with
one merged tool a single bad sub-field kills the speech too. In a classroom with
no adult in the loop, that is a teacher standing silent in front of children.

It also explains the one thing kept from the merge: `say` carries an optional
`board_text`, because an invalid one is skipped and the class still hears her.
An image never could be — a missing asset is a hard refusal.

Earlier this was phrased as *"a tool is one physical act of the teacher"*. That
was post-hoc: it only classifies speak-while-chalking as one act because the
definition was chosen to. Independent refusability is mechanical and testable.

## The tripwire

The first draft — *"the day `say` grows a third optional field, `teach` is being
rebuilt"* — was already tripped: `say` has `board_text`, `closing`,
`awaiting_answer`. Field count is not the invariant, because `closing` and
`awaiting_answer` are booleans **about the utterance**, unable to fail.

> `say` may carry (a) the line, (b) booleans about the line, and (c) at most one
> degrade-on-invalid content field — the chalk. **The day a field on `say` can
> cause `ok: false` for any reason other than `teacher_line`, or gains type
> object/array, or names an `asset://`, `teach` is being rebuilt.**

Those are exactly the three signatures the merge died of: hard-failing
sub-fields, nested structure, asset references.

And a behavioural tripwire, because a schema can stay clean while usage
degenerates: **if `board_touched` falls while say-only turns rise, the surface
has merged in practice whatever the schema says.**

## What `write_board` is for, now that `say(board_text)` exists

Both are capped at 400 characters and 8 lines and both run
`_clean_board_markdown` → `_push_stage`. Neither writes more than the other.
They are kept apart for two reasons, and the descriptions now say so, because
two tools that look interchangeable are a coin flip a 4B model pays for every
turn:

- **`write_board` puts writing up first, then she talks about it.**
  **`say(board_text)` chalks in the same breath.** Different moments.
- **`write_board` is the loud path** — it refuses with a reason she can act on
  inside the turn. **`board_text` is the quiet path** — it degrades. Deleting
  `write_board` would leave no loud path for board content at all.

A `board_text` that is dropped now reports `board: "skipped: <reason>"` beside
`ok: true`. Skipping silently was its own bug: she believed she had written, and
the next turn's `WRITING=` disagreed with her. **Degrade loudly, fail never.**

## Landmines removed the same day

- **`show_image` had `required: []`.** `show_image({turn_id})` passed schema
  validation and failed only at execute — a wasted round-trip a child sits
  through, handed free to any model that guesses. `asset` is now required and
  the pair case is one optional `second`, replacing the invisible `left`/`right`
  convention. This was the same all-optional trap that killed `teach`'s
  `board: {}`, alive in miniature.
- **`record_evidence` offered `off-topic` in its enum and refused it
  unconditionally in execute.** A schema-legal value that always fails is a
  landmine for a small model, which trusts an enum over the prose beside it.
- **`present` and `open_response`** were reachable in `execute` and in no tool
  list. Deleted, with the now-dead `LAYOUTS` and `response_open`.

## Bundling, which is now the whole optimization

A model splits messages when it believes it must see a result before deciding
the next call. So:

- **A worked example beats a rule.** Small models imitate more reliably than
  they deduce. The turn prompt now shows the shape —
  `show_image + record_evidence + say` in one message — instead of only stating
  the rule.
- **The tool list reads as a narrative**: look things up, change the room, `say`
  last because it ends the turn. `record_evidence` used to sit *after* the
  terminal tool. Order is the same in `mcp_server.TOOLS`,
  `hermes.TEACHER_TOOLS` and the config include list.
- **Batching hints live in the tool descriptions**, not only the prompt, so they
  travel with the schema and survive a prompt rewrite.
- **Prompt step 7 was cut.** *"Before EXIT, read_board so picture, writing and
  exercise match"* mandated a round-trip on every closing turn to fetch state
  the turn input already carries as `WRITING` / `IMAGES` / `CLIP` / `EXERCISE`.
  `read_board` survives as a tool; if a week of census lines shows it is never
  called, it goes too.

`supports_parallel_tool_calls: false` was checked and left alone: upstream it
gates concurrent *execution* of MCP calls, not what the model may emit. We want
it false — the board must land before the voice.

## The census

One log line per turn, names and counts only — never a teacher line, never a
child's words, never a learner id:

```
teacher turn census event=student ok=True tools=3 board_touched=True
  tool_names=read_library,record_evidence,say refusals=- board_skips=-
```

Joined with `api_calls=N/8` from the harness log, `tools` gives the bundling
ratio. A quietly-degraded E4B reads as `api_calls` p50 drifting 2 → 4+, tools
per turn falling toward 1, and `board_touched` collapsing: an all-talk teacher
who looks fine in any single transcript.

The baseline has to be recorded **before** the E4B migration, or there is
nothing to compare against.

`board_touched` counts only what *this* turn put up. `last_writing` persists
across turns, and treating it as proof would hide the exact failure the counter
exists to catch.

## The gate that would have saved the day

**If the strong development model stumbles on a schema, it does not ship to the
4B.** Gemini avoiding the nested union was the cheapest possible warning about
how E4B would fail on the edge device, and I read it as a bug to fix rather than
a verdict.

## Found while instrumenting

The turn census printed a stream frame where the event name belonged. The SSE
loop in `_handle_teacher_turn` bound its frames to `event`, which above it is
the *system* event (`heartbeat` / `class_start` / `None`). After the stream
finished, `event is None` and `event == "heartbeat"` were both false whatever
the turn actually was — so a heartbeat she correctly answered with silence was
filed as `last_teacher_fault`, and `S:talk` never once reached `BEATS`. An adult
watching `/teacher/status` would have learned to ignore the fault line.

The regression test has to emit at least one frame: a fake stream that yields
nothing never rebinds the loop variable, and the first version of the test
passed against the broken code.
