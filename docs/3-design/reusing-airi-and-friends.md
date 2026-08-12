# 04 — REFERENCE REPOS: what to take, what to leave

**Date:** 2026-08-11
**Location:** `references/` — three repos, cloned, audited by reading source.

| Repo | Version | License | Role for us |
|---|---|---|---|
| `hermes-agent` | `0.20.0` (Nous Research) | MIT | **Runtime dependency** — the teacher brain |
| `airi` | `0.11.3` @ `b230e16` (moeru-ai) | MIT | **Vendored source** — renderer + lipsync packages only |
| `openclaw` | `2026.8.1` (OpenClaw Foundation) | MIT | **Read-only reference** — patterns, not code |

All three are MIT, so vendoring and commercial use are fine. Keep the LICENSE files with anything copied.

---

## A. hermes-agent — runtime dependency

### Use as-is

| Capability | Path | Note |
|---|---|---|
| API server | `gateway/platforms/api_server.py` | port 8642; `/v1/responses` is the one we want |
| MCP client | `tools/mcp_tool.py` | our `classroom-mcp` registers via `~/.hermes/config.yaml` → `mcp_servers` |
| Cron | `cron/` (`scheduler.py`, `jobs.py`, `executions.py`, `monitor.py`) | before-class lesson preparation |
| Skills | `skills/`, `optional-skills/` | pedagogy strategies as procedural memory |
| Memory providers | `agent/memory_provider.py` + `plugins/memory/` (8 providers) | pick one, or write ours against the ABC |
| Custom model provider | `plugins/model-providers/custom/` | `provider: custom` + `base_url` → OVMS |
| Subagents | `tools/delegate_tool.py` | optional; e.g. offline post-class analysis |

### Files to read before writing the adapter

```
gateway/platforms/api_server.py                     ← the whole contract
website/docs/user-guide/features/api-server.md      ← the human-readable version
website/docs/guides/use-mcp-with-hermes.md
website/docs/reference/mcp-config-reference.md
website/docs/guides/automate-with-cron.md
website/docs/developer-guide/memory-provider-plugin.md
website/docs/user-guide/configuring-models.md       ← base_url semantics
plugins/model-providers/custom/__init__.py
```

### The exact API surface we depend on

```
POST http://127.0.0.1:8642/v1/responses      (stream=true)
  headers: X-Hermes-Session-Id  (or body: previous_response_id)

SSE out:
  response.created
  response.output_item.added   { item.type: "function_call", name, arguments }
  response.output_text.delta   { delta }
  response.output_item.done    { item.type: "function_call_output", output }
  response.completed | response.failed
  event: hermes.tool.progress  { status: "running", ... }
```

Config knobs that matter:
- `API_SERVER_CORS_ORIGINS` / `cors_origins` — required for the browser Stage to call Hermes directly
- `HERMES_API_TIMEOUT` — must be raised for a slow local model
- `model: { provider: custom, base_url: ..., default: ... }`

### Do NOT use

- Messaging gateways (Telegram/Discord/Slack/…) — a classroom is not a chat channel
- Hermes' own TTS/STT tools (`tools/tts_tool.py`, `tools/voice_mode.py`) — our speech service owns audio; keeping it out of the agent loop is what makes the reflex tier possible
- `hermes claw migrate` — nothing to migrate
- Terminal/exec tools — unless deliberately enabled; the agent has no business running shell in a classroom

### Risks

- `0.20.0`, moving fast. Deps are exact-pinned with `exclude-newer = "14 days"` — pin a specific commit and upgrade deliberately.
- Zero mentions of OpenVINO in the repo → SP-2 must prove the OVMS path.
- The agent loop is chat-shaped, tuned for a personal assistant. Whether its turn overhead is acceptable in a live classroom is SP-4.

---

## B. airi — vendored source

**Everything we want is `private: true`.** Not installable from npm. Use a git submodule under `vendor/airi` and import by path, or copy the packages outright.

### Take these — clean, no `stage-ui` dependency

Verified: none of these import `@proj-airi/stage-ui`.

| Package | What it gives |
|---|---|
| `packages/stage-ui-live2d` | Live2D scene + model components (`pixi-live2d-display`, PIXI v6). Note: needs `patches/pixi-live2d-display.patch` and the `@proj-airi/unplugin-live2d-sdk` Vite plugin |
| `packages/stage-ui-three` | VRM via `three` + `@pixiv/three-vrm`, wrapped in TresJS |
| `packages/model-driver-lipsync` | wLipSync AudioWorklet driver. Vowel/viseme classification (`A E I O U S`), not naive amplitude. Exposes `getVowelWeights()` / `getMouthOpen()` |
| `packages/pipelines-audio` | `createPlaybackManager`, `createSpeechPipeline`, `normalizeActPayload` |
| `packages/stream-kit` | `createQueue` — ordered async queues |
| `packages/stage-shared` | WebGPU detection, misc |
| `packages/ui` | Reka-UI primitives. **This one is publishable** |

Two known leaks to patch when vendoring — both are deep relative imports that cross package boundaries:
- `packages/stage-ui-three/src/composables/vrm/lip-sync.ts:11` → `'../../../../stage-ui/src/stores/audio'`
- `packages/stage-ui-mmd/src/composables/mmd/lip-sync.ts:15` — same, with an acknowledging comment

