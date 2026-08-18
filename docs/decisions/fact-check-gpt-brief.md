# FACT CHECK of the GPT "MASTER CONTEXT" brief

**Checked:** 2026-08-11
**Method:** read the source directly in `references/` (hermes-agent `0.20.0`, airi `0.11.3` @ `b230e16`, openclaw `2026.8.1`) + Google's official model card + OpenVINO release notes.

**Short verdict:** GPT's **facts** are surprisingly accurate — nearly every number and filename checks out. The failures are **architectural** (proposing two stacked agent runtimes, which it retracted in its own follow-up) and a few places where it **overstates how plug-and-play AIRI is**.

---

## Summary table

| # | Claim | Verdict |
|---|---|---|
| 1 | Hermes has an OpenAI-compatible API server, `/v1/chat/completions` + `/v1/responses`, port 8642 | ✅ TRUE |
| 2 | Stream events: `function_call`, `function_call_output`, `response.output_text.delta`, `response.completed` | ✅ TRUE (full set + `hermes.tool.progress`) |
| 3 | Hermes memory "is no longer just MEMORY.md", has external providers | ✅ TRUE (8 providers) |
| 4 | Hermes has MCP, cron, skills, subagents | ✅ TRUE, all four |
| 5 | `hermes claw migrate` exists, and has a "no direct equivalent" list | ✅ TRUE |
| 6 | AIRI has an openai-compatible provider with configurable `baseUrl` + `apiKey` | ✅ TRUE |
| 7 | AIRI has a streaming TTS pipeline taking `appendText`, decoding AudioBuffer, emitting per sentence | ⚠️ TRUE BUT INCOMPLETE — **not drop-in** |
| 8 | `stage-web`, `stage-ui`, `stage-pages` are reusable packages | ⚠️ PARTIAL — `stage-web` is an **app**, and all are `private: true` |
| 9 | Gemma 4 E4B: 4.5B effective, 8B with embeddings, 128K context, text/image/audio, native function calling, 35+ languages | ✅ TRUE, all of it |
| 10 | Gemma audio input capped at 30 seconds, output is still text | ✅ TRUE |
| 11 | Tau2: E2B 24.5 / E4B 42.2 / 12B 69.0 | ✅ TRUE (also: 26B-A4B 68.2, 31B 76.9) |
| 12 | RAM: BF16 17.9 / SFP8 8.9 / Q4_0 4.5 / Mobile 2.5 GB | ✅ TRUE |
| 13 | OpenVINO 2026.2 officially supports Gemma 4 E2B/E4B | ✅ TRUE — but see the warning below |
| 14 | OVMS has an example for `OpenVINO/gemma-4-E4B-it-int4-ov` | ✅ TRUE (the HF repo exists) |
| 15 | Hermes can point at OVMS | ⚠️ UNVERIFIED — **0 hits** for "openvino" anywhere in the Hermes repo |
| 16 | OpenClaw Canvas exposes 7 tools: present/hide/navigate/eval/snapshot/a2ui_push/a2ui_reset | ⚠️ NEARLY — it is **1 tool** `canvas` with a 7-value `action` enum |
| 17 | OpenClaw Canvas supports A2UI v0.8 | ✅ TRUE (v0.9 is explicitly **rejected**) |
| 18 | OpenClaw has a Gateway WS protocol + a client package for external apps | ✅ TRUE (caveat: npm may `E404` during rollout) |
| 19 | OpenClaw nodes expose `canvas.* camera.* device.* system.* notifications.*` | ⚠️ PARTIAL — all five exist, but there are **24 namespaces** total |
| 20 | OpenClaw Linux: mic in the WebView unvalidated, `getUserMedia` may fail | ✅ TRUE (quotable verbatim) |
| 21 | OpenClaw Linux companion uses **Tauri** | ⚠️ It has a dedicated Linux app using WebKitGTK; see #22 for the AIRI confusion |
| 22 | (implied) AIRI desktop uses Tauri | ❌ FALSE — AIRI desktop is **Electron**; Tauri is legacy and removed |
| 23 | SpeechOcean762: ~5000 utterances, 250 non-native speakers, **half are children**, 3-level annotation | ✅ TRUE (arXiv 2104.01378) |
| 24 | pyannote.audio does not support streaming diarization, suggests `diart` | ✅ TRUE (upstream FAQ) |
| 25 | Proposed architecture `Hermes → OpenClaw → AIRI` | ❌ DESIGN ERROR — GPT retracted it itself. See [Hermes decision](hermes-over-openclaw.md) |

---

## The items that need care

### ⚠️ #7 — AIRI streaming TTS is NOT drop-in

This is the most expensive misunderstanding if caught late.

