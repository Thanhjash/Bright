/**
 * The adult's console. Two things, and nothing that pretends.
 *
 * Everything here used to send a WebSocket frame -- `lesson.start`,
 * `control.command` -- that is not in Core's `CLIENT_EVENTS` allowlist, so
 * every button was rejected before any handler ran, and there was no handler to
 * reject it to: the receiving side was never written. Start, Repeat, Back and
 * Skip are gone with it. They were step navigation for the lesson graph this
 * project deleted, and there is no step cursor to move. "Start" is forbidden
 * outright: the room opens itself when someone appears, and a button to begin
 * is an adult decision sitting on the teaching path, which NS-1 forbids.
 *
 * What is left is what NORTH-STAR §1 has always said the adult is for -- they
 * are the safety authority in the room -- plus the one thing the teacher can
 * now do that only a person can answer.
 */
import { useCallback, useEffect, useState } from 'react'
import { CORE_HTTP } from '../../lib/env'

type Escalation = { reason: string; detail?: string; at?: string }
type Status = { escalation?: Escalation | null; pausedByAdult?: unknown }

const WHY: Record<string, string> = {
  danger: 'Nguy hiểm trong lớp',
  distress: 'Một em đang buồn hoặc hoảng',
  disclosure: 'Một em vừa kể điều đáng lo',
  equipment: 'Thiết bị hỏng',
  cannot_reach_the_class: 'Cô không tiếp cận được lớp',
}

export function CommandBar() {
  // Straight from /teacher/status rather than the WebSocket store: an
  // escalation is the one thing on this page that must not depend on a live
  // socket. If the bus is down, the adult still needs to see that the teacher
  // has stopped and is asking for them.
  const [status, setStatus] = useState<Status>({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const res = await fetch(`${CORE_HTTP}/teacher/status`)
        if (alive && res.ok) setStatus((await res.json()) as Status)
      } catch {
        /* the panel beside this one already says the room is unreachable */
      }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  const escalation = status.escalation
  const pausedByAdult = status.pausedByAdult

  const send = useCallback(async (path: string, label: string) => {
    setBusy(label)
    setError('')
    try {
      const res = await fetch(`${CORE_HTTP}/teacher/${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: '{}',
      })
      if (!res.ok) throw new Error(`${res.status}`)
    } catch (cause) {
      // A console that fails silently is how an adult learns to distrust it.
      setError(`Không gửi được lệnh (${String(cause).slice(0, 60)})`)
    } finally {
      setBusy('')
      // Reflect the new state at once rather than waiting for the next poll --
      // an adult who pressed a button needs to see that it landed.
      try {
        const res = await fetch(`${CORE_HTTP}/teacher/status`)
        if (res.ok) setStatus((await res.json()) as Status)
      } catch {
        /* the poll will catch up */
      }
    }
  }, [])

  return (
    <section
      className="rounded-3xl bg-ink-800 p-4 ring-2 ring-ink-600"
      aria-labelledby="safety-controls-title"
    >
      <p
        id="safety-controls-title"
        className="mb-3 text-xs font-bold tracking-[0.18em] text-muted uppercase"
      >
        Lớp học — an toàn
      </p>

      {/* The teacher asking for a person. Loud, first, in the school's own
          language, and it does not go away until someone answers it. */}
      {escalation ? (
        <div
          role="alert"
          data-testid="escalation"
          className="mb-3 rounded-2xl bg-coral/20 p-4 ring-2 ring-coral"
        >
          <p className="font-display text-xl font-extrabold text-coral">
            Cô đang gọi thầy cô
          </p>
          <p className="mt-1 font-bold text-cream">
            {WHY[escalation.reason] ?? escalation.reason}
          </p>
          {escalation.detail ? (
            <p className="mt-1 text-sm text-cream/85">{escalation.detail}</p>
          ) : null}
          <p className="mt-2 text-sm text-muted">
            Cô đã dừng dạy. Bảng vẫn giữ nguyên cho các em. Bấm “Tiếp tục” khi
            đã xong.
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          data-testid="pause"
          disabled={Boolean(pausedByAdult) || busy !== ''}
          onClick={() => void send('pause', 'pause')}
          className="min-h-20 rounded-2xl bg-amber/18 px-4 text-left text-amber ring-2 ring-amber/55 transition hover:bg-amber/25 disabled:opacity-45"
        >
          <span className="block font-display text-lg font-extrabold">Dừng lớp</span>
          <span className="block text-sm text-muted">Cô im lặng cho tới khi thầy cô cho tiếp</span>
        </button>
        <button
          type="button"
          data-testid="resume"
          disabled={!pausedByAdult && !escalation}
          onClick={() => void send('resume', 'resume')}
          className="min-h-20 rounded-2xl bg-mint/18 px-4 text-left text-mint ring-2 ring-mint/55 transition hover:bg-mint/25 disabled:opacity-45"
        >
          <span className="block font-display text-lg font-extrabold">Tiếp tục</span>
          <span className="block text-sm text-muted">Trả lớp lại cho cô</span>
        </button>
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-xl bg-coral/15 p-3 text-sm font-bold text-coral ring-2 ring-coral/45"
        >
          {error}
        </p>
      ) : null}
    </section>
  )
}
