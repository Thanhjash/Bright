/** Child-operated answer-station status and Ready control. */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useBus } from '../../bus'
import {
  EXPECTED_FEEDBACK_MS,
  EXPECTED_STT_MS,
  useVoiceInput,
} from '../../speech/useVoiceInput'
import type { VoicePhase } from '../../speech/useVoiceInput'
import { isMicrophoneSuppressed, subscribeOutputActivity } from '../../speech/outputActivity'

const PHASE_COPY: Record<VoicePhase, { label: string; hint: string; tone: string }> = {
  idle: {
    label: 'Answer station standing by',
    hint: 'Bright will call a learner when it is their turn.',
    tone: 'bg-ink-700 ring-ink-500 text-cream',
  },
  assigned: {
    label: 'Press Ready',
    hint: 'The learner presses once after reaching the answer station.',
    tone: 'bg-mint/20 ring-mint text-mint',
  },
  opening: {
    label: 'Opening microphone…',
    hint: 'Stay close and wait for the listening signal.',
    tone: 'bg-amber/18 ring-amber/70 text-amber',
  },
  listening: {
    label: 'Speak now',
    hint: 'Bright stops automatically after the learner becomes quiet.',
    tone: 'bg-mint/20 ring-mint text-mint',
  },
  thinking: {
    label: 'Checking the answer…',
    hint: 'The microphone is closed.',
    tone: 'bg-amber/18 ring-amber/70 text-amber',
  },
  waiting: {
    label: 'Answer received',
    hint: 'Bright is choosing the next teaching move.',
    tone: 'bg-violet/18 ring-violet/70 text-violet',
  },
  error: {
    label: 'Answer station needs attention',
    hint: 'Bright did not use uncertain input as learner evidence.',
    tone: 'bg-coral/18 ring-coral/70 text-coral',
  },
}

