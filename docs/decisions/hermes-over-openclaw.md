# DECISION: Hermes or OpenClaw?

**Date:** 2026-08-11
**Status:** LOCKED
**Verified versions:** hermes-agent `0.20.0` · openclaw `2026.8.1` · airi `0.11.3` (`b230e16`)

> **Correction, 2026-08-18.** The decision stands unchanged. One detail below is
> stale: §"Patterns worth borrowing" claims we settled on *"4 proposal-style
> tools over a Core-computed `available_actions[]`"*. That was the cassette
> design and it was rejected — see
> [teacher-agent-not-cassette.md](teacher-agent-not-cassette.md). The live
> surface is eight typed tools the agent chooses freely; Core validates and may
> refuse, but never offers a menu.

---

## Decision

> **Choose HERMES. Drop OpenClaw from the runtime.**
> OpenClaw stays in `references/` as a **reference implementation** to learn patterns from — not as a dependency.

---

## Why this is "pick one," not "stack them"

The original proposal (Hermes = "mind", OpenClaw = "nervous system") was **over-engineering**. Evidence from the source itself:

**OpenClaw is a complete agent runtime, not a device/IO layer.** It has its own LLM loop (`src/agents/`, `packages/agent-core`, `packages/llm-core`), MCP in both directions (`src/mcp/`), memory (`src/memory/` + 4 extensions), skills (`src/skills/` + ~30 bundled skills), and **50+ LLM provider plugins**. Its own positioning (`VISION.md:3`): *"OpenClaw is the AI that actually does things."*

**Hermes treats OpenClaw as a predecessor, not a lower layer.** A `hermes claw migrate` command exists (`hermes_cli/claw.py`, docs at `website/docs/guides/migrate-from-openclaw.md`) that migrates persona, memory, skills, model config, MCP servers, TTS, messaging, and approvals. You do not write a migration tool for something you intend to run on top of.

```
        OpenClaw  ←── competing at the same layer ──→  Hermes

NOT:            Hermes
                   ↓
                OpenClaw
```

Stacking two agent runtimes means **double planning**: two LLM loops picking tools, duplicated context, additive latency, conflicting state, and untraceable trajectories.

---

## Four reasons for Hermes

### 1. Python — same process space as the entire ML stack

This is the strongest reason and the easiest to overlook.

Everything the classroom needs is Python: OpenVINO, MediaPipe, pyannote.audio, SpeechBrain, whisper, forced alignment, face embedding.

- **Hermes**: Python 3.11–3.13, installed via `uv` (`pyproject.toml:13`). Perception, speech, and pronunciation services share the language.
- **OpenClaw**: TypeScript/Node ≥22.22.3, pnpm 11.15.1. Every camera/mic signal crosses a Node↔Python bridge — one more serialization layer, one more failure mode, one more latency hop, on *every* frame.

### 2. A verified integration contract that is exactly what AIRI needs

Hermes API Server (`gateway/platforms/api_server.py`) — verified by file:line:

| Thing | Evidence |
|---|---|
| Port `8642` | `api_server.py:151` `DEFAULT_PORT = 8642` |
| `/v1/chat/completions`, `/v1/responses` | `api_server.py:2066-2069` |
| SSE streaming | `api_server.py:4415, 4437, 4513, 4564` |
| Tool progress event | `api_server.py:4434` → `event="hermes.tool.progress"` |
| Server-side tool execution | doc `api-server.md:145` — tool calls are replayed with `status: completed`, **never** handed to the client to execute |
| Session continuity | `X-Hermes-Session-Id` header, or `previous_response_id` |
| CORS for browsers | `api_server.py:985-1016`, config `cors_origins` / env `API_SERVER_CORS_ORIGINS` |

Event types on the stream:

```
response.created
response.output_item.added     ← item type: function_call
response.output_text.delta
response.output_item.done      ← item type: function_call_output
response.completed / response.failed
hermes.tool.progress           ← custom, status: running
```

**This is precisely the signal set needed for embodiment.** Not "avatar reads text" — rather:

```
function_call: board.show_image  →  AIRI turns toward the board
hermes.tool.progress             →  AIRI "thinking" animation
response.output_text.delta       →  TTS starts streaming, mouth moves
function_call_output: correct    →  AIRI celebration animation
response.completed               →  AIRI returns to idle
```

OpenClaw exposes no equivalent event stream in an OpenAI-compatible shape that AIRI already speaks.

### 3. Install weight — the "poor schools" constraint decides here

| | Hermes | OpenClaw |
|---|---|---|
| Runtime | Python 3.11+ | Node ≥22.22.3 / 24.15+ / 25.9+ |
| Install | `uv pip install` / install.sh | pnpm workspace, ~140 extensions |
| Root deps | Python, exact-pinned | 64 runtime + 46 dev + 1 optional |
| Native modules | not required | `@lydell/node-pty`, `sqlite-vec`, `tree-sitter-bash` + `web-tree-sitter`, `playwright-core`, `quickjs-wasi`, `@silvia-odwyer/photon-node` |
| Lockfile | `uv.lock` | `pnpm-lock.yaml` 558 KB |

