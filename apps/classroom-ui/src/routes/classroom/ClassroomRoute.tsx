/**
 * `/classroom` — the room. The only page the children see.
 *
 * Board, teacher, and nothing else. `/control` is adult observability and an
 * emergency lever; it never appears on the projector. See
 * `docs/decisions/2026-08-18-room-runs-itself.md`.
 *
 * The audio unlock is armed HERE and only here. Browsers refuse to start an
 * AudioContext without a gesture, so the adult who boots the appliance pays for
 * it once. Arming it globally (it used to live in `main.tsx`) meant `/control`
 * silently constructed a SpeechPlayer it must never own.
 */
import { useEffect } from 'react'
import { BusProvider } from '../../bus'
import { Stage } from '../../stage/Stage'
import { unlockAudioOnFirstGesture } from '../../speech/speakingDriver'

export function ClassroomRoute() {
  useEffect(() => { unlockAudioOnFirstGesture() }, [])
  return (
    <BusProvider role="stage">
      <Stage />
    </BusProvider>
  )
}
