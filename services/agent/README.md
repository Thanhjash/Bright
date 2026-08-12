# services/agent — the TeacherAgent

Decides **what to teach next**. It is the only component in Bright that talks to a
model, and the only outbound network call in the system.

It does not hold state, render anything, or touch the DOM. It proposes; `classroom-core`
disposes. See [docs/4-build/phase-1-plan.md §3–§4](../../docs/4-build/phase-1-plan.md),
[docs/3-design/architecture.md-architecture.md §3](../../docs/3-design/architecture.md-architecture.md), NS-2/NS-3.

```
classroom-core ──TurnContext──►  TeacherAgent.turn()  ──AgentEvent stream──► classroom-core
                                        │                                        │
                                        └── ToolExecutor (injected by core) ◄─────┘
                                        │
                                        └── HTTPS ► mimo-v2.5-pro
```

---

## The contract

```python
class TeacherAgent(Protocol):
    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]: ...
```

`TurnContext` comes from `bright_contracts` — this service never redefines a wire model.

`AgentEvent` is a five-member discriminated union (`bright_agent/base.py`):

| Event | Meaning |
|---|---|
| `TextDelta(text)` | a chunk of teacher speech, in order. May carry inline `<\|ACT\|>` tokens |
| `Act(act, inline)` | an emotion/motion cue; `inline` is the exact `<\|ACT {...}\|>` token |
| `ToolCall(call_id, name, arguments)` | the model proposed something — already parsed, not yet validated |
| `ToolResult(call_id, name, ok, result, error)` | outcome of the single attempt |
| `Done(reason, detail, usage)` | terminal, exactly one per turn |

Three invariants a caller may rely on:

1. **Exactly one `Done` ends every turn.** `turn()` never raises for an operational
   failure — a dead endpoint, a malformed tool call and an illegal `action_id` all
   arrive as `Done(reason="error")`.
2. **Single attempt, always.** No retry, no tool-repair loop, no reprompt.
   `Done(reason="error")` means *fall back to the `lesson_run` default now* — thirty
   children are waiting (docs/3-design/architecture.md §3).
3. **`Done(reason="no_action")`** means the model produced nothing actionable. Core
   continues as if the agent were absent.

---

## Quick start

```bash
cd services/agent
uv venv .venv && uv pip install --python .venv/bin/python httpx pydantic pytest pytest-asyncio
# packages/contracts/python is not a distribution yet — put it on the path:
echo "$PWD/../../packages/contracts/python" > .venv/lib/python3.13/site-packages/bright_contracts.pth

.venv/bin/python -m pytest -m "not live"     # 37 offline tests, no network
.venv/bin/python -m pytest -m live -s        # hits the real endpoint, prints tokens
```

`conftest.py` also puts the contracts package on `sys.path` and loads the repo `.env`,
so tests work without the `.pth` trick.

### Configuration — environment only, never hardcoded

| Var | Default | Notes |
|---|---|---|
| `LLM_BASE_URL` | `https://token-plan-sgp.xiaomimimo.com/v1` | Phase 3: point at OVMS / llama.cpp |
| `LLM_API_KEY` | — | sent as **both** `api-key:` and `Authorization: Bearer`; the provider accepts either |
| `LLM_MODEL` | `mimo-v2.5-pro` | |
| `LLM_DISABLE_THINKING` | `true` | see the trap below |
| `LLM_MAX_TOKENS` | `400` | |
| `LLM_MAX_ROUNDS` | `3` | hard ceiling on tool-loop rounds |
| `LLM_TIMEOUT_S` | `20` | core's health probe decides FULL/DEGRADED from measured latency |

### The `thinking` trap

```python
body["thinking"] = {"type": "disabled"}     # TOP-LEVEL. correct.
body["extra_body"] = {"thinking": ...}      # SDK sugar. over raw HTTP this does nothing.
```

`extra_body` is Python-SDK syntax that the SDK flattens into the body. Sent literally,
reasoning stays on and the completion budget is burned returning empty content.
Both branches are covered by live tests (`tests/test_live.py`); the wrong shape was
re-confirmed live on 2026-08-11: `content: ''`, `reasoning_content:` a paragraph.

