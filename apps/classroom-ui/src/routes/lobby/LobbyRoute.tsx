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
 * The look is a lit porch onto the room that already exists: the classroom art
 * is a photographed blackboard on a warm plaster wall, so the door is warm
 * lamplight over the same deep ink, and the child's progress is drawn as a
 * PATH rather than a list of identical rectangles. The pictures on the cards
 * are the unit's own textbook art, named by the unit's author — this file
 * never chooses which face belongs to which lesson.
 *
 * See `docs/decisions/2026-08-21-the-front-door.md`: the picker is outside the
 * teaching loop, which is why it does not contradict "the room runs itself".
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { resolveAsset } from '../../lib/assets'
import { CORE_HTTP } from '../../lib/env'
import { LOBBY_LABELS as L } from '../../room/labels'
import { unlockAudioNow } from '../../speech/speakingDriver'
import type { Who } from './LobbyCamera'
import { LobbyCamera } from './LobbyCamera'
import type { CardState, Period } from './usePeriods'
import { cardState, useInstalled } from './usePeriods'

/** Card ground, node fill, and the badge — one tone per state, so the state is
 *  legible from the back of a room before any word is read. */
const TONE: Record<CardState, { card: string; node: string; badge: string }> = {
  done: {
    card: 'border-mint/35 bg-mint/[0.07]',
    node: 'bg-mint/20 text-mint ring-2 ring-mint/50',
    badge: 'bg-mint/15 text-mint',
  },
  next: {
    card: 'border-amber bg-amber/[0.10] shadow-[0_0_0_0.5vh_rgba(255,182,39,0.13),0_1.4vh_3vh_rgba(0,0,0,0.45)]',
    node: 'bg-amber text-ink-900 ring-4 ring-amber/30',
    badge: 'bg-amber text-ink-900',
  },
  locked: {
    card: 'border-ink-700/70 bg-ink-900/50',
    node: 'bg-ink-800 text-muted/60 ring-2 ring-ink-700',
    badge: 'bg-ink-800 text-muted/70',
  },
}

