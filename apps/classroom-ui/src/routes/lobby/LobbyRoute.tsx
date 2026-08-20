/**
 * `/` — the front door.
 *
 * The room used to have no beginning. `/` was a bare redirect to `/classroom`,
 * and a period started because a ten-second heartbeat noticed that a browser
 * was holding the audio lease. Nothing announced itself and nothing was chosen,
 * so to a child it read as a lesson that had already started without them.
 *
 * This page is deliberately the least clever thing in the app:
 *
 *  · it speaks HTTP only. It must NOT mount a stage-role bus — that socket is
 *    what claims the audio lease, and Core opens a class the moment the lease
 *    exists. A stage socket here would make her greet an empty lobby and then
 *    fight the real classroom window for the microphone.
 *  · it never opens a session. Pressing a card navigates, and the pulse in Core
 *    opens the period exactly as it does today. `_open_on_presence` is
 *    untouched, so if this page is broken the fix is to type `/classroom`.
 *  · it does not decide which period is next. `held` decides, and `held` is the
 *    same number the teacher reasons from.
 *
 * See `docs/decisions/2026-08-20-the-front-door.md`: the picker is outside the
 * teaching loop, which is why it does not contradict "the room runs itself".
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { CORE_HTTP } from '../../lib/env'
import { LOBBY_LABELS as L } from '../../room/labels'
import { unlockAudioNow } from '../../speech/speakingDriver'
import type { Who } from './LobbyCamera'
import { LobbyCamera } from './LobbyCamera'
import type { CardState, Period } from './usePeriods'
import { cardState, useInstalled } from './usePeriods'

const TONE: Record<CardState, string> = {
  done: 'border-mint/40 bg-ink-800',
  next: 'border-amber bg-ink-700 shadow-[0_0_0_4px_rgba(255,182,39,0.18)]',
  locked: 'border-ink-700 bg-ink-900/70',
}

const BADGE: Record<CardState, string> = {
  done: 'bg-mint/20 text-mint',
  next: 'bg-amber text-ink-900',
  locked: 'bg-ink-700 text-muted',
}

function PeriodCard({ period, state, onEnter }: {
  period: Period
  state: CardState
  onEnter: () => void
}) {
  const pressable = state === 'next'
  return (
    <button
      type="button"
      disabled={!pressable}
      onClick={pressable ? onEnter : undefined}
      data-lobby="period"
      data-period={period.n}
      data-state={state}
      className={`flex w-full items-center gap-5 rounded-3xl border-2 p-5 text-left transition ${TONE[state]} ${
        pressable ? 'cursor-pointer hover:brightness-110' : 'cursor-default opacity-70'
      }`}
    >
      <span
        className={`grid h-16 w-16 shrink-0 place-items-center rounded-2xl font-display text-3xl font-extrabold ${
          state === 'next' ? 'bg-amber text-ink-900' : 'bg-ink-900 text-muted'
        }`}
      >
        {state === 'done' ? '✓' : period.n}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block font-display text-2xl font-extrabold text-cream">
          {period.title}
        </span>
        {period.objectives.length > 0 && (
          <span className="mt-2 flex flex-wrap gap-2">
            {period.objectives.map(o => (
              <span key={o} className="rounded-full bg-ink-900/80 px-3 py-1 text-sm text-muted">
                {o}
              </span>
            ))}
          </span>
        )}
      </span>

      <span className={`shrink-0 rounded-full px-4 py-2 font-display text-base font-extrabold ${BADGE[state]}`}>
        {state === 'done' ? L.done : state === 'next' ? L.next : L.locked}
      </span>
    </button>
  )
}

export function LobbyRoute() {
  const navigate = useNavigate()
  // Once the door knows who this is, the progress it shows is THEIR progress.
  // Until then it is the deployment's declared learner, which is the same
  // fallback the room itself uses when perception cannot place anybody.
  const [who, setWho] = useState<Who | null>(null)
  const { installed, room, failed } = useInstalled(who?.learnerId)
  const [entering, setEntering] = useState(false)

  const onKnown = useCallback((found: Who) => { setWho(found) }, [])

  const servicesUp = Boolean(room?.hermesUp && room?.speechUp) && !failed
  const ready = servicesUp && Boolean(room?.prepared)
  const held = installed?.held ?? 0

  /**
   * Ask her to draft the period while nobody is waiting.
   *
   * This is "the agent works in the background" in its safe form.
   * `prepare_period` runs ONE turn with a restricted tool set -- it cannot
   * `say`, cannot touch the board, cannot mark anybody -- and it refuses
   * outright if a class is in progress. Fired at most once per mount, only when
   * the services are up, no class is open, and nothing is drafted yet.
   *
   * A resident background agent would be the wrong answer on this box: the
   * model, Whisper and VieNeu share one CPU budget, and a loop holding the turn
   * lock would delay the child's first word -- the one moment that matters
   * most. Discrete and pre-scheduled beats always-on.
   */
  const asked = useRef(false)
  useEffect(() => {
    if (asked.current || !servicesUp || !room || room.sessionOpen || room.prepared)
      return
    asked.current = true
    void fetch(`${CORE_HTTP}/teacher/prepare`, { method: 'POST' }).catch(() => {
      // Unprepared is slow, never broken. The pill keeps saying so.
      asked.current = false
    })
  }, [servicesUp, room])

  function enter() {
    // THE line that decides whether the video has sound. Browsers only start an
    // AudioContext inside a real gesture, and the deferred unlock the classroom
    // arms waits for the NEXT one -- which, after this click, never comes.
    // Spend the gesture we are standing in.
    unlockAudioNow()
    setEntering(true)
    navigate('/classroom')
  }

  return (
    <main className="min-h-full w-full overflow-y-auto bg-ink-900 px-[6vw] py-[6vh]">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <header className="flex flex-col gap-2">
          <h1 className="font-display text-5xl font-extrabold text-cream">{L.title}</h1>
          <p className="text-xl text-muted">{L.subtitle}</p>
          <p className="text-base text-muted/80">{L.heldCount(held)}</p>
        </header>

        <LobbyCamera onKnown={onKnown} />

        <div
          data-lobby="readiness"
          className="flex items-center gap-3 rounded-2xl bg-ink-800 px-5 py-4"
        >
          <span
            className={`h-3 w-3 rounded-full ${
              entering
                ? 'bg-sky'
                : ready
                  ? 'bg-mint'
                  : failed
                    ? 'bg-coral'
                    : servicesUp
                      ? 'bg-sky'
                      : 'bg-amber'
            } ${!ready && !failed ? 'animate-pulse' : ''}`}
          />
          <span data-lobby="readiness-text" className="text-lg text-cream">
            {entering
              ? L.entering
              : failed
                ? L.down
                : ready
                  ? L.ready
                  : servicesUp
                    ? L.drafting
                    : L.warming}
          </span>
        </div>

        <div className="flex flex-col gap-4">
          {(installed?.periods ?? []).map(period => (
            <PeriodCard
              key={period.n}
              period={period}
              state={cardState(period, held)}
              onEnter={enter}
            />
          ))}
        </div>
      </div>
    </main>
  )
}