---

## Wiring it into classroom-core

```python
from bright_agent import DirectAgent, LLMConfig, Done, TextDelta, ToolCall

async def execute(name: str, arguments: dict):        # THE seam
    ...                                               # core's own code; may raise

agent = DirectAgent(execute, LLMConfig.from_env())

async for ev in agent.turn(ctx):
    match ev:
        case TextDelta(): ...      # → speech.say
        case Done(reason="error"): fall_back_to_lesson_run()
```

`ToolExecutor` is a `Protocol`: `async def __call__(self, name, arguments) -> Any`.
It **raises** on failure; the agent converts that into one `ToolResult(ok=False)` and
one `Done(reason="error")`. This service does not import `classroom-core`, ever.

`bright_agent.act.to_text_stream(events)` flattens the event stream into the single
annotated text stream the avatar/TTS pipeline wants (`PROTOCOL.md` §5) — spoken text
with `<|ACT|>` tokens interleaved in order. Parsing them (the 5-char tail rule,
back-pressure) is `packages/airi-bridge`'s job, not ours.

---

## The five tools

`bright_agent/tools.py`, exactly the surface in docs/4-build/phase-1-plan.md §4 — sized for a 4.5B model,
not for MiMo.

```
classroom_get_state()
classroom_choose_next(state_version, action_id, params?)   ← action_id is a per-turn enum
classroom_say(text, style?)
classroom_record_observation(student_id, skill, result, evidence)
classroom_recall(query, k?)
```

`build_tools(ctx)` regenerates `classroom_choose_next`'s `action_id` enum from
`ctx.available_actions` on every turn. **This is the whole design**: an open-ended
tool-routing problem becomes a constrained multiple choice, which is where a small
model is strong. Do not "improve" it into free-form tool composition. If
`available_actions` is empty the tool is omitted rather than offered with an empty enum.

`classroom_choose_next` is terminal: the model picks ONE action and the turn ends.

### Validation — `bright_agent/validation.py`

Runs **inside the agent, before the executor is called**. An illegal proposal never
reaches core.

| Code | Trigger |
|---|---|
| `unknown_action_id` | `action_id ∉ ctx.available_actions` |
| `stale_state_version` | `state_version != ctx.state_version` (future values are stale too) |
| `bad_arguments` | unparseable JSON args, wrong types, illegal `result` |
| `missing_field` | required field, or a param an action declares |
| `empty_text` | `classroom_say` with nothing to say |
| `unknown_tool` | the model invented a tool name |
| `no_available_actions` | it chose when core offered nothing |

Every rejection is logged (`logging`) **and** appended to `validation.REJECTION_LOG`
as a `Rejection` carrying the arguments, the legal ids, both state versions, lesson id,
activity index and student id — enough to replay the decision in an eval later.

Any rejection ends the turn with `Done(reason="error")`. It does not skip the call and
carry on: a wrong proposal means the model has misread the situation, and repairing it
mid-class is the thing we are explicitly not doing.

---

## Prompt

`bright_agent/prompt.py`. Two parts, deliberately split for the prefix cache:

* `SYSTEM_PROMPT` — a module constant, byte-identical on every turn: persona, the
  scaffolding ladder (English → simpler English → image/gesture → example → Vietnamese
  hint → Vietnamese explanation, one step at a time, never jump to Vietnamese), and the
  ACT syntax with the exact 9 emotion names. ~350 tokens. **Do not grow it.**
* `render_turn(ctx)` — everything volatile, in the final user message:

```
LESSON en-a1-market-01 · class 7A · stage PRACTICE · activity 3/9
BOARD choice: "Which one is the apple?" [o1=apple, o2=banana]
STUDENT Minh (s17) — food_vocab 0.82
JUST DID choice: picked banana → wrong
MEMORY
- 2026-08-04: confused apple and banana
ACTIONS (state_version 88) — choose exactly one id:
1. next_activity — advance to sentence_builder
...
Say one short line, then call classroom_choose_next. Now.
```

Measured on 2026-08-11 (mimo-v2.5-pro, the context above):