function PeriodCard({ period, state, index, onEnter }: {
  period: Period
  state: CardState
  index: number
  onEnter: () => void
}) {
  const pressable = state === 'next'
  const tone = TONE[state]
  const total = period.objectives.length
  const done = period.covered.length
  const src = resolveAsset(period.art as never)

  return (
    <button
      type="button"
      disabled={!pressable}
      onClick={pressable ? onEnter : undefined}
      data-lobby="period"
      data-period={period.n}
      data-state={state}
      style={{ animationDelay: `${120 + index * 90}ms` }}
      className={`animate-rise relative flex w-full items-center gap-[1.4vw] rounded-[1.6rem] border-2 p-[1.5vh_1.4vw] text-left transition duration-200 ${tone.card} ${
        pressable ? 'cursor-pointer hover:-translate-y-[0.4vh] hover:brightness-110' : 'cursor-default'
      } ${state === 'locked' ? 'opacity-55' : ''}`}
    >
      {/* The node on the path. The line behind it is drawn by the parent, so
          this sits over the join and reads as a stop along a route. */}
      <span
        className={`grid h-[clamp(3.2rem,4.4vw,4.8rem)] w-[clamp(3.2rem,4.4vw,4.8rem)] shrink-0 place-items-center rounded-full font-display text-[clamp(1.5rem,2.3vw,2.5rem)] font-extrabold ${tone.node} ${
          pressable ? 'animate-[pulse_2.6s_ease-in-out_infinite]' : ''
        }`}
      >
        {state === 'done' ? '✓' : period.n}
      </span>

      {/* The unit's own textbook art. A missing file must look like a missing
          picture, never like a broken page, so it simply is not rendered. */}
      {src ? (
        <img
          src={src}
          alt=""
          className={`h-[clamp(3.4rem,5vw,5.4rem)] w-[clamp(3.4rem,5vw,5.4rem)] shrink-0 rounded-2xl object-cover ring-1 ring-cream/10 ${
            state === 'locked' ? 'grayscale' : ''
          }`}
        />
      ) : null}

      <span className="flex min-w-0 flex-1 flex-col gap-[0.7vh]">
        <span className="font-display text-[clamp(1.3rem,2.2vw,2.4rem)] leading-tight font-extrabold text-cream">
          {period.title}
        </span>

        {/* Honest progress. `covered` counts only objectives the room witnessed
            go RIGHT — a bar that fills on "not quite" lies to a child about
            what they can do. */}
        {total > 0 ? (
          <span className="flex items-center gap-[0.8vw]">
            <span className="h-[0.9vh] min-h-[6px] flex-1 overflow-hidden rounded-full bg-ink-950/70">
              <span
                className={`block h-full rounded-full transition-[width] duration-700 ${
                  state === 'done' ? 'bg-mint' : 'bg-amber'
                }`}
                style={{ width: `${Math.round((done / total) * 100)}%` }}
              />
            </span>
            <span className="shrink-0 text-[clamp(0.75rem,1vw,1.05rem)] text-muted">
              {L.objectives(done, total)}
            </span>
          </span>
        ) : null}
      </span>

      <span className={`shrink-0 rounded-full px-[1.3vw] py-[1vh] font-display text-[clamp(0.85rem,1.25vw,1.4rem)] font-extrabold ${tone.badge}`}>
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
  const periods = installed?.periods ?? []

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
    <main className="relative flex h-full min-h-screen w-full items-center overflow-hidden bg-ink-950">
      {/* Lamplight, not a flat panel. The room this opens onto is a warm
          plaster wall lit from a window; the door should feel like the same
          building. Two washes and a fine grain, all painted — no image to
          load, nothing to go missing on an appliance. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(70vw 55vh at 12% -8%, rgba(255,182,39,0.16), transparent 62%),'
            + 'radial-gradient(55vw 50vh at 96% 108%, rgba(86,204,242,0.10), transparent 60%)',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.05] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/></filter><rect width='140' height='140' filter='url(%23n)'/></svg>\")",
        }}
      />

      <div className="relative mx-auto flex w-full max-w-[110rem] items-center gap-[4vw] px-[5vw] py-[4vh]">
        {/* Left: who you are and whether the room is ready. */}
        <section className="flex w-[38%] shrink-0 flex-col gap-[2.2vh]">
          <header className="flex flex-col gap-[0.6vh]">
            <h1 className="font-display text-[clamp(1.9rem,3.2vw,3.6rem)] leading-[1.05] font-extrabold text-balance text-cream">
              {L.title}
            </h1>
            <p className="text-[clamp(1rem,1.5vw,1.7rem)] text-muted">{L.subtitle}</p>
            <p className="text-[clamp(0.8rem,1.1vw,1.2rem)] text-muted/60">{L.heldCount(held)}</p>
          </header>

          <LobbyCamera onKnown={onKnown} />

          <div
            data-lobby="readiness"
            className="flex items-center gap-[0.7vw] rounded-2xl bg-ink-900/70 px-[1.2vw] py-[1.2vh] ring-1 ring-cream/10"
          >
            <span
              className={`h-[0.9vh] w-[0.9vh] min-h-[8px] min-w-[8px] shrink-0 rounded-full ${
                entering ? 'bg-sky' : ready ? 'bg-mint' : failed ? 'bg-coral' : servicesUp ? 'bg-sky' : 'bg-amber'
              } ${!ready && !failed ? 'animate-pulse' : ''}`}
            />
            <span data-lobby="readiness-text" className="text-[clamp(0.9rem,1.3vw,1.5rem)] text-cream/90">
              {entering ? L.entering : failed ? L.down : ready ? L.ready : servicesUp ? L.drafting : L.warming}
            </span>
          </div>

          
        </section>

        {/* Right: the path. */}
        <section className="relative flex min-w-0 flex-1 flex-col justify-center gap-[1.6vh]">
          {/* The route itself, behind the nodes. It draws itself once on load —
              one orchestrated moment, not a page of fidgeting micro-motion. */}
          {periods.length > 1 ? (
            <span
              aria-hidden
              className="pointer-events-none absolute top-[calc(1.5vh+clamp(1.6rem,2.2vw,2.4rem))] bottom-[calc(1.5vh+clamp(1.6rem,2.2vw,2.4rem))] left-[calc(1.4vw+clamp(1.6rem,2.2vw,2.4rem))] w-[3px] -translate-x-1/2 overflow-hidden rounded-full bg-cream/10"
            >
              <span className="animate-[drawpath_900ms_ease-out_both] block h-full w-full origin-top bg-gradient-to-b from-mint/60 via-amber/50 to-transparent" />
            </span>
          ) : null}

          {periods.map((period, i) => (
            <PeriodCard
              key={period.n}
              period={period}
              index={i}
              state={cardState(period, held)}
              onEnter={enter}
            />
          ))}
        </section>
      </div>
    </main>
  )
}
