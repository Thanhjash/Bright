/**
 * The camera at the door: who is this, and if nobody knows, may we learn?
 *
 * Enrolment happens HERE and nowhere else — before the class, on the door, and
 * never on the projector or during a lesson
 * (`docs/decisions/2026-08-18-identity-is-perception.md`, rule 2).
 *
 * Two properties this component exists to hold:
 *
 *  · **It never enrols by itself.** The camera matches. Adding a face is a
 *    deliberate act: someone types a name and confirms that consent was given.
 *    A face seen twice and not recognised produces an OFFER, never a record.
 *  · **It asks Core, not the vision service.** Core owns the learner id and
 *    hands the same one to vision, so `students` and `subjects` cannot drift
 *    into two different children with the same face. It also means the browser
 *    never learns that :8002 exists.
 *
 * Recognising nobody is not a failure and is never drawn as one. A child whose
 * face has never been enrolled must still be able to press a card and be
 * taught; the room simply uses the deployment's declared learner, and writes no
 * other child's memory.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { CORE_HTTP } from '../../lib/env'
import { LOBBY_LABELS as L } from '../../room/labels'

export interface Who {
  learnerId: string
  displayName: string
}

/** Slower than the room's camera: nobody is being taught yet. */
const EVERY_MS = 2500
/** Offer enrolment only after the camera has genuinely failed to place them. */
const STRANGER_TRIES = 2
/** Three frames 450ms apart — one photo is a pose, not a face. */
const FRAMES = 3
const FRAME_GAP_MS = 450
/** Wide enough for SFace, small enough to post repeatedly. */
const WIDTH = 480

type Phase = 'starting' | 'looking' | 'known' | 'stranger' | 'enrolling' | 'no-camera'

function grab(video: HTMLVideoElement): string | null {
  const w = video.videoWidth
  const h = video.videoHeight
  if (!w || !h)
    return null
  const canvas = document.createElement('canvas')
  canvas.width = WIDTH
  canvas.height = Math.round((h / w) * WIDTH)
  const ctx = canvas.getContext('2d')
  if (!ctx)
    return null
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  // Base64 body only; the data: prefix is not part of the contract.
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1] ?? null
}

