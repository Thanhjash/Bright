/**
 * What this appliance has installed, and how far this child has got.
 *
 * One read-only GET, polled slowly. The front door is not allowed to be clever:
 * Core reports the periods an author wrote and the count of sessions it has
 * itself opened and closed, and the arithmetic that turns those into
 * done/next/locked happens here, in the one place that draws them.
 *
 * It deliberately reads the SAME `held` number the teacher receives as
 * PERIODS_HELD. That is what makes a card unable to lie: she works out which
 * period this is from the count, the card was drawn from the count, so the card
 * and the class it opens cannot disagree.
 */
import { useEffect, useState } from 'react'
import { CORE_HTTP } from '../../lib/env'

export interface Period {
  n: number
  title: string
  objectives: string[]
  /** The author's own words for what is in play, ids and prose alike. */
  inPlay: string
  /** Which of those objectives the room has actually witnessed go right. */
  covered: string[]
  /** `asset://…` picture for this period's card, chosen by the unit's author.
   *  Which face belongs to "How are you? Goodbye" is curriculum, not layout. */
  art: string
}

export interface Installed {
  unitId: string
  learnerId: string
  /**
   * Whether `held` and every `covered` above are about anybody at all.
   *
   * The door only learns a learner id once its camera has placed a face, and
   * for every poll before that Core is answering about nobody. It used to
   * answer about the deployment's scaffold learner instead, so a child with
   * seventeen witnessed answers was shown an empty bar with no hint that a
   * different subject had been substituted. Zero and "not known" must not
   * render identically.
   */
  learnerKnown: boolean
  held: number
  periods: Period[]
}

export interface RoomReadiness {
  hermesUp: boolean
  speechUp: boolean
  sessionOpen: boolean
  /**
   * Has she drafted this period yet?
   *
   * The services being up is NOT the same as the room being ready, and the
   * difference is the worst seventy seconds of the demo: on a cold start the
   * first turn is her reading the unit map and writing a plan while the class
   * watches a blank board. A prepared plan (`lesson_plans`, keyed
   * `prepare:<unit>`) is replayed by `start_teacher_session`, so the opening
   * turn becomes a greeting instead of homework. Saying "ready" while that is
   * still to come is a lie the pill used to tell.
   */
  prepared: boolean
}

/** Slow on purpose: nothing here changes between one child and the next. */
const EVERY_MS = 4000

function asPeriod(raw: unknown): Period | null {
  if (!raw || typeof raw !== 'object')
    return null
  const r = raw as Record<string, unknown>
  const n = typeof r.n === 'number' ? r.n : Number.NaN
  if (!Number.isFinite(n))
    return null
  return {
    n,
    title: typeof r.title === 'string' ? r.title : '',
    objectives: Array.isArray(r.objectives) ? r.objectives.filter(o => typeof o === 'string') : [],
    inPlay: typeof r.inPlay === 'string' ? r.inPlay : '',
    covered: Array.isArray(r.covered) ? r.covered.filter(o => typeof o === 'string') : [],
    art: typeof r.art === 'string' ? r.art : '',
  }
}

export function useInstalled(learnerId?: string): {
  installed: Installed | null
  room: RoomReadiness | null
  failed: boolean
} {
  const [installed, setInstalled] = useState<Installed | null>(null)
  const [room, setRoom] = useState<RoomReadiness | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancel = false
    const query = learnerId ? `?learnerId=${encodeURIComponent(learnerId)}` : ''

    const tick = async () => {
      try {
        const [periodsRes, statusRes] = await Promise.all([
          fetch(`${CORE_HTTP}/library/periods${query}`).then(r => r.json()),
          fetch(`${CORE_HTTP}/teacher/status`).then(r => r.json()),
        ])
        if (cancel)
          return
        const body = periodsRes as Record<string, unknown>
        setInstalled({
          unitId: typeof body.unitId === 'string' ? body.unitId : '',
          learnerId: typeof body.learnerId === 'string' ? body.learnerId : '',
          learnerKnown: body.learnerKnown === true,
          held: typeof body.held === 'number' ? body.held : 0,
          periods: (Array.isArray(body.periods) ? body.periods : [])
            .map(asPeriod)
            .filter((p): p is Period => p !== null),
        })
        const status = statusRes as Record<string, unknown>
        const prepare = status.lastPrepare as { ok?: unknown } | null | undefined
        setRoom({
          hermesUp: status.hermesUp === true,
          speechUp: status.speechUp === true,
          sessionOpen: status.sessionOpen === true,
          prepared: Boolean(prepare && prepare.ok !== false),
        })
        setFailed(false)
      }
      catch {
        // A dark front door is honest; a crashed one is not. Keep whatever was
        // last true on screen and say the room is not ready.
        if (!cancel)
          setFailed(true)
      }
    }

    void tick()
    const id = window.setInterval(() => { void tick() }, EVERY_MS)
    return () => {
      cancel = true
      window.clearInterval(id)
    }
  }, [learnerId])

  return { installed, room, failed }
}

export type CardState = 'done' | 'next' | 'locked'

/**
 * Which card the child may press.
 *
 * Exactly one: the period after the last one she has held. A finished period is
 * NOT pressable, and that is not tidiness — she works out which period this is
 * from `held`, so a card offering to re-teach Period 1 would open Period 3 and
 * say so. Re-teaching a period means resetting what the room witnessed, which
 * is an adult's decision and not a button on the child's screen.
 */
export function cardState(period: Period, held: number): CardState {
  if (period.n <= held)
    return 'done'
  if (period.n === held + 1)
    return 'next'
  return 'locked'
}
