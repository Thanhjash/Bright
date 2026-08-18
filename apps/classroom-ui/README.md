# classroom-ui

The two screens of the Bright classroom (docs/design/runtime-topology.md §1):

| Route | Who sees it | What it is |
|---|---|---|
| `/classroom` | 30 children, via a projector | full screen, no chrome, board + avatar + overlay |
| `/control` | the facilitator, on the laptop | status, live transcript, six big command buttons |

One app, two routes, two WebSocket connections to `classroom-core` — one with
role `stage`, one with role `control`. In a classroom the laptop uses **Extend
display**, never Mirror: students never see the console.

React 19 · Vite · TypeScript · Tailwind v4 · Zustand · react-router.

---

## Run it

```bash
pnpm install

pnpm dev          # against classroom-core on 127.0.0.1:8004
pnpm dev:mock     # standalone, no backend at all
```

Then open <http://127.0.0.1:3000/classroom> and
<http://127.0.0.1:3000/control>. `/` redirects to `/classroom`.

```bash
pnpm typecheck    # tsc --noEmit
pnpm build        # typecheck + production bundle into dist/
pnpm build:mock   # a shippable demo build with the fixtures baked in
```

For the demo: Chrome fullscreen (`F11`), or `chrome --kiosk
http://127.0.0.1:3000/classroom`. That is the whole Phase 1 packaging story
(docs/design/runtime-topology.md §7).

### Configuration

Every value has a working default, so the app boots with no `.env`.
Copy `.env.example` → `.env.local` to override.

| Variable | Default | Meaning |
|---|---|---|
| `VITE_MOCK` | unset | `1` → fixtures, no backend. `pnpm dev:mock` sets it via `.env.mock` |
| `VITE_BUS_URL` | `ws://127.0.0.1:8004/ws` | the event bus |
| `VITE_CORE_HTTP` | `http://127.0.0.1:8004` | origin for `GET /assets/<id>` |

`VITE_POLL=1 pnpm dev` turns on polling file-watch — needed when running from
WSL against a repo on a Windows drive, where inotify never fires and HMR
silently stops working.

### Mock mode

`VITE_MOCK=1` swaps `WsBus` for `MockBus`. Both implement the same `Bus`
interface and emit the same `Event<T>` envelopes, so **nothing downstream
knows the difference** — the store, the Stage and the console are byte-identical
between mock and live.

`MockBus` plays the server, not the UI: it owns the lesson position, grades the
interactive steps, honours control commands, and replies to `client.hello` with
a `scene.snapshot`.

What the fixture covers (`src/bus/fixtures.ts`, 14 activities):

- **every implemented scene kind** — `idle`, `text` (xl and lg), `image`,
  `vocabulary` (display and `point`), `choice`
- **every stubbed kind** — `sentence_builder`, `matching`, `pronunciation`,
  `roleplay`, `video`, `explore`, each carrying real props
- **interaction round-trips** — tapping a card emits `interaction.point`,
  tapping an option emits `interaction.choice`; the mock grades after ~400 ms
  and answers with a fresh `scene.update` carrying `highlightId` / `revealed`
- **speech** — `speech.say` with inline `<|ACT …|>` tokens, driving subtitles,
  the transcript, and the avatar's emotion
- **overlay states** — student name, listening indicator, mode badge
- **control commands** — pause, resume, skip, back, repeat, and `takeover`
  (which drops the mode to `DEGRADED` and makes the badge appear)
- **snapshot / reset** — `requestSnapshot()` replays a full snapshot

`?step=<n>` on either route jumps the fixture straight to an activity —
e.g. `/classroom?step=10` for the roleplay board. Mock mode only.

---

## Component map

```
src/
├── main.tsx · App.tsx           routes: /classroom, /control
│
├── bus/                         the wire
│   ├── types.ts                 Bus interface + typed server/client event maps
│   ├── emitter.ts               typed emitter over Event<T>
│   ├── wsClient.ts              WsBus — hello, seq gaps, resnapshot, backoff
│   ├── mockClient.ts            MockBus — fixture driver, plays the server
│   ├── fixtures.ts              the demo lesson
│   ├── createBus.ts             the one place that decides mock vs live
│   ├── wiring.ts                the one place events become store state
│   └── BusProvider.tsx          per-route bus + React context
│
├── store/classroom.ts           zustand: scene, lesson, mode, connection,
│                                subtitle, avatar, transcript. Server-driven only.
│
├── stage/
│   ├── Stage.tsx                board 72% / avatar 28%, overlay above both
│   ├── SceneRouter.tsx          scene.kind → component; unknown kind → error card
│   ├── DisconnectedNotice.tsx   nothing on /classroom unless disconnected
│   ├── BoardLayer/
│   │   ├── IdleBoard · TextBoard · ImageBoard          fully implemented
│   │   ├── VocabularyBoard · ChoiceBoard               fully implemented, interactive
│   │   ├── stubs.tsx            matching · sentence_builder · pronunciation ·
│   │   │                       roleplay · explore · video — readable placeholders
│   │   ├── ErrorCard.tsx        unknown kind, bad version, render crash
│   │   └── parts.tsx            BoardShell, Prompt, MediaTile, StubBoard
│   ├── AvatarLayer/
│   │   ├── Avatar.tsx           <Avatar emotion speaking mouthOpen /> — the seam
│   │   └── AvatarLayer.tsx      layout + narrow store subscription
│   └── OverlayLayer/            SubtitleBar · StudentName · ListeningIndicator ·
│                                ModeBadge (DEGRADED/OFFLINE only)
│
├── speech/speakingDriver.ts     placeholder mouth animation; airi-bridge replaces it
│
├── lib/
│   ├── scene.ts                 kind → props narrowing (composes @contracts)
│   ├── assets.ts                asset:// → /assets/<id>, placeholders in mock
│   ├── act.ts                   display-only <|ACT|> scrubber
│   └── env.ts                   VITE_* with defaults
│
└── routes/
    ├── classroom/ClassroomRoute.tsx
    └── control/                 ControlRoute · StatusPanel · CommandBar ·
                                 TranscriptPanel · ConnectionPill
```

