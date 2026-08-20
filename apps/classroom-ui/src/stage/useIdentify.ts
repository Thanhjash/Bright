/**
 * Send one still frame to Core, occasionally, so the room knows who is here.
 *
 * WHAT CROSSES THE WIRE. A JPEG of one frame, and nothing else. Core hands it
 * to the vision service, which answers with a `student_id` and a confidence and
 * keeps the face to itself. The teacher never receives the frame, the box, the
 * embedding, or the name — she receives an id, and through it that learner's
 * recorded evidence (NORTH-STAR, "Identity is the system's job, not the
 * model's").
 *
 * WHY IT IS SLOW ON PURPOSE. Recognition is not a reflex and nothing waits on
 * it: Core stores the answer and uses it the next time it opens a class. A
 * frame every few seconds is plenty for "which child sat down", and anything
 * faster spends CPU that the teacher's own turn needs — on this box the model
 * already keeps a child waiting ~19s, and a face detector competing with it
 * makes that worse for no gain.
 *
 * WHAT IT DOES NOT DO. It never enrols. Enrolment is a deliberate, consented
 * act on the adult console; the camera only ever matches (rule 3). And it stops
 * entirely as soon as the room is confident, because re-identifying the same
 * child for the rest of the period is pure cost.
 */
import { useEffect, useRef } from 'react'
import { CORE_HTTP } from '../lib/env'

/** Long enough to be cheap, short enough that a child who sits down is seen. */
const EVERY_MS = 6000
/** Give up after this many tries: an empty chair should not poll forever. */
const MAX_TRIES = 10
/** Small enough to post cheaply, big enough for a detector. */
const WIDTH = 480

export interface Identified {
  recognised: boolean
  studentId: string | null
  displayName?: string
}

export function useIdentify(
  video: React.RefObject<HTMLVideoElement | null>,
  active: boolean,
  onIdentified: (who: Identified) => void,
) {
  const tries = useRef(0)
  const done = useRef(false)

  useEffect(() => {
    if (!active) return
    done.current = false
    tries.current = 0
    let cancelled = false

    const grab = async () => {
      const el = video.current
      if (!el || !el.videoWidth || done.current || cancelled) return
      const scale = WIDTH / el.videoWidth
      const canvas = document.createElement('canvas')
      canvas.width = WIDTH
      canvas.height = Math.round(el.videoHeight * scale)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.drawImage(el, 0, 0, canvas.width, canvas.height)

      // toDataURL rather than a Blob upload: Core's route takes base64, and one
      // small JPEG a few seconds apart is not worth a multipart parser.
      const base64 = canvas.toDataURL('image/jpeg', 0.8).split(',')[1]
      if (!base64) return

      try {
        const res = await fetch(`${CORE_HTTP}/teacher/identify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_base64: base64 }),
        })
        if (!res.ok) return
        const who: Identified = await res.json()
        if (cancelled) return
        if (who.recognised && who.studentId) {
          // Stop asking. The same child does not need recognising twice, and
          // Core expires the answer on its own if the period runs long.
          done.current = true
          onIdentified(who)
        }
      } catch {
        // A camera is optional and vision may be down. Never let this surface
        // in the room: the lesson does not depend on it.
      }
    }

    const timer = window.setInterval(() => {
      if (done.current || tries.current >= MAX_TRIES) {
        window.clearInterval(timer)
        return
      }
      tries.current += 1
      void grab()
    }, EVERY_MS)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [active, video, onIdentified])
}
