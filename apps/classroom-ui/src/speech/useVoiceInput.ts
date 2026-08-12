/**
 * The student's voice, end to end.
 *
 *     hold → mic → Whisper → `student.speech.final` on the bus
 *
 * ── WHY IT LOOKS THE WAY IT DOES ──────────────────────────────────────────
 * A transcription costs ~3.4 s and cannot be made cheaper: Whisper always
 * processes a 30-second window, so the price is per CALL, not per second of
 * speech (`stt.ts`). Three and a half seconds of nothing, in front of a class,
 * reads as "it broke" — so the phase is never implicit:
 *
 *     idle → opening → listening → thinking → waiting → idle | error
 *
 * `thinking` is only the FIRST half of the wait. With the teacher agent live
 * (`BRIGHT_AGENT=1`) a spoken answer costs ~3.4 s of Whisper and then up to ~6 s
 * of the agent deciding what to do about it — call it ten seconds between a
 * child stopping speaking and the board changing. So the machine does not
 * return to `idle` when the transcript lands: `waiting` holds until
 * `stateVersion` moves, which is the only honest proof that core acted on what
 * was sent. Two named waits with two running counters, instead of one counter
 * and then five silent seconds that look identical to a crash.
 *
 * `listening` shows a live level meter (a muted mic otherwise records perfect
 * silence and fails invisibly). There is no state in which the console simply
 * sits still.
 *
 * ── PUSH-TO-TALK IS THE DEFAULT, AND THAT IS DELIBERATE ───────────────────
 * The teacher holding a button is the only signal in this system that reliably
 * knows when a child started and stopped talking. Automatic mode keys off the
 * `listening` overlay flag, which is the lesson's *intent* to listen — right in
 * a quiet room, wrong the moment thirty children are talking over the answer.
 * It is offered, it is not the default.
 *
 * The store is React-local on purpose. `store/classroom.ts` is a pure
 * reflection of server events and must stay that way; the microphone is a
 * property of THIS browser window (the facilitator's laptop, never the
 * projector), so its state does not belong there. The one thing that crosses
 * over is the finished transcript, which goes onto the bus like any other
 * client event and comes back as server state.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Bus } from '../bus'
import { selectListening, useClassroom } from '../store/classroom'
import { createMicRecorder, MAX_UTTERANCE_MS, MicError } from './micRecorder'
import type { Clip } from './micRecorder'
import { SttError, transcribe } from './stt'
import {
  interruptibleSpeechTurnId,
  isMicrophoneSuppressed,
  subscribeOutputActivity,
  waitForMicrophoneRelease,
} from './outputActivity'

export type VoicePhase = 'idle' | 'opening' | 'listening' | 'thinking' | 'waiting' | 'error'
export type VoiceMode = 'ptt' | 'auto'

/** What `thinking` shows its progress against. Measured, not guessed. */
export const EXPECTED_STT_MS = 3400

/**
 * What `waiting` shows its progress against: the agent's own budget for a turn.
 * PROTOCOL.md §7 puts the FULL/DEGRADED line at 3 s of agent latency, and the
 * lead measured up to 6 s in practice, so the bar is scaled to 6 s.
 */
export const EXPECTED_AGENT_MS = 6000

/**
 * After this, core is not going to answer this utterance. The console stops
 * claiming to wait rather than counting up forever — a facilitator who has been
 * told "waiting" for half a minute has been told nothing.
 */
const WAIT_GIVE_UP_MS = 20_000

/**
 * `waiting` ends on the next `stateVersion` bump, and the protocol carries no
 * correlation id, so a bump that core was going to make anyway can end it
 * instantly. A minimum dwell keeps "your answer went out" readable instead of
 * flickering past — the facilitator needs to SEE the hand-off, not infer it.
 */
const MIN_WAIT_VISIBLE_MS = 700
const BARGE_ACK_TIMEOUT_MS = 1_200

export interface VoiceResult {
  text: string
  confidence: number
  /** press-release → transcript on screen, the number that actually matters */
  latencyMs: number
  /** what the speech service said it spent */
  serviceMs: number
}