### Types

Everything on the wire comes from `packages/contracts/src/index.ts`, imported
as `@contracts` (aliased in both `vite.config.ts` and `tsconfig.json`).
**No wire type is redefined here.** `src/lib/scene.ts` *composes* them into a
kind → props map, because `SceneProps` is a bare union whose discriminant
(`kind`) lives on `Scene`, so TypeScript cannot narrow `scene.props` alone.

### Two invariants worth not breaking

**The store is a pure reflection of server events.** Every mutator is called
from `bus/wiring.ts` and nowhere else. The UI never advances the lesson, grades
an answer, or picks the next scene — it renders state and emits interactions
(docs/design/runtime-topology.md §4, rule 2). Optimistic press feedback is deliberately kept in
component-local state so this stays literally true.

**Never patch across a gap.** `WsBus` tracks `seq` per connection. On a gap it
discards local state, re-sends `client.hello`, and drops every state-carrying
event until the `scene.snapshot` lands. A fresh connection is treated as a gap.
An unknown `v` is rejected loudly and never rendered.

### Adding a scene kind

1. Add it to `PROTOCOL.md` and `packages/contracts` first — never here first.
2. Add the kind → props row in `src/lib/scene.ts` (`ScenePropsByKind`,
   `SCENE_KINDS`, `SCENE_LABEL`). The `satisfies` clause makes a missing row a
   build error.
3. Write the board in `src/stage/BoardLayer/`.
4. Add a `case` in `SceneRouter.tsx` and a fixture step in `bus/fixtures.ts`.

### Replacing the avatar

`packages/airi-bridge` owns the real Live2D character. The seam is exactly:

```tsx
<Avatar emotion={Emotion} speaking={boolean} mouthOpen={number} />
```

`mouthOpen` is `0…0.7` — the value Live2D writes raw to `ParamMouthOpenY`
(PROTOCOL.md §6.5). Do not rescale it. Swapping in the real renderer means
replacing the body of `AvatarLayer/Avatar.tsx` and deleting
`speech/speakingDriver.ts`; no other file changes.

---

## Interpretations of PROTOCOL.md

Places the protocol was silent and this client had to choose. Each is a
candidate for a protocol amendment.

1. **There is no "request a snapshot" event.** The catalog defines
   `scene.snapshot` as *the reply to `client.hello`*, so a resnapshot is a
   re-sent `client.hello` carrying our last `stateVersion`. It assumes core
   answers every hello with a snapshot, not only when its version is higher.

2. **Outbound envelopes.** "Every message on the bus" is an `Event<T>`, so
   client→server messages carry one too. `seq` is a **separate client-side
   counter, reset per connection** (the protocol only describes the server's
   sequence), and `stateVersion` is the highest we have seen. Core is expected
   to ignore both, or to use `stateVersion` for staleness checks.

3. **`interaction.point` coordinates are normalised 0…1 within the tapped
   element**, not viewport pixels — the projector resolution is unknown to core
   and a pixel value would be meaningless to it. The centre of a card is
   `(0.5, 0.5)`.

4. **Vocabulary `interaction: 'tap'` emits `interaction.point`.** The protocol
   defines the mode but no matching event; a tap on a card *is* a point at that
   card. `'none'` renders inert cards.

5. **Subtitle precedence and lifetime.** `scene.overlay.subtitle` is
   authoritative; the current `speech.say` text fills in only when the overlay
   has none. A new `scene.update` retires the previous spoken line — unless the
   teacher is still mid-utterance, since core may push a scene while speaking.
   Without that rule a silent activity would keep projecting the last thing
   said, indefinitely.

6. **Mode badge precedence.** `scene.overlay.modeBadge` wins; the last
   `mode.changed` is the fallback for a scene that predates the mode switch.
   Never shown in `FULL` (§7).

7. **`speech.say` text may still contain `<|ACT …|>`.** `lib/act.ts` strips
   tokens before anything is displayed, and lifts the emotion out. This is a
   display-safety net only — the real, back-pressured, tail-retaining stream
   parser belongs to airi-bridge (§5.1).

8. **`error` is in the TypeScript `EventType` union but not in the PROTOCOL.md
   catalog.** Treated as server→client with an `ErrorPayload`; logged and shown
   in the transcript, never on the projector.

9. **`ImageProps` has no `autoplay` in the TS contract**, though PROTOCOL.md
   groups `image | video` under one shape that includes it. The TS types were
   followed as the tighter of the two.

10. **`speech.say.audioAsset` is currently ignored** — audio playback lands
    with airi-bridge. Until then subtitle timing is estimated from word count.

11. **The console echoes its own `control.command` into the transcript** as a
    `system` line. It is a log of what was sent, not a claim about state; the
    only confirmation of a command is the scene actually changing.
