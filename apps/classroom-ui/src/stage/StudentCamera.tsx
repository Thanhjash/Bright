/**
 * The student's own corner of the room -- opposite the avatar.
 *
 * Face recognition is not built (NORTH-STAR §3, "Identity is the system's
 * job, not the model's"): there is no `student_id` this component can ever
 * resolve, and it must never guess one. What it CAN show honestly today is a
 * real self-view -- the child sees themselves, the way a mirror would.
 * `getUserMedia` stays local to this tab: nothing is recorded, nothing is
 * sent anywhere, and nothing here performs recognition (NS-3 -- the model
 * never touches a camera either).
 *
 * Four states, and only four. No state fabricates a video feed:
 *
 *   no-camera   no video input device exists on this machine
 *   off         a device exists but the stream is not running (permission
 *               denied or revoked, or the track ended)
 *   live        a real MediaStream is attached to the <video> below
 *   recognised  live + `recognisedName` -- the seam for when perception
 *               ships. Core would hand this component a name resolved from
 *               a `student_id`; this file never resolves a face itself.
 */
import { useEffect, useRef, useState } from 'react'
import { CAMERA_LABELS } from '../room/labels'

type CameraStatus = 'requesting' | 'live' | 'off' | 'no-camera'

export function StudentCamera({ recognisedName }: { recognisedName?: string }) {
  const [status, setStatus] = useState<CameraStatus>('requesting')
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    let cancelled = false

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('no-camera')
      return
    }

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'user' }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setStatus('live')
        // The OS can revoke the camera mid-class -- another app claims it,
        // the adult unplugs it. Fall back to an honest 'off' rather than
        // freezing the last frame and pretending it is still live.
        stream.getVideoTracks().forEach((track) => {
          track.addEventListener('ended', () => {
            if (!cancelled) setStatus('off')
          })
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const name = err instanceof DOMException ? err.name : ''
        setStatus(name === 'NotFoundError' || name === 'OverconstrainedError' ? 'no-camera' : 'off')
      })

    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }
  }, [])

  const label = status === 'live'
    ? (recognisedName ? CAMERA_LABELS.recognised(recognisedName) : CAMERA_LABELS.live)
    : status === 'requesting'
      ? CAMERA_LABELS.requesting
      : status === 'off'
        ? CAMERA_LABELS.off
        : CAMERA_LABELS.noCamera

  return (
    <div
      data-stage="camera"
      className="pointer-events-none flex h-full w-full flex-col overflow-hidden rounded-[1.4rem] bg-ink-950/85 ring-3 ring-sky/40 backdrop-blur-sm"
    >
      <div className="relative h-[68%] w-full shrink-0 bg-ink-900">
        {/* The video element always exists so a real stream can attach the
            instant it arrives -- no remount, no flash. It stays invisible
            (not display:none) until `live`, which is why a plain opacity
            toggle here is not "faking" a feed: there is nothing behind it
            in any other state. */}
        <video
          ref={videoRef}
          className={
            'absolute inset-0 h-full w-full object-cover [transform:scaleX(-1)] '
            + (status === 'live' ? 'opacity-100' : 'opacity-0')
          }
          autoPlay
          muted
          playsInline
        />
        {status !== 'live' ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <CameraGlyph status={status} />
          </div>
        ) : recognisedName ? (
          <span className="absolute bottom-[6%] left-1/2 -translate-x-1/2 rounded-full bg-mint/90 px-[0.6vw] py-[0.2vh] font-display text-[clamp(0.6rem,0.85vw,0.8rem)] font-extrabold text-ink-900">
            {recognisedName}
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-[0.15vh] px-[0.5vw] text-center">
        <span className="font-display text-[clamp(0.68rem,0.9vw,0.9rem)] font-extrabold leading-tight text-cream">
          {label.cta}
        </span>
        <span className="font-display text-[clamp(0.56rem,0.7vw,0.7rem)] leading-tight text-muted">
          {label.sub}
        </span>
      </div>
    </div>
  )
}

function CameraGlyph({ status }: { status: Exclude<CameraStatus, 'live'> }) {
  const tone = status === 'requesting' ? 'text-sky/80' : status === 'off' ? 'text-amber/70' : 'text-muted/60'
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={`h-[34%] w-[34%] ${tone} ${status === 'requesting' ? 'animate-pulse' : ''}`}
      aria-hidden
    >
      <path
        d="M4 8.5C4 7.67 4.67 7 5.5 7H8l1-1.5h6L16 7h2.5c.83 0 1.5.67 1.5 1.5v9c0 .83-.67 1.5-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-9Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="13" r="3.2" stroke="currentColor" strokeWidth="1.6" />
      {status === 'no-camera' || status === 'off' ? (
        <path d="M3 3l18 18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      ) : null}
    </svg>
  )
}
