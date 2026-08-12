/**
 * The student's turn to speak, as the facilitator sees it.
 *
 * One big button held down while a child talks, and a live account of what the
 * machine is doing with it. Transcription takes ~3.4 s and nothing can make it
 * faster, so this panel spends that time SAYING SO: a level meter while the mic
 * is open, a filling bar and a running count while Whisper works, the transcript
 * and its measured latency when it lands. The one thing it never does is go
 * quiet and leave a teacher wondering whether to press it again.
 *
 * Failures are the loud path, not the quiet one. A blocked microphone, a speech
 * service that is down, and a recording nobody spoke into each produce a
 * different sentence, in red, that says what to do next.
 */
import { useEffect, useRef } from 'react'
import { useBus } from '../../bus'
import { EXPECTED_AGENT_MS, EXPECTED_STT_MS, useVoiceInput } from '../../speech/useVoiceInput'
import type { VoicePhase } from '../../speech/useVoiceInput'
import { selectListening, useClassroom } from '../../store/classroom'

const PHASE_COPY: Record<VoicePhase, { label: string; hint: string; tone: string }> = {
  idle: {
    label: 'Hold to listen',
    hint: 'Hold while the child speaks — or hold the space bar',
    tone: 'bg-ink-700 ring-ink-500 text-cream',
  },
  opening: {
    label: 'Opening the mic…',
    hint: 'Waiting for the microphone',
    tone: 'bg-ink-700 ring-amber/60 text-cream',
  },
  listening: {
    label: 'Listening',
    hint: 'Let go when the child has finished',
    tone: 'bg-mint/20 ring-mint text-mint',
  },
  thinking: {
    label: 'Thinking…',
    hint: 'Whisper needs about 3.4 seconds, whatever the length',
    tone: 'bg-amber/18 ring-amber/70 text-amber',
  },
  waiting: {
    label: 'With the teacher',
    hint: 'The answer is sent — waiting for the lesson to move',
    tone: 'bg-violet/18 ring-violet/70 text-violet',
  },
  error: {
    label: 'Try again',
    hint: 'Hold to listen',
    tone: 'bg-coral/18 ring-coral/70 text-coral',
  },
}

export function VoicePanel() {
  const bus = useBus()
  const voice = useVoiceInput(bus)
  const sceneListening = useClassroom(selectListening)
  const copy = PHASE_COPY[voice.phase]
  // In automatic mode the button is a status light, not an instruction: telling
  // a teacher to "hold" a control that is disabled is worse than saying nothing.
  const idleInAuto = voice.mode === 'auto' && voice.phase === 'idle'

  useSpaceBarHold(voice.press, voice.release, voice.mode === 'ptt')

  return (
    <section className="rounded-3xl bg-ink-800 p-5 ring-2 ring-ink-600">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-bold tracking-[0.18em] text-muted uppercase">Student voice</p>
        <ModeSwitch mode={voice.mode} onChange={voice.setMode} />
      </div>

      <button
        type="button"
        // Pointer events, not mouse/touch: one code path for a trackpad, a
        // finger and a pen. `pointerup` is also caught on `window` below,
        // because a pointer released outside the button never fires it here —
        // and a missed release means a microphone that never closes.
        onPointerDown={(e) => {
          e.preventDefault()
          if (voice.mode === 'ptt') voice.press()
        }}
        onPointerUp={() => {
          if (voice.mode === 'ptt') voice.release()
        }}
        onPointerCancel={() => {
          if (voice.mode === 'ptt') voice.release()
        }}
        onPointerLeave={() => {
          if (voice.mode === 'ptt') voice.release()
        }}
        onLostPointerCapture={() => {
          if (voice.mode === 'ptt') voice.release()
        }}
        disabled={voice.mode === 'auto'}
        data-voice-phase={voice.phase}
        data-testid="push-to-talk"
        className={`flex w-full touch-none items-center gap-4 rounded-2xl p-5 text-left ring-2 transition-[transform,background-color] duration-150 select-none active:scale-[0.985] disabled:opacity-55 ${copy.tone}`}
      >
        <MicGlyph phase={voice.phase} getLevel={voice.getLevel} />
        <span className="min-w-0 flex-1">
          <span className="block font-display text-2xl leading-tight font-extrabold">
            {idleInAuto ? 'Waiting for the lesson' : copy.label}
          </span>
          <span className="block truncate text-sm text-muted">
            {idleInAuto ? 'The mic opens when the lesson asks a child to speak' : copy.hint}
          </span>
        </span>
        {voice.phase === 'listening' ? (
          <span className="font-mono text-xl font-bold tabular-nums">
            {(voice.elapsedMs / 1000).toFixed(1)}s
          </span>
        ) : null}
      </button>

      {/* The wait, made visible — BOTH halves of it. Whisper is ~3.4 s and the
          agent can add another ~6 s on top, so a single unlabelled spinner
          would sit there for ten seconds looking broken. Each bar is capped
          just short of full: it must never claim to be finished before the
          answer actually arrives. */}
      {voice.phase === 'thinking' ? (
        <Progress
          tone="bg-amber"
          value={voice.thinkingMs / EXPECTED_STT_MS}
          caption={`transcribing · ${(voice.thinkingMs / 1000).toFixed(1)}s of ~3.4s`}
        />
      ) : null}
      {voice.phase === 'waiting' ? (
        <Progress
          tone="bg-violet"
          value={voice.waitingMs / EXPECTED_AGENT_MS}
          caption={`teacher deciding · ${(voice.waitingMs / 1000).toFixed(1)}s`}
        />
      ) : null}

      {voice.mode === 'auto' ? (
        <p className="mt-3 rounded-2xl bg-ink-900 p-3.5 text-sm leading-snug text-muted ring-2 ring-ink-700">
          Automatic — the microphone follows the lesson&apos;s{' '}
          <span className="font-bold text-cream">listening</span> flag, currently{' '}
          <span className={sceneListening ? 'font-bold text-mint' : 'font-bold text-muted'}>
            {sceneListening ? 'on' : 'off'}
          </span>
          . It cannot tell one child from thirty; hold-to-talk is the reliable one.
        </p>
      ) : null}

      {voice.error ? (
        <p
          role="alert"
          className="mt-3 rounded-2xl bg-coral/15 p-3.5 text-base leading-snug font-semibold text-coral ring-2 ring-coral/50"
        >
          {voice.error.message}
        </p>
      ) : null}

      {voice.last ? (
        <div className="mt-3 rounded-2xl bg-ink-900 p-4 ring-2 ring-sky/40">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-xs font-bold tracking-[0.16em] text-sky uppercase">Heard</span>
            <span className="font-mono text-xs text-muted">
              {(voice.last.latencyMs / 1000).toFixed(2)}s end to end · {voice.last.serviceMs}ms stt ·
              conf {voice.last.confidence.toFixed(2)}
            </span>
          </div>
          <p data-testid="voice-transcript" className="mt-1 text-xl leading-snug text-cream">
            {voice.last.text}
          </p>
        </div>
      ) : null}
    </section>
  )
}