export interface VoiceFailure {
  message: string
  /** `empty` is a normal classroom outcome (nobody spoke); the rest are faults. */
  kind: 'denied' | 'unavailable' | 'unsupported' | 'unreachable' | 'rejected' | 'empty' | 'too-short'
}

/**
 * Shorter than this and the button was tapped, not held. Sending it anyway
 * costs the full 3.4 s to be told a syllable — worse, Whisper will happily
 * transcribe half a word and the lesson will grade it.
 */
const MIN_UTTERANCE_MS = 350

export interface VoiceInput {
  phase: VoicePhase
  mode: VoiceMode
  setMode: (mode: VoiceMode) => void
  /** ms since recording started, 0 otherwise */
  elapsedMs: number
  /** ms since the POST went out, 0 otherwise */
  thinkingMs: number
  /** ms since the transcript went on the bus, 0 otherwise */
  waitingMs: number
  /** 0…1 live input level; poll it from a frame loop, it is not reactive */
  getLevel: () => number
  last: VoiceResult | null
  error: VoiceFailure | null
  /** true while automatic mode is holding the mic open */
  autoArmed: boolean
  press: () => void
  release: () => void
}

export function useVoiceInput(bus: Bus): VoiceInput {
  const mic = useMemo(() => createMicRecorder(), [])
  const [phase, setPhase] = useState<VoicePhase>('idle')
  const [mode, setMode] = useState<VoiceMode>('ptt')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [thinkingMs, setThinkingMs] = useState(0)
  const [waitingMs, setWaitingMs] = useState(0)
  const [last, setLast] = useState<VoiceResult | null>(null)
  const [error, setError] = useState<VoiceFailure | null>(null)
  const [outputSuppressed, setOutputSuppressed] = useState(isMicrophoneSuppressed)

  const log = useClassroom((s) => s.log)
  const listening = useClassroom(selectListening)
  const [acceptedUtteranceId, setAcceptedUtteranceId] = useState<string | null>(null)

  // A press that arrives while a transcription is still in flight must not
  // start a second recording, and a release that arrives before `getUserMedia`
  // resolves must still stop the take that is about to begin.
  const busy = useRef(false)
  const wantsStop = useRef(false)
  const startedAt = useRef(0)
  const waitingSince = useRef(0)
  const phaseRef = useRef<VoicePhase>('idle')
  const discardCapture = useRef(false)
  const bargeRequest = useRef<string | null>(null)
  const pendingBargeAcks = useRef(new Map<
    string,
    (ack: { accepted: boolean; speechTurnId: string; reason?: string }) => void
  >())
  const utterance = useRef<{
    utteranceId: string
    activityId: string
    activityGeneration: number
  } | null>(null)

  useEffect(() => {
    phaseRef.current = phase
  }, [phase])
  useEffect(() => () => mic.release(), [mic])
  useEffect(
    () => bus.on('student.response.accepted', ({ utteranceId }) => setAcceptedUtteranceId(utteranceId)),
    [bus],
  )
  useEffect(() => {
    const off = bus.on('speech.barge_in.ack', (ack) => {
      pendingBargeAcks.current.get(ack.requestId)?.(ack)
    })
    return () => {
      off()
      pendingBargeAcks.current.clear()
    }
  }, [bus])

  const finish = useCallback(
    async (clip: Clip | null) => {
      const releasedAt = performance.now()
      if (discardCapture.current) {
        discardCapture.current = false
        utterance.current = null
        setPhase('idle')
        busy.current = false
        return
      }
      if (!clip) {
        setPhase('idle')
        busy.current = false
        return
      }
      if (clip.durationMs < MIN_UTTERANCE_MS) {
        const message = 'That was a tap, not a hold. Keep the button down while the child speaks.'
        setError({ message, kind: 'too-short' })
        setPhase('error')
        log('system', `voice — ${message}`)
        busy.current = false
        return
      }
      setPhase('thinking')
      setThinkingMs(0)
      try {
        const result = await transcribe(clip.audio)
        const latencyMs = Math.round(performance.now() - releasedAt)
        setLast({ ...result, latencyMs })
        setError(null)
        waitingSince.current = performance.now()
        setWaitingMs(0)
        setPhase('waiting')

        const correlation = utterance.current
        if (!correlation) {
          throw new Error('voice capture has no active lesson correlation')
        }

        // Raw child speech exists only long enough to grade this event. Never
        // copy it into the console transcript/log, which survives in memory
        // and is visible to facilitators after the turn.
        log('system', 'voice — spoken answer received')
        bus.send('student.speech.final', {
          text: result.text,
          confidence: result.confidence,
          ...correlation,
          ...currentStudent(),
        })
      } catch (cause) {
        const failure = describe(cause)
        setError(failure)
        setPhase('error')
        console.error('[voice]', failure.kind, cause)
        log('system', `voice — ${failure.message}`)
      } finally {
        busy.current = false
      }
    },
    [bus, log],
  )

  useEffect(
    () => subscribeOutputActivity(() => {
      const suppressed = isMicrophoneSuppressed()
      setOutputSuppressed(suppressed)
      if (!suppressed || !busy.current)
        return
      if (phaseRef.current !== 'opening' && phaseRef.current !== 'listening')
        return
      // During an authorized barge-in, this is the exact terminal signal we
      // are waiting for. It is not a new teacher-output race.
      if (bargeRequest.current !== null)
        return
      // Teacher output won the half-duplex race. Never send a clip that may
      // contain the projector's voice back through ASR.
      discardCapture.current = true
      wantsStop.current = true
      if (mic.recording())
        void mic.stop().then(finish)
    }),
    [finish, mic],
  )

  const openMicrophone = useCallback(() => {
    void (async () => {
      try {
        await mic.start(() => {
          // The cap fired: the button was never released. Treat it as a
          // release rather than throwing the audio away.
          log('system', `voice — stopped at the ${Math.round(MAX_UTTERANCE_MS / 1000)}s limit`)
          void mic.stop().then(finish)
        })
      } catch (cause) {
        const failure = describe(cause)
        setError(failure)
        setPhase('error')
        console.error('[voice]', failure.kind, cause)
        log('system', `voice — ${failure.message}`)
        busy.current = false
        return
      }
      if (wantsStop.current) {
        // Released during `getUserMedia`. Honour it now.
        void mic.stop().then(finish)
        return
      }
      startedAt.current = performance.now()
      setPhase('listening')
    })()
  }, [finish, log, mic])

  const requestBargeIn = useCallback(async (
    speechTurnId: string,
    activityId: string,
    activityGeneration: number,
  ): Promise<{ accepted: boolean; reason?: string }> => {
    const requestId = crypto.randomUUID()
    bargeRequest.current = requestId
    const ack = new Promise<{ accepted: boolean; speechTurnId: string; reason?: string }>((resolve) => {
      pendingBargeAcks.current.set(requestId, resolve)
    })
    bus.send('speech.barge_in', {
      requestId,
      speechTurnId,
      activityId,
      activityGeneration,
    })
    let timer = 0
    try {
      const reply = await Promise.race([
        ack,
        new Promise<null>((resolve) => {
          timer = window.setTimeout(() => resolve(null), BARGE_ACK_TIMEOUT_MS)
        }),
      ])
      if (!reply)
        return { accepted: false, reason: 'Core did not acknowledge the interruption.' }
      if (reply.speechTurnId !== speechTurnId)
        return { accepted: false, reason: 'Core acknowledged a different speech turn.' }
      if (!reply.accepted)
        return { accepted: false, reason: reply.reason ?? 'Core rejected the interruption.' }
      const released = await waitForMicrophoneRelease(speechTurnId)
      if (!released)
        return { accepted: false, reason: 'Stage did not confirm that teacher audio stopped.' }
      return { accepted: true }
    }
    finally {
      if (timer) window.clearTimeout(timer)
      pendingBargeAcks.current.delete(requestId)
      if (bargeRequest.current === requestId) bargeRequest.current = null
    }
  }, [bus])

  const press = useCallback(() => {
    if (busy.current) return
    const lesson = useClassroom.getState().lesson
    if (!lesson) {
      const message = 'No active lesson is available for this answer.'
      setError({ message, kind: 'rejected' })
      return
    }
    utterance.current = {
      utteranceId: crypto.randomUUID(),
      activityId: lesson.activityId,
      activityGeneration: lesson.activityGeneration,
    }
    setAcceptedUtteranceId(null)
    discardCapture.current = false
    busy.current = true
    wantsStop.current = false
    setError(null)
    setLast(null)
    setElapsedMs(0)
    setPhase('opening')

    if (isMicrophoneSuppressed()) {
      const speechTurnId = interruptibleSpeechTurnId()
      if (!speechTurnId) {
        const message = 'Teacher audio cannot be interrupted safely right now.'
        setError({ message, kind: 'rejected' })
        setPhase('error')
        busy.current = false
        log('system', `voice — ${message}`)
        return
      }
      void requestBargeIn(
        speechTurnId,
        lesson.activityId,
        lesson.activityGeneration,
      ).then((result) => {
        if (!result.accepted) {
          const message = result.reason ?? 'Teacher audio could not be interrupted safely.'
          setError({ message, kind: 'rejected' })
          setPhase('error')
          busy.current = false
          log('system', `voice — ${message}`)
          return
        }
        if (wantsStop.current) {
          setPhase('idle')
          busy.current = false
          return
        }
        openMicrophone()
      })
      return
    }
    openMicrophone()
  }, [log, openMicrophone, requestBargeIn])

  const release = useCallback(() => {
    if (!busy.current) return
    wantsStop.current = true
    if (mic.recording()) void mic.stop().then(finish)
  }, [finish, mic])

  // Automatic mode: the lesson's `listening` overlay flag opens and closes the
  // microphone. Driven on TRANSITIONS, not on every render — `press` and
  // `release` change identity whenever the bus does, and re-firing them on that
  // would either restart a take or cut one short. Switching back to
  // push-to-talk mid-utterance closes the mic through the same edge.
  const autoArmed = mode === 'auto' && listening && !outputSuppressed
  const autoHolding = useRef(false)
  useEffect(() => {
    if (autoArmed === autoHolding.current) return
    autoHolding.current = autoArmed
    if (autoArmed) press()
    else release()
  }, [autoArmed, press, release])

  // Waiting ends only on the ACK for this utterance. Scene/state updates can be
  // unrelated (timer, facilitator command, agent action) and are not proof that
  // the child's answer was accepted.
  useEffect(() => {
    if (phase !== 'waiting') return

    if (acceptedUtteranceId === utterance.current?.utteranceId) {
      const dwell = MIN_WAIT_VISIBLE_MS - (performance.now() - waitingSince.current)
      const id = window.setTimeout(() => setPhase('idle'), Math.max(0, dwell))
      return () => window.clearTimeout(id)
    }

    const id = window.setTimeout(() => {
      setPhase('idle')
      log('system', 'voice — no reply from the lesson; the answer may not have been used')
    }, WAIT_GIVE_UP_MS)
    return () => window.clearTimeout(id)
  }, [acceptedUtteranceId, phase, log])

  // One timer for all three counters. It exists only while something is
  // happening, so an idle console does no work at all.
  useEffect(() => {
    if (phase !== 'listening' && phase !== 'thinking' && phase !== 'waiting') return
    const from = performance.now()
    const id = window.setInterval(() => {
      if (phase === 'listening') setElapsedMs(performance.now() - startedAt.current)
      else if (phase === 'thinking') setThinkingMs(performance.now() - from)
      else setWaitingMs(performance.now() - from)
    }, 100)
    return () => window.clearInterval(id)
  }, [phase])

  return {
    phase,
    mode,
    setMode,
    elapsedMs: phase === 'listening' ? elapsedMs : 0,
    thinkingMs: phase === 'thinking' ? thinkingMs : 0,
    waitingMs: phase === 'waiting' ? waitingMs : 0,
    getLevel: mic.level,
    last,
    error,
    autoArmed,
    press,
    release,
  }
}

/** `student.speech.final.studentId` is optional; send it when core told us one. */
function currentStudent(): { studentId?: string } {
  const id = useClassroom.getState().lesson?.currentStudentId
  return id ? { studentId: id } : {}
}

function describe(cause: unknown): VoiceFailure {
  if (cause instanceof MicError) return { message: cause.message, kind: cause.failure }
  if (cause instanceof SttError) return { message: cause.message, kind: cause.failure }
  return {
    message: cause instanceof Error ? cause.message : String(cause),
    kind: 'rejected',
  }
}