On a 16 GB box that must simultaneously host Gemma E4B INT4 (~4.5 GB) + STT + TTS + a browser + camera + face models, every hundred MB counts. Playwright and a native PTY serve nothing in a classroom.

### 4. Exactly the capabilities the product needs — each verified

| Product need | Hermes has it? | Evidence |
|---|---|---|
| MCP client with tool auto-discovery | ✅ | `tools/mcp_tool.py` — stdio/HTTP/SSE, registers into the tool registry |
| Structured long-term memory | ✅ | `MEMORY.md`/`USER.md` **+ 8 external providers** (`plugins/memory/`: mem0, honcho, supermemory, byterover, hindsight, holographic, openviking, retaindb) |
| Proactive lesson preparation | ✅ | `cron/` — scheduler, jobs, executions, monitor |
| Skills (procedural memory) | ✅ | `skills/` across 14 categories + `optional-skills/` |
| Subagents / delegation | ✅ | `tools/delegate_tool.py` — single + batch parallel |
| Point at any local model | ✅ | `provider: custom` + `base_url` (`plugins/model-providers/custom/`) — documented for Ollama, llama.cpp, vLLM |
| Built-in TTS / STT | ✅ | `tools/tts_tool.py`, `tools/transcription_tools.py`, `tools/voice_mode.py` |
| Commercially usable license | ✅ | MIT (Nous Research, 2025) |

---

## What dropping OpenClaw costs us

Being honest about the losses:

| Lost | Replaced by |
|---|---|
| Canvas — agent-controlled HTML/CSS/JS workspace | our own `classroom-mcp` + `Learning Stage`. We need something *more specialized* than a generic canvas, so this is arguably a gain |
| A2UI v0.8 — agent-generated dynamic UI | our semantic scene DSL. See NS-3 |
| Gateway WS — multi-device control plane | we have **one** appliance, not a fleet. An internal event bus suffices |
| `camera.*` / `device.*` nodes | a local Python `perception-service` — faster, no WS hop |
| ~50 provider plugins | not needed. We run exactly one local model |

**One more point — stated carefully.** The OpenClaw Linux companion carries this caveat, `docs/platforms/linux.md:32-35`:

> *"the shell does not grant microphone capture to the WebKitGTK WebView, so `getUserMedia` is expected to fail there. Until that lands, open the Gateway's Control UI in a regular browser"*

**This is a WebView limitation, not an OpenClaw-wide one** — the documented workaround is to use a regular browser, which is exactly what our architecture does anyway (Chromium kiosk). So this is *not* a disqualifier on its own; treat it as a data point about maturity on Linux, not as the deciding argument. The decision rests on reasons 1–3 above.

---

## Patterns worth BORROWING from OpenClaw (not the runtime)

Three design ideas worth copying:

**1. One tool with an action enum — instead of N flat tools.**
`extensions/canvas/src/tool-schema.ts:12-20`:
```ts
const CANVAS_ACTIONS = ["present","hide","navigate","eval","snapshot","a2ui_push","a2ui_reset"] as const;
```
It registers as **one** tool named `canvas` with an `action` enum. For a small model like E4B, fewer tools with a clear enum beat many flat tools. **Resolved in [architecture](../design/architecture.md) §3** — we went further: 4 proposal-style tools over a Core-computed `available_actions[]`, so `board.*` never reaches the model at all.

**2. The Gateway req/res/event frame shape.** `docs/gateway/protocol.md:46-49`:
```
{type:"req",   id, method, params}
{type:"res",   id, ok, payload|error}
{type:"event", event, payload, seq?, stateVersion?}
```
`seq` + `stateVersion` are the important details — Learning Stage needs exactly this to avoid state drift on reconnect.

**3. Dangerous commands require an explicit allowlist.** `src/gateway/node-command-policy.ts:101-110` — `camera.snap`, `screen.record`, etc. are blocked by default. For a system with a camera pointed at children, this pattern is **mandatory** to copy.

**4. Heartbeat is a periodic main-session agent turn, not a socket ping.**
OpenClaw (`docs/gateway/heartbeat.md`) wakes the same agent, skips if busy,
and replies `HEARTBEAT_OK` when nothing needs attention. Bright copies that
shape onto the live class: Core `pulse_teacher` checks Hermes/speech/silence,
wakes on Start (`[sat_down]`), and only calls Hermes when the room has been
quiet too long. See [2026-08-18-room-runs-itself.md](2026-08-18-room-runs-itself.md).
The 5 s PROTOCOL `heartbeat` frame stays a socket liveness ping.

---

## Conditions that would reverse this decision

Revisit if:

- The Hermes API server proves unstable across `0.2x` releases (measured by our own evals — see [open questions](../archive/open-questions.md))
- Hermes agent-loop overhead pushes p95 latency past the usable threshold on the target box
- `provider: custom` + `base_url` cannot talk to OpenVINO Model Server (spike SP-2)

Because of NS-4, reversal means rewriting an adapter, **not** rewriting the product. `classroom-mcp` and `classroom-core` do not change.
