/**
 * The room's one status dock -- the strip below the board.
 *
 * There is no Start button. She opens her own class the moment the Stage
 * claims the audio lease -- the presence gate in `teacher_os.pulse_teacher`.
 * A button to begin is an adult decision sitting on the teaching path, which
 * NS-1 forbids, and the room is meant to run itself.
 *
 * There is no hold-to-talk either. The room listens whenever she is not
 * speaking (`voiceGate`), because a child in a remote classroom has no
 * keyboard and no mouse.
 *
 * This is also where the subtitle lives now (imported from `OverlayLayer`),
 * and where the heard-echo chip lives. All three used to be three
 * independently bottom-anchored elements, each claiming the same strip of
 * screen for itself -- which is exactly how the subtitle and the status pill
 * ended up printed on top of each other. They are now three children of ONE
 * flex column, in a fixed order (heard, then subtitle, then the status
 * card), so they stack instead of collide. Not a chat -- nothing here is
 * tapped, and nothing here is ever wider than the safe band between the
 * camera corner and the avatar's column.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CORE_HTTP, IS_MOCK } from '../lib/env'
import { HEARD_PREFIX, ROOM_LABELS } from '../room/labels'
import { createMicRecorder } from '../speech/micRecorder'
import type { VoiceFragment } from '../speech/voiceGate'
import { createVoiceGate } from '../speech/voiceGate'
import { SttError, transcribe } from '../speech/stt'
import { useClassroom } from '../store/classroom'
import { SubtitleBar } from './OverlayLayer/SubtitleBar'

/**
 * Mock-mode-only visual QA seam, the same shape as `mockClient.ts`'s
 * `?step=`: it lets a screenshot exercise the heard-echo chip without
 * driving a real microphone through Core. It is inert (and unread) whenever
 * `VITE_MOCK` is not `1`, so it never reaches a kiosk build.
 */
function mockHeardOverride(): string | null {
  if (!IS_MOCK || typeof location === 'undefined') return null
  return new URLSearchParams(location.search).get('heard')
}

type Status = {
  ok?: boolean
  phase?: string
  hermesUp?: boolean
  speechUp?: boolean
  stageAudioOwner?: boolean
  readyToStart?: boolean
  sessionOpen?: boolean
  turnBusy?: boolean
  lastSay?: string | null
  lastFault?: { error?: string } | null
}

type DockPhase = 'asleep' | 'waking' | 'speaking' | 'listen' | 'hearing' | 'thinking' | 'fault'

async function readJson(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text()
  try {
    return JSON.parse(text) as Record<string, unknown>
  } catch {
    throw new Error(text.slice(0, 160) || `HTTP ${res.status}`)
  }
}