export function VoicePanel() {
  const bus = useBus()
  const voice = useVoiceInput(bus)
  const [checking, setChecking] = useState(false)
  const [check, setCheck] = useState<'idle' | 'pass' | 'fail'>('idle')
  const copy = PHASE_COPY[voice.phase]
  const outputQuiet = useSyncExternalStore(
    subscribeOutputActivity,
    () => !isMicrophoneSuppressed(),
    () => false,
  )
  const canReady = voice.phase === 'assigned' && outputQuiet
  const readyCopy = voice.phase === 'assigned' && !outputQuiet
    ? {
        label: 'Wait for the listening signal',
        hint: 'Bright is clearing the teacher voice from the answer microphone.',
        tone: 'bg-amber/18 ring-amber/70 text-amber',
      }
    : copy

  return (
    <section className="rounded-3xl bg-ink-800 p-5 ring-2 ring-ink-600" aria-labelledby="answer-station-title">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p id="answer-station-title" className="text-xs font-bold tracking-[0.18em] text-muted uppercase">
            Answer station
          </p>
          <p className="mt-1 text-sm text-muted">Assigned turns only · microphone closes after each attempt</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-extrabold ${
          voice.assignment ? 'bg-mint/18 text-mint' : 'bg-ink-700 text-muted'
        }`}>
          {voice.assignment ? 'Turn assigned' : 'Standing by'}
        </span>
      </div>

      <button
        type="button"
        onClick={voice.ready}
        disabled={!canReady}
        data-voice-phase={voice.phase}
        data-output-quiet={outputQuiet ? 'true' : 'false'}
        data-testid="answer-station-ready"
        className={`flex min-h-[7rem] w-full items-center gap-4 rounded-2xl p-5 text-left ring-2 transition active:scale-[0.985] disabled:cursor-default disabled:opacity-75 ${readyCopy.tone}`}
      >
        <MicGlyph phase={voice.phase} getLevel={voice.getLevel} />
        <span className="min-w-0 flex-1">
          <span className="block font-display text-2xl leading-tight font-extrabold">{readyCopy.label}</span>
          <span className="mt-1 block text-sm leading-snug text-muted">{readyCopy.hint}</span>
        </span>
        {voice.phase === 'listening' ? (
          <span className="font-mono text-xl font-bold tabular-nums">{(voice.elapsedMs / 1000).toFixed(1)}s</span>
        ) : null}
      </button>

      {voice.phase === 'thinking' ? (
        <Progress tone="bg-amber" value={voice.thinkingMs / EXPECTED_STT_MS} caption="speech recognition" />
      ) : null}
      {voice.phase === 'waiting' ? (
        <Progress tone="bg-violet" value={voice.waitingMs / EXPECTED_FEEDBACK_MS} caption="teacher response" />
      ) : null}

      {voice.error ? (
        <p role="alert" className="mt-3 rounded-2xl bg-coral/15 p-3.5 text-base font-semibold text-coral ring-2 ring-coral/50">
          {voice.error.message}
        </p>
      ) : null}

      {voice.last ? (
        <p className="mt-3 rounded-2xl bg-ink-900 p-3.5 text-sm text-muted ring-2 ring-ink-700" aria-live="polite">
          Attempt complete: <span className="font-bold text-cream">{outcomeLabel(voice.last.outcome)}</span>
          {' · '}{(voice.last.latencyMs / 1000).toFixed(1)}s
        </p>
      ) : null}

      {!voice.assignment && voice.phase === 'idle' ? (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl bg-ink-900 p-3 ring-2 ring-ink-700">
          <div>
            <p className="font-bold text-cream">Microphone preflight</p>
            <p className="text-xs text-muted">Run once while the answer station is quiet.</p>
          </div>
          <button
            type="button"
            disabled={checking}
            onClick={() => {
              setChecking(true)
              void voice.checkStation().then((result) => setCheck(result.ok ? 'pass' : 'fail')).finally(() => setChecking(false))
            }}
            className={`min-h-12 rounded-xl px-4 font-bold ring-2 ${check === 'pass' ? 'bg-mint/18 text-mint ring-mint/50' : check === 'fail' ? 'bg-coral/18 text-coral ring-coral/50' : 'bg-ink-700 text-cream ring-ink-500'}`}
          >
            {checking ? 'Checking…' : check === 'pass' ? 'Microphone ready' : check === 'fail' ? 'Check again' : 'Check microphone'}
          </button>
        </div>
      ) : null}
    </section>
  )
}

function outcomeLabel(outcome: NonNullable<ReturnType<typeof useVoiceInput>['last']>['outcome']): string {
  const labels = {
    speech: 'speech received',
    no_speech: 'no speech',
    noise_only: 'noise only',
    device_lost: 'microphone lost',
    asr_timeout: 'recognition timed out',
    asr_unavailable: 'recognition unavailable',
  } as const
  return labels[outcome]
}

function Progress({ tone, value, caption }: { tone: string; value: number; caption: string }) {
  return (
    <div className="mt-3" aria-live="polite">
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-ink-700">
        <div className={`h-full rounded-full transition-[width] duration-100 ${tone}`} style={{ width: `${Math.min(96, value * 100)}%` }} />
      </div>
      <p className="mt-1.5 font-mono text-xs text-muted">{caption}</p>
    </div>
  )
}

function MicGlyph({ phase, getLevel }: { phase: VoicePhase; getLevel: () => number }) {
  const ring = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (phase !== 'listening') return
    let raf = 0
    const tick = () => {
      const level = getLevel()
      if (ring.current) {
        ring.current.style.transform = `scale(${1 + level * 0.55})`
        ring.current.style.opacity = String(0.18 + level * 0.62)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [getLevel, phase])

  return (
    <span className="relative flex h-12 w-12 shrink-0 items-center justify-center">
      <span ref={ring} className="absolute inset-0 rounded-full bg-current opacity-15" aria-hidden />
      <svg viewBox="0 0 24 24" className="relative h-7 w-7" aria-hidden>
        <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" />
      </svg>
    </span>
  )
}