export function LobbyCamera({ onKnown }: { onKnown: (who: Who) => void }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [phase, setPhase] = useState<Phase>('starting')
  const [who, setWho] = useState<Who | null>(null)
  const [name, setName] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const misses = useRef(0)
  const settled = useRef(false)

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancel = false
    const start = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640 } })
        if (cancel) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => {})
        }
        setPhase('looking')
      }
      catch {
        // No camera is a normal classroom, not a fault. The door still works.
        setPhase('no-camera')
      }
    }
    void start()
    return () => {
      cancel = true
      stream?.getTracks().forEach(t => t.stop())
    }
  }, [])

  useEffect(() => {
    if (phase !== 'looking')
      return
    let cancel = false
    /** One attempt that did not place a face -- whatever the reason. */
    const missed = () => {
      if (cancel || settled.current)
        return
      misses.current += 1
      if (misses.current >= STRANGER_TRIES)
        setPhase('stranger')
    }
    const tick = async () => {
      const video = videoRef.current
      if (!video || settled.current)
        return
      const frame = grab(video)
      if (!frame)
        return
      try {
        const res = await fetch(`${CORE_HTTP}/teacher/identify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_base64: frame }),
        })
        if (cancel)
          return
        if (!res.ok) {
          // A REFUSAL IS STILL AN ANSWER FOR THIS COUNTER.
          //
          // `misses` used to move only on a 2xx that said "not recognised", so
          // with vision or Core down the door stayed on `looking` for ever and
          // the "I'm new" offer -- the ONLY way into the room for a face the
          // appliance has never seen -- never appeared. A child would stand in
          // front of a camera that was looking at nothing, with no way in.
          //
          // The offer is safe to show either way: enrolment is a deliberate,
          // consented act, and if perception really is down the attempt fails
          // loudly with a message an adult can act on, which is strictly better
          // than a door that waits silently for ever.
          missed()
          return
        }
        const body = await res.json() as { recognised?: boolean, studentId?: string, displayName?: string }
        if (body.recognised && body.studentId) {
          settled.current = true
          const found = { learnerId: body.studentId, displayName: body.displayName || body.studentId }
          setWho(found)
          setPhase('known')
          onKnown(found)
          return
        }
        missed()
      }
      catch {
        // Perception is optional and must never surface at the door as an
        // error -- but "we could not ask" still has to move the counter, or
        // the door never offers the child a way in. Same reasoning as the
        // !res.ok branch above.
        missed()
      }
    }
    void tick()
    const id = window.setInterval(() => { void tick() }, EVERY_MS)
    return () => {
      cancel = true
      window.clearInterval(id)
    }
  }, [phase, onKnown])

  const enrol = useCallback(async () => {
    const video = videoRef.current
    if (!video || !name.trim() || !consent)
      return
    setBusy(true)
    setRefusal(null)
    try {
      const frames: string[] = []
      for (let i = 0; i < FRAMES; i++) {
        const frame = grab(video)
        if (frame)
          frames.push(frame)
        if (i < FRAMES - 1)
          await new Promise(r => setTimeout(r, FRAME_GAP_MS))
      }
      const res = await fetch(`${CORE_HTTP}/teacher/enroll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frames,
          displayName: name.trim(),
          consentConfirmed: true,
        }),
      })
      const body = await res.json() as { learnerId?: string, displayName?: string, detail?: string }
      if (!res.ok || !body.learnerId) {
        // Vision's own words: "must contain exactly one clearly detected face"
        // is something a person standing at the door can act on.
        setRefusal(body.detail || L.stranger)
        return
      }
      // Enrolling tells vision who this face IS. It does not tell Core who is
      // standing at the door -- that is `identified_learner`, and it is what
      // `_open_on_presence` reads when it opens the session. Without this one
      // extra frame the child we just enrolled would still be taught as the
      // deployment's default learner, and their record would stay empty.
      const seen = await fetch(`${CORE_HTTP}/teacher/identify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_base64: grab(video) }),
      }).then(r => r.json()).catch(() => null) as { recognised?: boolean } | null
      if (!seen?.recognised) {
        // Enrolled but not matched back: the threshold did not clear on this
        // frame. Say so rather than promise a lesson that opens as somebody
        // else -- another frame, or better light, usually settles it.
        setRefusal(L.stranger)
        return
      }

      settled.current = true
      const found = { learnerId: body.learnerId, displayName: body.displayName || name.trim() }
      setWho(found)
      setPhase('known')
      onKnown(found)
    }
    catch {
      setRefusal(L.stranger)
    }
    finally {
      setBusy(false)
    }
  }, [name, consent, onKnown])

  return (
    <section
      data-lobby="camera"
      data-phase={phase}
      className="flex items-center gap-[1.2vw] rounded-3xl bg-ink-900/70 p-[1.4vh_1.2vw] ring-1 ring-cream/10"
    >
      <div className="relative aspect-square w-[clamp(4.5rem,6.5vw,7.5rem)] shrink-0 overflow-hidden rounded-2xl bg-ink-950">
        <video
          ref={videoRef}
          muted
          playsInline
          className={`h-full w-full object-cover [transform:scaleX(-1)] ${
            phase === 'no-camera' ? 'opacity-0' : 'opacity-100'
          }`}
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-[1vh]">
        {phase === 'no-camera' && <p className="text-[clamp(1rem,1.5vw,1.7rem)] text-muted">{L.noCamera}</p>}
        {(phase === 'starting' || phase === 'looking') && (
          <p className="text-[clamp(1rem,1.5vw,1.7rem)] text-muted">{L.looking}</p>
        )}
        {phase === 'known' && who && (
          <p data-lobby="known" className="font-display text-[clamp(1.4rem,2.2vw,2.4rem)] font-extrabold text-mint">
            {L.hello(who.displayName)}
          </p>
        )}

        {phase === 'stranger' && (
          <>
            <p className="text-[clamp(1.05rem,1.6vw,1.8rem)] text-cream">{L.stranger}</p>
            <button
              type="button"
              data-lobby="im-new"
              onClick={() => setPhase('enrolling')}
              className="w-fit whitespace-nowrap rounded-2xl bg-amber px-[1.4vw] py-[1.1vh] font-display text-[clamp(0.95rem,1.3vw,1.45rem)] font-extrabold text-ink-900"
            >
              {L.imNew}
            </button>
          </>
        )}

        {phase === 'enrolling' && (
          <div className="flex flex-col gap-3">
            <p className="font-display text-xl font-extrabold text-cream">{L.enrolTitle}</p>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={L.enrolName}
              maxLength={40}
              className="w-full rounded-xl bg-ink-950 px-4 py-3 text-lg text-cream outline-none ring-2 ring-ink-600 focus:ring-sky"
            />
            <p className="text-sm text-muted">{L.enrolWhat}</p>
            <label className="flex items-start gap-3 text-base text-cream">
              <input
                type="checkbox"
                checked={consent}
                onChange={e => setConsent(e.target.checked)}
                className="mt-1 h-5 w-5 shrink-0"
              />
              <span>{L.enrolConsent}</span>
            </label>
            {refusal && <p className="text-base text-coral">{refusal}</p>}
            <div className="flex gap-3">
              <button
                type="button"
                data-lobby="enrol-go"
                disabled={!name.trim() || !consent || busy}
                onClick={() => { void enrol() }}
                className="rounded-2xl bg-amber px-5 py-3 font-display text-lg font-extrabold text-ink-900 disabled:opacity-40"
              >
                {busy ? L.enrolWorking : L.enrolGo}
              </button>
              <button
                type="button"
                onClick={() => { setPhase('stranger'); setRefusal(null) }}
                className="rounded-2xl bg-ink-700 px-5 py-3 font-display text-lg text-cream"
              >
                {L.enrolCancel}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