Fix by injecting an `AudioContext` rather than importing AIRI's store.

### Read but rewrite

`packages/stage-ui/src/components/scenes/Stage.vue` (~900 lines) is where all the coupling lives — its import block pulls in ~13 app-level stores (`useChatStore`, `useSpeechStore`, `useProviderStore`, `useSettings`, `useLlmStreamingControlStore`, …).

Do not vendor it. **Read it, then rewrite the glue** against our own stores. The useful shapes to copy:

```
:217  emotionsQueue          — emotion fan-out per renderer
:271  streamingControl.onSignal({type:'act'|'delay'})  — signal → motion/emotion
:298  playSpecialToken()
:314  playFunction()         — lip-sync node wiring
constants/emotions.ts:1      — happy/sad/angry/think/surprise/awkward/question/curious/neutral
```

**`packages/stage-ui-live2d/src/tools/expression-tools.ts` is dead code with zero importers** — it defines real `@xsai/tool` definitions (`expression_set`, `expression_get`) backed by an expression store. It is a ready-made template for tool → animation binding. Ideal starting point for our AIRI event mapper.

### Take with care

| Thing | Path | Caveat |
|---|---|---|
| openai-compatible provider | `packages/stage-ui/src/libs/providers/providers/openai-compatible/index.ts` | `baseUrl` is a bare string with no host allowlist → can point at `127.0.0.1:8642`. Browser CORS applies (Hermes supports `cors_origins`) |
| REST TTS session | `packages/stage-ui/src/libs/speech/tts-session.ts` | **use `transport: 'rest'`** — client-side segmenter, works against any `/audio/speech` endpoint |
| In-browser VAD | `packages/stage-ui/src/workers/vad/vad.ts` | Silero-style ONNX via transformers.js. Useful reference, but our VAD should live in the Python speech service |
| Whisper in-browser | `packages/stage-ui/src/libs/inference/adapters/whisper.ts` | has a real GPU resource coordinator with WASM fallback — good reading for the 16 GB budget question |

### Do NOT take

- `packages/stage-ui/src/libs/speech/streaming-pipeline.ts` — requires AIRI server-runtime (`/api/v1/audio/speech/ws`, auth token, `STREAMING_TTS_UPSTREAM`). See [fact check](../2-decisions/fact-check-gpt-brief.md) #7
- `packages/core-agent`, `packages/core-character` — Hermes owns cognition
- `apps/stage-tamagotchi` (Electron), `apps/stage-pocket` (Capacitor) — we run Chromium kiosk
- `integrations/*` (discord, telegram, minecraft, vscode) — irrelevant
- `packages/drizzle-duckdb-wasm`, `memory-pgvector` — our data lives in Core, server-side

### Stack compatibility

AIRI: Vue 3.5, pnpm 10.33 catalogs, Vite 8, Turborepo, UnoCSS, Vitest.
`classroom-stage` should match Vue 3.5 + Vite + pnpm to keep vendored packages building. UnoCSS is optional but reduces friction if we copy any components.

---

## C. openclaw — read-only reference

**Nothing gets imported.** Read these files, then close the repo.

| Read | Why |
|---|---|
| `extensions/canvas/src/tool-schema.ts:12-20` | one tool + action enum — a tool-shape decision for `board.*` |
| `extensions/canvas/index.ts:16-25` | node-command layer vs. tool layer separation |
| `docs/gateway/protocol.md:46-49` | req/res/event frames with `seq` + `stateVersion` — copy this for our event bus |
| `docs/gateway/protocol.md:355-367` | operator/node roles + scope model — informs facilitator-console permissions |
| `src/gateway/node-command-policy.ts:101-110` | dangerous-command allowlist. **Mandatory pattern** for a camera pointed at children |
| `extensions/canvas/src/a2ui-jsonl.ts:112-113` | how they version-gate a UI protocol and reject unsupported versions |
| `docs/platforms/linux.md:32-35` | the WebKitGTK microphone caveat — the reason we run Chromium kiosk, not an embedded WebView |
| `docs/nodes/index.md:573-577` | render-only vs. action-dispatch trust boundary for embedded pages |

### Lessons already absorbed into our design

1. **Action-enum tool shape** → resolved in [architecture](architecture.md) §3: we went further than OpenClaw and collapsed to 4 proposal tools over a Core-computed `available_actions[]`. `board.*` never reaches the model at all
2. **`seq` + `stateVersion` on every event** → adopted in [architecture](architecture.md) §4
3. **Deny-by-default for camera/recording** → adopted in [architecture](architecture.md) §5
4. **Version-gate the UI protocol** → our scene DSL should carry a version and reject unknown ones

### Explicitly rejected

Gateway WS as our transport (we have one appliance, not a fleet), A2UI as our board protocol (too generic for classroom activities), and its node/camera layer (a local Python service is faster and simpler).

---

## Summary

```
hermes-agent   →  run it            (pip install, config, don't fork)
airi           →  vendor 6 packages (submodule; rewrite Stage.vue glue)
openclaw       →  read 8 files      (import nothing)
```