/** A capped progress bar with a caption. Never reaches 100%. */
function Progress({ tone, value, caption }: { tone: string; value: number; caption: string }) {
  return (
    <div className="mt-3">
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-ink-700">
        <div
          className={`h-full rounded-full transition-[width] duration-100 ease-linear ${tone}`}
          style={{ width: `${Math.min(96, value * 100)}%` }}
        />
      </div>
      <p className="mt-1.5 font-mono text-xs text-muted">{caption}</p>
    </div>
  )
}

function ModeSwitch({
  mode,
  onChange,
}: {
  mode: 'ptt' | 'auto'
  onChange: (mode: 'ptt' | 'auto') => void
}) {
  return (
    <div className="flex rounded-full bg-ink-900 p-1 ring-2 ring-ink-700">
      {(['ptt', 'auto'] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={`rounded-full px-3.5 py-1.5 text-xs font-extrabold tracking-wider uppercase transition-colors ${
            mode === m ? 'bg-ink-600 text-cream' : 'text-muted hover:text-cream'
          }`}
        >
          {m === 'ptt' ? 'Hold to talk' : 'Automatic'}
        </button>
      ))}
    </div>
  )
}

/**
 * The microphone icon doubles as the level meter. Polled from a frame loop
 * rather than pushed through React: the level changes sixty times a second and
 * must not re-render the panel.
 */
function MicGlyph({ phase, getLevel }: { phase: VoicePhase; getLevel: () => number }) {
  const ring = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (phase !== 'listening') return
    let raf = 0
    const tick = () => {
      const el = ring.current
      if (el) {
        const level = getLevel()
        el.style.transform = `scale(${1 + level * 0.55})`
        el.style.opacity = String(0.18 + level * 0.62)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [phase, getLevel])

  return (
    <span className="relative flex h-12 w-12 shrink-0 items-center justify-center">
      <span
        ref={ring}
        className="absolute inset-0 rounded-full bg-current opacity-15"
        style={{ transform: 'scale(1)' }}
        aria-hidden
      />
      <svg viewBox="0 0 24 24" className="relative h-7 w-7" aria-hidden>
        <path
          d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {phase === 'thinking' ? (
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-current" />
      ) : null}
    </span>
  )
}

/**
 * Space bar as the second push-to-talk affordance.
 *
 * A teacher standing beside a child is not looking at the trackpad. `repeat` is
 * ignored — key auto-repeat would otherwise fire `press` fifty times a second —
 * and the release is bound to `window` so it survives focus moving mid-hold.
 */
function useSpaceBarHold(press: () => void, release: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    const isSpace = (e: KeyboardEvent) => e.code === 'Space' && !isTypingTarget(e.target)

    const down = (e: KeyboardEvent) => {
      if (!isSpace(e) || e.repeat) return
      e.preventDefault()
      press()
    }
    const up = (e: KeyboardEvent) => {
      if (!isSpace(e)) return
      release()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [enabled, press, release])

  // A pointer released anywhere but on the button — or the window losing focus
  // mid-hold — must still close the microphone.
  useEffect(() => {
    if (!enabled) return
    const stop = () => release()
    window.addEventListener('pointerup', stop)
    window.addEventListener('blur', stop)
    return () => {
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('blur', stop)
    }
  }, [enabled, release])
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el?.tagName) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable
}