export function RoomDock() {
  const speaking = useClassroom((s) => s.avatar.speaking)
  const connected = useClassroom((s) => s.connection.state === 'open' || s.connection.state === 'mock')
  const [status, setStatus] = useState<Status>({})
  const [phase, setPhase] = useState<DockPhase>('asleep')
  const [heard, setHeard] = useState<string | null>(mockHeardOverride)
  /** True while phrases are still arriving for the sentence being spoken. The
   *  chip is styled differently so a child can see the words are not final. */
  const [growing, setGrowing] = useState(false)
  const [hint, setHint] = useState<string | null>(null)
  // The dock's phase comes from /teacher/status, which knows nothing about the
  // microphone. Without this the room went on saying "Tới lượt con nói" while
  // the gate was dead and nothing was listening at all.
  const [deaf, setDeaf] = useState(false)
  const mic = useRef(createMicRecorder())
  const phaseRef = useRef<DockPhase>('asleep')

  const setDock = useCallback((next: DockPhase) => {
    phaseRef.current = next
    setPhase(next)
  }, [])

  useEffect(() => {
    return () => mic.current.release()
  }, [])

  useEffect(() => {
    let cancel = false
    const tick = async () => {
      try {
        const body = (await fetch(`${CORE_HTTP}/teacher/status`).then((r) => r.json())) as Status
        if (cancel) return
        setStatus(body)
        if (phaseRef.current === 'hearing') return
        if (body.sessionOpen) {
          if (body.turnBusy) setDock('thinking')
          else setDock(speaking ? 'speaking' : 'listen')
        } else if (!body.hermesUp && connected) {
          setDock('fault')
        } else {
          setDock('asleep')
        }
      } catch {
        if (!cancel && phaseRef.current === 'asleep') setDock(connected ? 'fault' : 'asleep')
      }
    }
    void tick()
    const id = window.setInterval(() => { void tick() }, 2500)
    return () => {
      cancel = true
      window.clearInterval(id)
    }
  }, [connected, setDock, speaking])

  useEffect(() => {
    if (phaseRef.current === 'hearing' || phaseRef.current === 'thinking' || phaseRef.current === 'waking') return
    if (status.sessionOpen) setDock(speaking ? 'speaking' : 'listen')
  }, [setDock, speaking, status.sessionOpen])

  // One clip at a time, newest wins.
  //
  // Whisper is single-threaded behind one lock in the speech service, and a
  // clip costs 3-10s on this CPU. The gate can produce clips far faster than
  // that. Measured on 2026-08-18 with no backpressure at all: the ASR queue
  // grew 0 -> 3s -> 17s -> 116s -> **200s**, so by the end the teacher was
  // answering something a child said three minutes earlier. Queue depth, not
  // model speed, was the dominant latency.
  //
  // Two rules fix it. Never run two transcriptions at once, and while one is
  // running keep only the LATEST clip that arrived -- an older clip is a
  // staler answer, and a child who repeats themselves means the second try is
  // the one they want heard.
  const inFlight = useRef(false)
  const pending = useRef<{ audio: Blob; durationMs: number } | null>(null)

  // ── the live line ──────────────────────────────────────────────────────
  //
  // Phrases of one sentence arrive in order and are transcribed one at a time
  // behind the same single-flight lock. Newest-wins is right for whole
  // utterances and WRONG for phrases: dropping one leaves a hole in the middle
  // of a sentence, which reads as something the child never said. So this
  // queue drops nothing; when it gets deep the GATE stops cutting instead, and
  // the final clip covers whatever was not cut.
  const fragQueue = useRef<VoiceFragment[]>([])
  const fragBusy = useRef(false)
  /** Texts of the settled phrases of the current sentence, in order. */
  const said = useRef<string[]>([])
  /** Which sentence those belong to; a late phrase from a previous one is
   *  discarded rather than glued onto the sentence being spoken now. */
  const saidFor = useRef(-1)
  /** What the first phrase turned out to be, pinned onto the rest so one
   *  sentence cannot flap between languages halfway through. */
  const saidLanguage = useRef<string | null>(null)
  /** A phrase that failed to transcribe. A sentence with a hole in it must
   *  never reach the teacher -- answering "My favourite is" as if it were the
   *  whole question is worse than answering nothing -- so a holed sentence
   *  falls back to the one whole-utterance call the gate also provides. */
  const holed = useRef(false)

  const submitClip = useCallback(async (clip: { audio: Blob; durationMs: number }) => {
    if (inFlight.current) {
      pending.current = clip          // drop whatever was queued before it
      return
    }
    if (skipNextClip.current) {
      // The phrase stream owns this sentence. Hold the whole-utterance clip
      // rather than transcribing it: if a phrase fails to come back, the
      // sentence would have a hole in it, and one whole-clip call is the only
      // honest way to recover. If every phrase lands, this is dropped unheard.
      skipNextClip.current = false
      wholeClip.current = clip
      void drainRef.current?.()
      return
    }
    inFlight.current = true
    // Not while the child is still talking -- the phrase path owns the pill
    // until the sentence ends.
    if (phaseRef.current !== 'hearing') setDock('thinking')
    try {
      const heard = await transcribe(clip.audio)
      const heardText = heard.text.trim()
      // Whisper's own verdict on whether this was speech at all, which the
      // room measured and then ignored. Observed in one real session: TEN of
      // twelve clips came back `no-speech 1.000` -- a chair, a cough, the
      // teacher's own tail of reverb -- and every one of them was posted as a
      // turn, so she answered things nobody said. That is why she asks "Hi,
      // how are you?" into an empty room.
      //
      // 0.9 rather than 1.0: the certain cases are what matter here, and a
      // real utterance in a noisy classroom rarely scores that high. When it
      // is wrong, the cost is one lost sentence and the child repeats; the
      // other way round, the cost is the teacher talking to furniture.
      if (heardText && heard.noSpeechProbability < 0.9) {
        setHeard(heardText)
        setHint(null)
        const res = await fetch(`${CORE_HTTP}/teacher/turn`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          // Whisper already decided which language this was, and the room
          // used to throw it away. A Grade-3 beginner switching to their home
          // language is the clearest "I am lost" signal in the room, and it
          // costs nothing to pass on.
          body: JSON.stringify({ text: heardText, language: heard.language ?? null }),
        })
        const body = await readJson(res)
        if (!res.ok) throw new Error(JSON.stringify(body).slice(0, 180))
      }
      setDock('listen')
    } catch (err) {
      // A clip with no speech in it is the normal case in a room with noise,
      // not a fault worth shouting about on the projector.
      if (err instanceof SttError && err.failure === 'empty') setHint(null)
      else setHint(err instanceof SttError ? err.message : 'The teacher needs a moment.')
      setDock('listen')
    } finally {
      inFlight.current = false
      const next = pending.current
      pending.current = null
      if (next) void submitClipRef.current?.(next)
    }
  }, [setDock])

  /** Post one finished sentence. Shared by the phrase path and the fallback. */
  const postTurn = useCallback(async (text: string, language: string | null) => {
    const res = await fetch(`${CORE_HTTP}/teacher/turn`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text, language }),
    })
    const body = await readJson(res)
    if (!res.ok) throw new Error(JSON.stringify(body).slice(0, 180))
  }, [])

  const drainFragments = useCallback(async () => {
    if (fragBusy.current) return
    const frag = fragQueue.current.shift()
    if (!frag) return
    fragBusy.current = true
    try {
      // A new sentence: forget the last one's words rather than continue it.
      if (frag.utteranceId !== saidFor.current) {
        saidFor.current = frag.utteranceId
        said.current = []
        saidLanguage.current = null
        holed.current = false
      }

      if (frag.audio.size > 0) {
        try {
          const part = await transcribe(frag.audio, {
            language: saidLanguage.current,
            // A phrase that turns out to be a breath is ordinary and must not
            // break the chain of phrases around it.
            allowEmpty: true,
          })
          if (part.text) said.current.push(part.text)
          if (!saidLanguage.current && part.language) saidLanguage.current = part.language
        } catch {
          // Transport, not silence. Mark the sentence holed; the whole-clip
          // fallback below will carry it instead.
          holed.current = true
        }
      }

      const line = said.current.join(' ').trim()
      if (line) {
        setHeard(line)
        setHint(null)
      }
      setGrowing(!frag.last)

      if (!frag.last) return

      // The sentence is over.
      //
      // What the CHILD saw was the phrases: fast, and good enough to know she
      // is being heard. What the TEACHER gets is the whole utterance decoded
      // in one pass, because a phrase carries less context and is measurably
      // worse for it -- the same sentence came back "I am 9 years old today"
      // whole and "I am not ironier as a soldier today" in pieces. She must
      // answer what was said, not an approximation of it.
      //
      // The extra call costs ~2s and lands inside the window where the pill
      // already says "Cô đang nghĩ" and a hosted model turn is about to spend
      // 7-19s anyway. Nobody sees it.
      const whole = wholeClip.current
      wholeClip.current = null
      setDock('thinking')

      let settled = ''
      let settledLanguage = saidLanguage.current
      if (whole) {
        try {
          const final = await transcribe(whole.audio, { allowEmpty: true })
          settled = final.text.trim()
          if (final.language) settledLanguage = final.language
        } catch {
          // Fall through to the phrases; an approximate sentence beats none.
        }
      }
      // The phrases are the fallback now, not the source of truth.
      const toSend = settled || (holed.current ? '' : line)
      if (!toSend) {
        setDock('listen')
        return
      }
      setHeard(toSend)
      try {
        await postTurn(toSend, settledLanguage)
      } catch {
        setHint('The teacher needs a moment.')
      }
      setDock('listen')
    } finally {
      fragBusy.current = false
      if (fragQueue.current.length) void drainRef.current?.()
    }
  }, [postTurn, setDock])

  const drainRef = useRef<typeof drainFragments | null>(null)
  drainRef.current = drainFragments

  /** Set the moment the gate says a sentence has ended, so the whole-clip
   *  lane stands down before it can start a second transcription of audio the
   *  phrase lane is already handling. */
  const skipNextClip = useRef(false)
  /** The whole-utterance clip, held in case the phrase lane holes out. */
  const wholeClip = useRef<{ audio: Blob; durationMs: number } | null>(null)

  // `submitClip` recurses through a ref so the callback identity stays stable.
  const submitClipRef = useRef<typeof submitClip | null>(null)
  submitClipRef.current = submitClip

  // The room listens by itself. The gate never opens while she is speaking --
  // the Stage is the only loudspeaker, so an open mic during Piper output
  // would feed her own voice back into Whisper.
  useEffect(() => {
    const recorder = mic.current
    const gate = createVoiceGate(recorder, {
      onClip: (clip) => { void submitClip(clip) },
      onFragment: (fragment) => {
        // Claim the sentence NOW, synchronously. `finalizeCapture` emits the
        // last fragment and then awaits `mic.stop()`, so `onClip` follows
        // within milliseconds -- long before this fragment has been
        // transcribed. Without claiming it here the whole-clip lane starts a
        // second transcription of the same audio and posts its own wording.
        if (fragment.last) skipNextClip.current = true
        fragQueue.current.push(fragment)
        void drainRef.current?.()
      },
      pendingFragments: () => fragQueue.current.length + (fragBusy.current ? 1 : 0),
      onStateChange: (state) => {
        setDeaf(state === 'error')
        // `hearing` -- the amber pill with the moving bars and "Cô đang nghe
        // con" -- was fully built and NOTHING EVER SET IT. The dock's phase
        // came only from `/teacher/status`, which knows nothing about a
        // microphone, so while the room was recording it still said "your turn
        // to speak". A child could not tell whether she was listening, which is
        // the one thing this strip exists to say.
        //
        // The gate is the only thing that knows, so it is the thing that says
        // so. The status poll already refuses to overwrite `hearing`.
        if (state === 'capturing') {
          setDock('hearing')
          setGrowing(true)
        }
        else if (phaseRef.current === 'hearing')
          // `gated` means she started speaking and the capture was abandoned.
          // Without this branch the dock kept saying "Cô đang nghe con" while
          // SHE was talking -- the status poll refuses to overwrite `hearing`,
          // so it stuck there until the gate reached `listening` again.
          setDock(state === 'gated' ? 'speaking' : 'listen')
      },
      onError: (message) => setHint(message),
    })
    gate.start()
    return () => gate.stop()
  }, [submitClip])

  const ready = Boolean(status.hermesUp && status.stageAudioOwner)
  const light = !connected
    ? 'bg-coral'
    : ready && status.speechUp
      ? 'bg-mint'
      : status.hermesUp
        ? 'bg-amber'
        : 'bg-coral'

  const copy = deaf ? ROOM_LABELS.deaf : labelFor(phase, ready)

  const waiting = phase === 'asleep' || phase === 'fault' || phase === 'waking'
  // A live mic problem (`hint`) always outranks the resting sub-label -- it
  // is the more actionable thing to show under the same headline, not a
  // second banner competing for its own row.
  const subLine = hint ?? copy.sub

  return (
    // One flex column owns the whole strip below the board: heard chip on
    // top, the subtitle in the middle, the status card at the foot. Order
    // here is the stacking order on screen -- nothing in this file positions
    // a sibling independently any more, which is what let the subtitle and
    // the status pill land on top of each other before.
    <div
      data-stage="chrome"
      className="pointer-events-none absolute inset-x-0 bottom-0 top-[var(--board-bottom)] z-[28] flex flex-col items-center justify-end gap-[0.8vh] pb-[1.6vh] pl-[var(--camera-col)] pr-[calc(var(--avatar-col)+2vw)]"
    >
      {/*
        The live line. Phrases land here as they settle, so the child sees
        words while still speaking -- but in the small chip, deliberately, and
        never on the chalk. A provisional word on the chalkboard is a word a
        Grade-3 child reads aloud and copies into a book.

        `line-clamp-2` and not `truncate`: truncation hides the END of the
        line, and the end is the newest words -- the whole point.

        The amber ring is the same amber as the `hearing` pill below, so the
        two read as one thing: she is listening, and this is what she has so
        far. It goes back to the quiet ring the moment the sentence is sent,
        without any word moving -- a fragment is decoded from its own audio
        alone, so nothing already on screen is ever rewritten.
      */}
      {heard ? (
        <p
          data-stage="heard"
          data-growing={growing ? 'true' : 'false'}
          className={`pointer-events-none line-clamp-2 max-w-full rounded-3xl bg-ink-950/70 px-[1.2vw] py-[0.5vh] font-display text-[clamp(0.75rem,1.05vw,1rem)] text-cream/80 transition-[box-shadow] duration-200 ${
            growing ? 'ring-2 ring-amber/45' : 'ring-1 ring-cream/15'
          }`}
        >
          <span className="text-muted">{HEARD_PREFIX}</span> {heard}
          {growing ? <span className="animate-pulse text-amber">▍</span> : null}
        </p>
      ) : null}

      <SubtitleBar />

      <div
        data-stage="dock"
        className={
          'pointer-events-none flex items-center gap-[0.6vw] rounded-[1.3rem] px-[1.4vw] py-[0.7vh] font-display ' +
          (phase === 'hearing' ? 'bg-amber/90 text-ink-900' : 'bg-ink-950/74 text-cream/90')
        }
      >
        {waiting ? (
          <span className={`h-[0.9vh] w-[0.9vh] min-h-[7px] min-w-[7px] rounded-full ${light}`} aria-hidden />
        ) : (
          <span className="flex h-[2.2vh] min-h-[16px] items-end gap-[2px]" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className={`w-[3px] rounded-full ${phase === 'hearing' ? 'bg-ink-900' : 'bg-mint'}`}
                style={{
                  height: `${[40, 70, 100, 55][i]}%`,
                  animation: phase === 'hearing' ? 'listen 1.1s ease-in-out infinite' : undefined,
                  animationDelay: `${i * 90}ms`,
                  transformOrigin: 'bottom',
                }}
              />
            ))}
          </span>
        )}
        <span className="flex flex-col items-start leading-tight">
          <span className="text-[clamp(0.85rem,1.3vw,1.15rem)] font-bold">{copy.cta}</span>
          <span className={`text-[clamp(0.6rem,0.85vw,0.78rem)] ${phase === 'hearing' ? 'text-ink-900/70' : 'text-cream/65'}`}>
            {subLine}
          </span>
        </span>
      </div>
    </div>
  )
}

function labelFor(phase: DockPhase, ready: boolean): { cta: string; sub: string } {
  // Whose turn is it? That is the only question this chrome answers, and in a
  // classroom it is the one thing a child cannot work out from the board alone.
  // The room listens by itself now, so nothing here may instruct anyone to
  // press, hold or release: there is no button, and a child has no keyboard.
  // Both languages, because the class reads Vietnamese and is learning English.
  // The words live in room/labels.ts, the one file a Laos school replaces.
  // Nothing here reads, parses or branches on the text (NS-7).
  switch (phase) {
    case 'speaking':
      return ROOM_LABELS.speaking
    case 'hearing':
      return ROOM_LABELS.hearing
    case 'thinking':
      return ROOM_LABELS.thinking
    case 'listen':
      return ROOM_LABELS.listening
    case 'fault':
      return ROOM_LABELS.fault
    case 'waking':
      return ROOM_LABELS.waking
    default:
      return ready ? ROOM_LABELS.comingReady : ROOM_LABELS.comingWaiting
  }
}
