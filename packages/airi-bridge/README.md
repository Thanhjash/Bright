# `@bright/airi-bridge`

A talking Live2D avatar for Bright: a framework-agnostic core plus a thin React layer, ported from [Project AIRI](https://github.com/moeru-ai/airi) (MIT, v0.11.3 @ `b230e16`), which is Vue.

Everything below `src/react/` runs without React. `src/react/` is ~400 lines of glue.

```
src/vendor/   AIRI code, copied. Framework-free. Read-only.
src/act/      <|ACT|> / <|DELAY|> parsing. The correctness-critical part.
src/live2d/   Live2D runtime: motion manager, emotion channel, stage. No React.
src/speech/   text deltas → TTS → ordered playback → lip-sync. No React.
src/react/    <Live2DAvatar>, useSpeechPlayer.
```

`packages/contracts/PROTOCOL.md` is authoritative. Nothing here redefines `Emotion`, `ActPayload`, `EMOTION_MOTION_GROUP` or the `TAG_*` constants — they are imported through `src/contracts.ts`, the single file that knows where the contracts package lives.

---

## Quick start

```tsx
import { Live2DAvatar, useSpeechPlayer } from '@bright/airi-bridge/react'
import lipSyncProfile from '@bright/airi-bridge/wlipsync-profile.json'

function Stage() {
  const player = useSpeechPlayer({
    // You choose the provider. The bridge never knows about it.
    tts: async text => (await fetch('/api/tts', { method: 'POST', body: text })).arrayBuffer(),
    lipSyncProfile,
  })

  // Feed SSE deltas straight in. Always await push().
  async function onTurn(stream: AsyncIterable<string>) {
    const turn = player.speak({ turnId: 't-1' })
    for await (const delta of stream) await turn.push(delta)
    await turn.end()
  }

  return (
    <Live2DAvatar
      model="/models/live2d/haru_greeter_t03.model3.json"
      binding="/models/live2d/bright-model.json"
      cubismCore="/models/live2d/live2dcubismcore.min.js"
      emotion={player.emotion}
      speaking={player.speaking}
      getMouthOpen={player.getMouthOpen}
    />
  )
}
```

```bash
npm install    # inside this directory — there is no npm workspace at the repo root
npm run build  # tsdown → dist/
npm test       # vitest
npm run typecheck
```

---

## What you must supply

| Thing | Why it is not in the package |
|---|---|
| **A Live2D model** | Licensing is an open decision (see `docs/4-build/tracker.md` P1). Every path is injected. `models/live2d/haru_greeter_t03` is present for development; its `bright-model.json` records `commercialUse: RESTRICTED`. Do not ship it to a school before that is resolved. |
| **`live2dcubismcore.min.js`** | Live2D's licence forbids redistribution, so it is not on npm and cannot be bundled. Pass its URL to `<Live2DAvatar cubismCore>` / `ensureCubismCore()`, or load it with a `<script>` tag. |
| **A TTS function** | `(text: string) => Promise<ArrayBuffer>`, injected. The app picks Piper, a hosted API, whatever. |
| **`<think>` stripping** | PROTOCOL.md §5.2 requires reasoning content to be removed *before* text reaches the chunker. That belongs upstream, in `hermes-adapter` / `classroom-core`, where the provider's reasoning format is known. This package does not guess. |

---

## Public API

### `@bright/airi-bridge/act`

```ts
createMarkerParser(onEvent, options?)   // streaming; emits {type:'literal',text} / {type:'special',raw}
createMarkerParserWithHandlers({ onLiteral, onSpecial })
parseMarkerText(text)                   // non-streaming, for tests and pre-rendered narration

parseAct(raw)      // '<|ACT {...}|>'  → ActPayload | undefined
parseDelay(raw)    // '<|DELAY 1.5|>'  → seconds | undefined
parseSignal(raw)   // → { kind: 'act' | 'delay' | 'unknown' }
resolveEmotion(act)// normalises the ActPayload emotion union → { name, intensity }
isActToken / isDelayToken
```

### `@bright/airi-bridge/live2d`

```ts
createLive2DStage(canvas, { model, binding?, ... }) → Live2DStage
  .setMotion(group, index?)   .setExpression(ref | null)
  .setEmotion(emotion)        // → EmotionResolution, via the fallback chain
  .setMouthOpen(0..1)         // written RAW. Do not rescale.
  .setSpeaking(boolean)       .setFocus(x, y)   .resize(w, h)   .destroy()
  .capabilities()             // what the loaded model can actually do
  .ready()                    // resolves when the model is on the stage

ensureCubismCore(url)
parseModelBinding(json) / loadModelBinding(url)   // bright-model.json
resolveEmotionAction(emotion, binding, capabilities) / createEmotionResolver(...)
buildExpressionIndex(defs) / resolveExpressionRef(index, ref)
fitModel(canvas, model, layout)
useLive2DMotionManagerUpdate(...) + the four update plugins
ref / computedRef / toValue                       // the Vue-free Ref shim
```

For `.zip` or directory-upload model sources, add `import '@bright/airi-bridge/live2d/zip-loader'` once, before loading any model. It is a separate entry point because importing it patches pixi-live2d-display's static `ZipLoader`/`FileLoader` in place. A plain `.model3.json` URL does not need it.

### `@bright/airi-bridge/speech`

```ts
createSpeechPlayer({ tts, audio, ttsMaxConcurrent?, chunker?, ...events }) → SpeechPlayer
  .speak(options?) → { turnId, push(delta), end(), cancel(reason?) }
  .isSpeaking()  .getMouthOpen()  .setMuted(b)  .isMuted()  .stopAll()  .dispose()

createWebAudioBackend({ audioContext?, destination?, lipSyncProfile?, volume? })
asOpaqueBackend(backend)
```

### `@bright/airi-bridge/react`

```tsx
<Live2DAvatar model binding? cubismCore? emotion? speaking? getMouthOpen? className? style?
              fallback? renderError? stageOptions? onReady? onError? />

useSpeechPlayer({ tts, lipSyncProfile?, audio?, muted?, ...events })
  → { speak, say, speaking, emotion, getMouthOpen, setMuted, muted, stopAll, player }
```

`getMouthOpen` is a stable function, not state. `<Live2DAvatar>` samples it once per animation frame; putting the mouth position in React state would re-render the tree sixty times a second.

### `@bright/airi-bridge/lipsync` — browser only

`createLive2DLipSync(audioContext, profile, options?)`. Kept out of every other entry point because `wlipsync` subclasses `AudioWorkletNode` at module scope; a static import breaks SSR and Node. All other entry points import cleanly in Node — there is a test for it.

---

## The invariants, and where each one lives

From PROTOCOL.md §5 and §6. If you change any of these, you will hear it.

| # | Invariant | Enforced in |
|---|---|---|
| §5.1 | **Retain a 5-character tail** when scanning for `<\|`. A token split across two SSE chunks must never leak as spoken text. | `src/act/marker-parser.ts`; `TAG_TAIL_RETAIN` from contracts, with a load-time assertion that it still covers the longest opener |
| §5 | Unterminated tokens are dropped at stream end, never emitted as text | `marker-parser.ts` `end()` |
| §5.3 | Back-pressure: `await` the parser on every delta | `consume()` awaits its handlers. The upstream `useLlmmarkerParser` wrapper does **not** — which is why it was not the API we exposed |
| §5 | DELAY is **space** separated, never colon | vendored `parsers/delay.ts` |
| §6.1 | Chunker `boost = 2` — first two segments bypass the min-word rule | vendored `tts-chunker.ts`, defaulted in `speech/player.ts` |
| §6.2 | TTS 4-way concurrent, playback strictly in **text** order, failures store `null` so the gate advances | vendored `speech-pipeline.ts` (`scheduleCompletedRequests`) |
| §6.3 | A special attached to a segment fires **after** that segment's audio | vendored `speech-pipeline.ts` (`enqueuePlayback` awaits `waitForPlayback`) |
| §6.4 | **Muting must still dispatch specials** | *Not in the vendored code.* It is a property of the `play` function. `createWebAudioBackend` implements mute as a `GainNode` at 0 and taps lip-sync **before** the gain, so audio runs full duration and the mouth keeps moving |
| §6.5 | `getMouthOpen()` returns **0…0.7**, written **raw** to `ParamMouthOpenY` (0…1). Do not rescale | `stage.setMouthOpen` clamps to [0,1] and nothing more. AIRI's `Math.min(x, 100)` in `Model.vue` is dead code, not a 0-100 scale — it is not copied |
| — | `speaking` is per **utterance**, not per segment | `speech/player.ts`. Tracking playback alone flaps `[true,false,true,false,…]` in the gap between segments, which restarts the 200 ms lip-sync release tail between every clause and makes the mouth stutter shut mid-sentence. Speaking ends only when no audio is playing **and** no intent is still running |

The last one is verified against the real model: `real-model.test.ts` loads `haru_greeter_t03.moc3`, confirms `ParamMouthOpenY` has range `[0,1]`, writes `0.7` and reads it back, then writes `70` and shows it saturating at `1` — the exact bug a rescale would produce.

---

## Emotion dispatch is config-driven

`EMOTION_MOTION_GROUP` in the contracts maps each emotion to a capitalised motion group (`neutral` → `Idle`). That is the right default and it stays the default. It is not sufficient on its own.

Real models mostly do not ship per-emotion motion groups. Haru has motion groups **`Idle` and `Tap`, nothing else**, so eight of the nine contract entries miss. Without a per-model binding the avatar would appear to work while doing nothing distinct — a silent failure in front of a class.

So each model directory carries a `bright-model.json`:

```jsonc
{
  "emotionChannel": "expression",          // or "motion"
  "emotionMap": {
    "happy":   { "expression": "F05" },    // model3.json Name, file basename, or index
    "neutral": { "expression": null }      // null = clear the active expression
  },
  "motionGroups": { "available": ["Idle", "Tap"], "idle": "Idle", "fallback": "Idle" },
  "lipSync":  { "parameter": "ParamMouthOpenY", "range": [0, 1] },
  "layout":   { "anchor": "bottom-right", "scale": 0.22, "offsetX": 0, "offsetY": 0.05 }
}
```

No expression id and no motion group name is hard-coded anywhere in this package.

**The fallback chain** (`resolveEmotionAction`), in order, never dead-ending:

1. the binding's configured **expression**, if the model has it
2. the binding's configured **motion group**, if the model has it
3. the **contract** motion group (`EMOTION_MOTION_GROUP`), if the model has it
4. `motionGroups.fallback` (normally `Idle`), if the model has it
5. nothing — `{ kind: 'none' }`, and never a throw

`createEmotionResolver` logs each distinct degraded emotion **once**. An emotion that misses will miss on every turn; a warning per frame in front of a class is worse than the miss.

### The expression-reference trap

In `haru_greeter_t03.model3.json` the expression `Name` and its file basename are **different and off by one**: `{ "Name": "f04", "File": "expressions/F05.exp3.json" }`. A human authoring the binding reads the directory and writes `"F05"`.

Worse, the two key spaces overlap: `"F05"` lowercased is `"f05"`, which is the `Name` of a *different* entry. A case-insensitive `Name`-first lookup returns the neighbour — every emotion one off, and still "working". The integration test caught exactly this during development. `resolveExpressionRef` therefore matches: exact `Name` → exact file basename → case-insensitive file basename → case-insensitive `Name`, with a numeric index always unambiguous.

---

## Ported verbatim vs rewritten

### Vendored — copied, headers name the upstream path and every deviation

| Path here | From AIRI | Deviation |
|---|---|---|
| `vendor/model-driver-lipsync/live2d/index.ts` + `shared/wlipsync/profile.json` | `packages/model-driver-lipsync/src/…` | none |
| `vendor/stream-kit/queue.ts` | `packages/stream-kit/src/queue.ts` | none |
| `vendor/pipelines-audio/{types,stream,timeline,priority,eventa,speech-pipeline}.ts` | `packages/pipelines-audio/src/…` | none |
| `vendor/pipelines-audio/processors/tts-chunker.ts` | same | none |
| `vendor/pipelines-audio/managers/playback-manager.ts` | same | `errorMessageFrom` from a local 12-line util instead of `@moeru/std` |
| `vendor/pipelines-audio/llm-streaming-control/{types,controller,parsers/*}.ts` | same | two type-only annotations in `controller.ts` so it compiles under `strict: true` (upstream leaves `strict` off) |
| `vendor/pipelines-audio/llm-streaming-control/payloads.ts` | same | the emotion vocabulary is imported from `packages/contracts` rather than redeclared |
| `live2d/{decode-zip-filename,eye-motions,live2d-zip-loader}.ts` | `packages/stage-ui-live2d/src/utils/…` | none |

`@moeru/eventa` is taken as a real dependency rather than shimmed: the speech pipeline unwraps eventa's `{ body }` envelope (`payload?.body ?? payload`), and a hand-rolled emitter would have to reproduce that exactly.

`transcript-buffer.ts` is not vendored — it is STT-side and Bright does not use it.

### Ported — de-Vue'd, behaviour preserved

| Path here | From AIRI | What changed |
|---|---|---|
| `live2d/motion-manager.ts` (522 → ~480 lines) | `composables/live2d/motion-manager.ts` | `Ref<T>` → `./ref` shim; `Ref<any>` → typed; the per-frame web-storage read is an injected getter; the lip-sync parameter id is an argument; beat-sync and expression plugins not ported. The `pre`/`post`/`final` plugin pipeline is untouched |
| `live2d/idle-eye-focus.ts` | `composables/live2d/animation.ts` | `three`'s `MathUtils.lerp/randFloat` inlined (two lines) so `three` is not a dependency |
| `live2d/fit-model.ts` | `composables/live2d/fit-model.ts` | Vue `computed` + `@vueuse` breakpoints → a pure function taking the binding's `layout` |
| `live2d/model-parameters.ts` | `stores/model-parameters.ts` | Pinia + localStorage store → a plain object with upstream's defaults |
| `act/marker-parser.ts` | `core-agent/src/runtime/llm-marker-parser.ts` | rewritten around the *inner* awaiting parser, not the non-back-pressuring push-stream wrapper; constants from contracts |

### Rewritten from scratch

`live2d/stage.ts` replaces `Canvas.vue` + `Model.vue` (~940 lines of Vue) with ~440 lines. `live2d/model-binding.ts`, `live2d/emotion-channel.ts`, `live2d/expression-index.ts`, `speech/audio-backend.ts`, `speech/player.ts` and everything in `src/react/` are new.

### Not ported, and why

| | |
|---|---|
| `beat-sync.ts` (359 lines) | reacts to music. A classroom does not need it. The plugin slot is still there |
| `expression-controller.ts` (282 lines) | AIRI's own expression store and blending. Bright drives expressions through `emotion-channel.ts` + the model's own Cubism expression manager, which is simpler and config-driven. AIRI ships `live2dExpressionEnabled = false` by default, so the ported auto-blink plugin's "expression OFF" branch **is** its production behaviour — fidelity is preserved |
| `eye-tracking.ts` | needs a camera. Phase 2 |
| VRM / MMD / Spine renderers | Live2D only, per `docs/4-build/phase-1-plan.md` §7 |
| `Model.vue`'s theme drop-shadow, model-reload broadcast channel, runtime-motion upload | AIRI product features, not Bright's |

### About AIRI's `patches/pixi-live2d-display.patch`

`docs/3-design/reusing-airi-and-friends.md` warns that `stage-ui-live2d` needs it. Reading it: it only teaches the unpatched `FileLoader`/`ZipLoader` to skip `items_pinned_to_model.json` and to stop URI-encoding archive paths. `live2d-zip-loader.ts` overrides `createSettings` on both loaders and already does this. **Bright runs `pixi-live2d-display@0.4.0` unpatched.**

---

## Tests

`npm test` — 164 tests, 13 files. Notable groups:

**ACT parser (59 tests)** — the part that must be correct.

- Chunk splitting: seven token shapes are split at **every possible index** into two chunks, and one is split at every possible pair of indices into three; each split must produce byte-identical spoken text and exactly the expected specials. Plus a character-by-character feed of a two-token string.
- Specific split points: `ready<` + `|ACT…`, `<|AC` + `T …`, and a closer cut as `…|` + `>ok`.
- The retained tail is asserted to be exactly `TAG_TAIL_RETAIN` characters.
- Unterminated tokens: bare `<|`, half-written `<|ACT {"emotion":"hap`, a token whose closer never arrives across three chunks. All dropped, never spoken. Parser recovers for the next turn; `reset()` discards.
- Look-alikes: a lone `|>` in text, `5 < 6 and 7 < 8`, an unknown `<|WHATEVER 1|>` (a special, not text), and the escaped `<{'|'}…{'|'}>` form.
- Back-pressure: an async handler must complete before `consume()` resolves, and events stay in stream order.
- `parseAct`: bare string, `{name, intensity}`, intensity as a numeric **string**, clamping in both directions, non-finite fallback to 1, case and whitespace normalisation, all nine contract emotions accepted and near-misses (`surprise`, `joy`, `thinking`) rejected, unknown emotion dropped **while keeping `motion`**, non-object emotion payloads, invalid JSON, non-object bodies, missing space after `ACT`.
- `parseDelay`: space form accepted, **colon form rejected**, zero/negative/`1e3`/non-numeric rejected.

**Real model (12 tests)** — loads `live2dcubismcore.min.js` and `haru_greeter_t03.moc3` for real in Node (WebGL is only needed to *draw* a model, not to instantiate one), and reads the real `model3.json` and `bright-model.json`. Asserts the scale trap end-to-end, that Haru really has only `Idle`/`Tap`, that the contract-default binding degrades to `Idle` for every non-neutral emotion, that every referenced expression exists both in `model3.json` and on disk, the `F05` → index 4 resolution, and that all nine emotions resolve with zero warnings. Skips loudly if `models/live2d/` is absent.

**Speech invariants (13 tests)** — text-order playback with deliberately inverted TTS latency; a throwing provider and an empty-buffer provider both advancing the gate; a special firing after its segment and before the next; `boost = 2`; mute proven by running the same utterance muted and unmuted and asserting **identical event sequences**; and a three-sentence utterance asserted to emit exactly `[true, false]` speaking transitions — the loose version of that assertion was passing while real flapping was happening, which is how the release-tail bug above was found.

**Upstream regression tests, carried over** — `tts-chunker`, `playback-manager`, `speech-pipeline`, `llm-streaming-control`, `payloads`, `decode-zip-filename`, and AIRI's own `motion-manager.test.ts`. The last one is the evidence the de-Vue'd port preserved behaviour: only two lines changed (`ref` from our shim, and the mocked module name), every assertion untouched.

**React (9 tests, jsdom)** — the audio graph is built once and disposed on unmount, `getMouthOpen` keeps a stable identity across renders, ACT emotion reaches React state, mute passes through, a `speak()` after unmount does not throw, and changing a handler does not rebuild the graph.

### Three upstream tests are marked `it.fails`

`playback-manager.test.ts` contains three cases that fail against **pristine** upstream source at `b230e16` (verified by diffing our copy against it — identical but for the `errorMessageFrom` import). They encode behaviour AIRI intends but has not implemented: `stopByIntent` ends with `tryStartWaiting()`, and `stealOldest` restarts the stealing item synchronously instead of leaving it queued.

They are marked `it.fails` rather than skipped, so the suite goes red the day we re-vendor a fixed upstream. None of the three is reachable from Bright: `createSpeechPlayer` runs `maxVoices: 1` with no owner ids.

---

## Things worth knowing before you change something

- **`src/vendor/` is read-only.** To change behaviour, wrap it. Every file's header states whether it is verbatim and what deviates.
- **Do not "fix" the chunker's emoji handling.** Grapheme clusters longer than one code unit are dropped from TTS input. That is upstream's deliberate behaviour and it is copied as-is.
- **Do not lower `TAG_TAIL_RETAIN`.** `marker-parser.ts` throws at load time if it stops covering the longest recognised opener.
- **Do not rescale `getMouthOpen()`.** See §6.5 above and the real-model test.
- The Vue-free `Ref` shim has **no reactivity**. Every consumer reads `.value` inside the render loop; React bridges to it by writing in an effect.
- **Clearing an expression is `resetExpression()`, never `setExpression(undefined)`.** pixi-live2d-display's `setExpression` resolves to `false` for an unknown reference *without throwing*, so the wrong call would leave the avatar stuck in its last emotion silently — and `neutral` maps to `expression: null` on the demo model.
- **Every entry point except `/lipsync` and `/live2d/zip-loader` imports cleanly in Node.** `wlipsync` subclasses `AudioWorkletNode`, and `pixi-live2d-display/cubism4` throws, at *module scope*; both are therefore behind dynamic `import()`. Do not convert them back to static imports — it would break SSR and every Node test.

## Licence

MIT. Ported code is Copyright (c) 2024-present Moeru AI Project AIRI Team, MIT — attribution headers are on every ported file and must stay there.
