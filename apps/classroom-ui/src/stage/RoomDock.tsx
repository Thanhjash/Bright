/**
 * The only chrome on the projector.
 *
 * There is no Start button. She opens her own class the moment the Stage
 * claims the audio lease -- the presence gate in `teacher_os.pulse_teacher`.
 * A button to begin is an adult decision sitting on the teaching path, which
 * NS-1 forbids, and the room is meant to run itself.
 *
 * There is no hold-to-talk either. The room listens whenever she is not
 * speaking (`voiceGate`), because a child in a remote classroom has no
 * keyboard and no mouse. This component is a status chip and a fault banner.
 * Not a chat. Subtitles stay on the board.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CORE_HTTP } from '../lib/env'
import { ROOM_LABELS } from '../room/labels'
import { createMicRecorder } from '../speech/micRecorder'
import { createVoiceGate } from '../speech/voiceGate'
import { SttError, transcribe } from '../speech/stt'
import { useClassroom } from '../store/classroom'

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
  const [heard, setHeard] = useState<string | null>(null)
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

  const submitClip = useCallback(async (clip: { audio: Blob; durationMs: number }) => {
    if (inFlight.current) {
      pending.current = clip          // drop whatever was queued before it
      return
    }
    inFlight.current = true
    setDock('thinking')
    try {
      const heardText = (await transcribe(clip.audio)).text.trim()
      if (heardText) {
        setHeard(heardText)
        setHint(null)
        const res = await fetch(`${CORE_HTTP}/teacher/turn`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ text: heardText }),
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
      onStateChange: (state) => setDeaf(state === 'error'),
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

  return (
    <>
      {/* What the child said, echoed back. It lives BELOW THE BOARD -- the top
          of the room is chalk now, and this chip was landing on the first line
          she writes. Everything the system says about itself lives under the
          board's bottom edge; the chalk is the child's. */}
      {/* (kept for provenance) It used to live at the TOP of the room --
          her subtitle owns the bottom, and when both sat in the same corner
          they overlapped on a real projector. Top = the class, bottom = the
          teacher. */}
      {heard ? (
        <p
          data-stage="heard"
          className="pointer-events-none absolute left-1/2 top-[calc(var(--board-bottom)+1vh)] z-[29] max-w-[52%] -translate-x-1/2 truncate rounded-full bg-ink-950/78 px-6 py-2 font-display text-[clamp(0.95rem,1.4vw,1.3rem)] text-cream/90 ring-1 ring-cream/15"
        >
          {heard}
        </p>
      ) : null}
    <div
      data-stage="dock"
      className="pointer-events-none absolute inset-x-0 bottom-0 z-[28] top-[var(--board-bottom)] flex flex-col items-center justify-end gap-[0.6vh] pb-[2vh] lg:pr-[calc(var(--avatar-col)*0.6)]"
    >
      {hint ? (
        <p className="pointer-events-none max-w-[36rem] text-center font-display text-[clamp(0.95rem,1.4vw,1.2rem)] text-amber">
          {hint}
        </p>
      ) : null}

      {phase === 'asleep' || phase === 'fault' || phase === 'waking' ? (
        <div
          data-stage="waiting"
          className="pointer-events-none flex min-h-[4.4rem] items-center justify-center gap-3 rounded-full bg-ink-950/70 px-8 py-4 font-display text-[clamp(1.1rem,1.7vw,1.5rem)] font-bold text-cream/85"
        >
          <span className={`h-3 w-3 rounded-full ${light}`} aria-hidden />
          {copy.cta}
        </div>
      ) : (
        <div
          data-stage="listening"
          className={
            'pointer-events-none flex min-h-[4.6rem] items-center justify-center gap-3 rounded-full px-10 py-4 font-display text-[clamp(1.1rem,1.6vw,1.45rem)] font-bold ' +
            (phase === 'hearing'
              ? 'bg-amber/90 text-ink-900'
              : 'bg-ink-950/70 text-cream/85')
          }
        >
          <span className="flex h-6 items-end gap-1" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className={`w-1.5 rounded-full ${phase === 'hearing' ? 'bg-ink-900' : 'bg-mint'}`}
                style={{
                  height: `${[40, 70, 100, 55][i]}%`,
                  animation: phase === 'hearing' ? 'listen 1.1s ease-in-out infinite' : undefined,
                  animationDelay: `${i * 90}ms`,
                  transformOrigin: 'bottom',
                }}
              />
            ))}
          </span>
          {copy.cta}
        </div>
      )}
      <p className="pointer-events-none font-display text-[clamp(0.8rem,1.1vw,1rem)] tracking-wide text-cream/70">
        {copy.sub}
      </p>
    </div>
    </>
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