`packages/stage-ui/src/libs/speech/streaming-pipeline.ts` does have exactly the API GPT described (`appendText` / `finish` / `cancel`, `AudioBuffer` decode, per-sentence emission, and even an explicit race guard via a serialized promise chain at `:157, :215-226`).

**But it does not talk to a TTS provider directly.** It connects to **AIRI's own server**:

```
:124  toWebSocketUrl(options.serverUrl ?? SERVER_URL, '/api/v1/audio/speech/ws', token, …)
:114-122  getAuthToken()  ← hard-fails without one
:107  requires server-side STREAMING_TTS_UPSTREAM config
```

Using this path means also running **AIRI server-runtime** — another service on the 16 GB box.

**Alternative:** `packages/stage-ui/src/libs/speech/tts-session.ts` defines `SpeechTransport = 'rest' | 'bidirectional-ws'` (`:228`). The `rest` mode uses a **client-side segmenter**: it chunks text and calls `generateSpeech` over REST. Same outward interface (`appendText` / `finishInput` / `end`).

→ **Architecture decision in [architecture](../design/architecture.md): use the REST + segmenter path with our own TTS service. Do not pull in AIRI server-runtime.**

### ⚠️ #8 — All AIRI stage packages are `private: true`

Not installable from npm. Must be **vendored / git submoduled**.

- `apps/stage-web` is an **app**, not a package (`packages/stage-web` does not exist)
- `private: true`: `stage-ui`, `stage-pages`, `stage-layouts`, `stage-shared`, `stage-ui-live2d`, `stage-ui-three`, `model-driver-lipsync`, `pipelines-audio`, `core-agent`, `core-character`
- Publishable: only `packages/ui`, `server-sdk`, `server-shared`, `server-runtime`, `plugin-protocol`, `cap-vite`, `unocss-preset-fonts`, `font-*`

What to actually take: [reusing AIRI](../design/reusing-airi-and-friends.md).

### ⚠️ #13 + #15 — Gemma 4 audio on OpenVINO may NOT work

Google's model card says E4B accepts **text/image/audio**. OpenVINO's release notes say their implementation supports **text and image**; video is unsupported. **Audio is unconfirmed.**

Direct consequence: GPT's section 43 proposal ("use Gemma audio to verify ambiguous utterances") **may be dead on the Intel box**. Do not design anything that depends on it. → Spike SP-1 in [open questions](../archive/open-questions.md).

Also: grepping `"openvino"` across the entire hermes-agent repo returns **0 hits**. In theory `provider: custom` + `base_url` will work (OVMS exposes an OpenAI-compatible API), but **nobody has tried it**. → Spike SP-2.

### ⚠️ #16 — Canvas tool shape

GPT listed 7 tools. In reality `extensions/canvas/src/tool-schema.ts:12-20` defines **one** tool `canvas` with an `action` enum.

This is not nitpicking — it is a **design lesson**. For a 4.5B model, collapsing into fewer tools with enums may beat 15 flat tools. Measure it with evals; do not guess.

### ❌ #22 — AIRI is Electron, not Tauri

AIRI's `AGENTS.md:18`: *"Legacy: `crates/` (old Tauri desktop; current desktop is Electron)"* — and that directory is already gone from the checkout.

Impact: if we ever package Learning Stage as a desktop app, the Tauri assumption does not carry. With the locked architecture we run **Chromium kiosk**, so this only affects reference reading.

---

## Where GPT was RIGHT and deserves credit

For fairness — these are easy things to hallucinate, and GPT got them right:

- The entire Gemma 4 quantization RAM table (17.9 / 8.9 / 4.5 / 2.5 GB) — exact match to the model card
- The entire Tau2 series (24.5 / 42.2 / 69.0) — exact match
- Hermes port `8642` — matches `DEFAULT_PORT`
- The filename `gateway/platforms/api_server.py` — correct
- The full set of Responses API SSE event names — correct
- The verbatim OpenClaw Linux microphone caveat — matches the docs

**GPT's real error was architectural** (stacking Hermes on OpenClaw) in its first pass, which it corrected itself. The remaining defects are of the "right at the description level, wrong at the implementation level" kind — items #7 and #8 are the two that could burn days if trusted at face value.

---

## Sources

- [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4) · [Gemma 4 overview](https://ai.google.dev/gemma/docs/core)
- [OpenVINO 2026.2 release](https://medium.com/openvino-toolkit/openvino-2026-2-more-models-gpu-optimizations-and-enhanced-agentic-support-b962b0c8e898) · [OpenVINO/gemma-4-E4B-it-int4-ov](https://huggingface.co/OpenVINO/gemma-4-E4B-it-int4-ov)
- [SpeechOcean762 (arXiv 2104.01378)](https://arxiv.org/abs/2104.01378)
- Source read directly: `references/hermes-agent`, `references/airi`, `references/openclaw`