| Segment | tokens |
|---|---|
| hidden provider preamble | ~250 |
| `SYSTEM_PROMPT` | ~350 |
| tool JSON schemas | ~650 |
| rendered turn context | ~140 |
| **prompt total** | **~1 480** |
| completion | 150–190 |
| latency | 2.7–5.8 s, 1 round |

`cached_tokens` is reported and quantised to 512-token blocks: an identical repeat turn
cached ~1 472/1 476, a turn whose `available_actions` changed cached 512–1 024. The
volatile enum lives inside the tool block, which sits in the cacheable prefix — so a
change to the action set partly busts the cache. That is a knowingly accepted cost;
see *Known weaknesses*.

---

## ACT tokens — `bright_agent/act.py`

Emission only. `format_act` / `format_delay` render `PROTOCOL.md` §5 grammar;
`ActEmitter` implements the adapter table:

| Trigger | Emitted |
|---|---|
| first tool call of the turn | `<\|ACT {"emotion":"think"}\|>` (deduped, once per turn) |
| `record_observation` → `correct` | `happy` |
| → `wrong` / `near` | `curious` |
| → `silence` | `question` |
| turn completes | `<\|ACT {"emotion":"neutral"}\|>` |

Only the nine emotions exist; `make_act` raises on anything else. `neutral` maps to the
Live2D motion group `Idle`, not `Neutral`.

---

## How a `HermesAgent` slots in later

Everything downstream is written against `TeacherAgent` and `AgentEvent`, so a second
implementation is a new file plus a config switch — no refactor:

```python
class HermesAgent:                                    # services/agent/hermes.py
    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        async for sse in hermes_stream(render_turn(ctx)):   # reuse prompt.py verbatim
            ...  # response.output_text.delta  -> TextDelta
                 # function_call              -> validate_call(...) then ToolCall
                 # hermes.tool.progress       -> ActEmitter.on_tool_call(...)
                 # response.completed         -> Act(neutral) + Done
```

Reusable as-is: `prompt.py` (the prompt is the pedagogy, not the transport),
`tools.py` (Hermes gets the same five tool schemas over MCP), `validation.py`
(guards belong on our side of the boundary regardless of runtime), `act.py`.

Two things to check when that day comes, both already flagged in the docs:
**disable Hermes' multi-attempt tool-repair loop** (docs/3-design/architecture.md §3 — it is a 3× latency
spike in front of a class), and verify it passes MiMo's non-standard `thinking` field
through untouched.

`LocalAgent` (Phase 3) is cheaper still: `DirectAgent` with `LLM_BASE_URL` pointed at
OVMS or llama.cpp. When that serving layer exposes grammar-constrained decoding, add
the GBNF/JSON-schema grammar built from the same `available_actions` ids that
`build_tools` already produces — docs/3-design/architecture.md §3 requires an invalid id to be
*impossible to emit*, and today's `enum` is only a strong hint plus a hard reject.

---

## Known weaknesses (read before Phase 2)

1. **Tool schemas are 44 % of the prompt** (~650 of ~1 480 tokens) and the volatile
   `action_id` enum lives inside them, so changing the action set costs cache. Fixing
   it means moving the choice out of the tool schema entirely (docs/3-design/architecture.md §3 "Tier C" —
   constrained JSON in one completion). Worth measuring against the small model before
   Phase 3, not now.
2. **`enum` is not constrained decoding.** Rejection is our only real guarantee today.
   The hard requirement in docs/3-design/architecture.md §3 is unmet until the serving layer supports it.
3. **The model usually speaks via `classroom_say`, so the `TextDelta` stream is often
   empty.** Inline ACT tokens the model writes end up inside the `say` argument, and
   core — not this service — hands that text to the speech pipeline. Both paths reach
   the same parser, but it means "the text stream" has two sources. Watch it when B4
   lands.
4. **A rejection kills the whole turn**, including any good calls made earlier in the
   same round. That is the safe direction, but it means one bad `record_observation`
   can lose a valid action choice. Revisit only with eval data.
5. Observed live: MiMo happily emits three tool calls in one round despite
   `parallel_tool_calls: false`. The loop handles them in order and stops at
   `choose_next`; a weaker model will not batch like this, which is the case that
   `max_rounds` exists for.
