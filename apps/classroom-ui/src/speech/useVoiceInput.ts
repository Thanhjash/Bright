/**
 * Core-assigned answer-station capture.
 *
 * Core owns learner attribution and issues an assignment plus one capture
 * attempt. The child presses Ready at the physical station; only then is the
 * microphone opened. Local energy endpointing closes the take, dedicated ASR
 * produces text, and the browser sends exactly one correlated final result.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CaptureOutcome, CaptureRequest, TurnAssignment } from '@contracts'
import type { Bus } from '../bus'
import { setLocalCapabilities } from '../bus/clientCapabilities'
import { useClassroom } from '../store/classroom'
import { ConservativeEndpointDetector } from './captureEndpoint'
import type { EndpointResult } from './captureEndpoint'
import { createMicRecorder, MicError } from './micRecorder'
import type { Clip, MicFailure } from './micRecorder'
import { isMicrophoneSuppressed } from './outputActivity'
import { SttError, transcribe } from './stt'
import { publishAnswerStationActivity } from './answerStationActivity'
import { SYNTHETIC_FIXTURE_ID } from '../lib/env'

export type VoicePhase =
  | 'idle'
  | 'assigned'
  | 'opening'
  | 'listening'
  | 'thinking'
  | 'waiting'
  | 'error'

export const EXPECTED_STT_MS = 1_200
export const EXPECTED_FEEDBACK_MS = 2_500
const ASR_TIMEOUT_MS = 6_000
const ACK_TIMEOUT_MS = 20_000
const ENDPOINT_TICK_MS = 40

export interface VoiceResult {
  outcome: CaptureOutcome
  confidence: number
  latencyMs: number
  serviceMs: number
}

export interface VoiceFailure {
  message: string
  kind: CaptureOutcome | 'denied' | 'unsupported' | 'assignment_expired' | 'output_active'
}

export interface StationCheck {
  ok: boolean
  noiseFloor: number
  peak: number
  failure?: VoiceFailure
}

export interface VoiceInput {
  phase: VoicePhase
  assignment: TurnAssignment | null
  capture: CaptureRequest | null
  elapsedMs: number
  thinkingMs: number
  waitingMs: number
  getLevel: () => number
  last: VoiceResult | null
  error: VoiceFailure | null
  ready: () => void
  checkStation: () => Promise<StationCheck>
  cancel: () => void
}

interface ActiveAttempt {
  assignment: TurnAssignment
  capture: CaptureRequest
  utteranceId: string
  requestedAt: number
}

export function useVoiceInput(bus: Bus): VoiceInput {
  const assignment = useClassroom((state) => state.assignment)
  const capture = useClassroom((state) => state.capture)
  const [phase, setPhase] = useState<VoicePhase>('idle')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [thinkingMs, setThinkingMs] = useState(0)
  const [waitingMs, setWaitingMs] = useState(0)
  const [last, setLast] = useState<VoiceResult | null>(null)
  const [error, setError] = useState<VoiceFailure | null>(null)
  const [noiseFloor, setNoiseFloor] = useState(0.012)

  const attempt = useRef<ActiveAttempt | null>(null)
  const handledCaptureIds = useRef(new Set<string>())
  const acceptedUtteranceId = useRef<string | null>(null)
  const detector = useRef<ConservativeEndpointDetector | null>(null)
  const endpointTimer = useRef(0)
  const deadlineTimer = useRef(0)
  const ackTimer = useRef(0)
  const asrAbort = useRef<AbortController | null>(null)
  const captureStartedAt = useRef(0)
  const phaseStartedAt = useRef(0)
  const finishing = useRef(false)
  const activeRef = useRef(false)

  const onDeviceFailure = useCallback((failure: MicFailure) => {
    setLocalCapabilities({ microphone: failure })
    if (!activeRef.current || !attempt.current) {
      setError(describeMicFailure(failure))
      setPhase('error')
      return
    }
    void finishInfrastructureFailure(failure)
  // finishInfrastructureFailure is stable through refs and intentionally not a
  // dependency: the device callback is installed once with the recorder.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const mic = useMemo(() => createMicRecorder(onDeviceFailure), [onDeviceFailure])

  const clearTimers = useCallback(() => {
    window.clearInterval(endpointTimer.current)
    window.clearTimeout(deadlineTimer.current)
    window.clearTimeout(ackTimer.current)
    endpointTimer.current = 0
    deadlineTimer.current = 0
    ackTimer.current = 0
  }, [])

  const resetAttempt = useCallback((releaseMic = true) => {
    clearTimers()
    asrAbort.current?.abort()
    asrAbort.current = null
    detector.current = null
    activeRef.current = false
    finishing.current = false
    attempt.current = null
    if (releaseMic) mic.release()
  }, [clearTimers, mic])

  const sendFinal = useCallback((
    outcome: CaptureOutcome,
    text: string,
    confidence: number,
    serviceMs = 0,
  ) => {
    const current = attempt.current
    if (!current || handledCaptureIds.current.has(current.capture.captureId)) return
    handledCaptureIds.current.add(current.capture.captureId)
    const latencyMs = Math.round(performance.now() - captureStartedAt.current)
    acceptedUtteranceId.current = current.utteranceId
    bus.send('student.speech.final', {
      text,
      confidence,
      utteranceId: current.utteranceId,
      assignmentId: current.assignment.assignmentId,
      responseTurnId: current.assignment.responseTurnId,
      captureId: current.capture.captureId,
      captureOutcome: outcome,
      activityId: current.assignment.activityId,
      activityGeneration: current.assignment.activityGeneration,
      ...(SYNTHETIC_FIXTURE_ID ? {
        synthetic: true as const,
        syntheticFixtureId: SYNTHETIC_FIXTURE_ID,
      } : {}),
    })
    setLast({ outcome, confidence, latencyMs, serviceMs })
    setWaitingMs(0)
    phaseStartedAt.current = performance.now()
    setPhase('waiting')
    activeRef.current = false
    mic.release()
    ackTimer.current = window.setTimeout(() => {
      setError({
        kind: 'asr_unavailable',
        message: 'The lesson did not acknowledge this attempt. Bright kept it out of learner memory.',
      })
      setPhase('error')
      resetAttempt(false)
    }, ACK_TIMEOUT_MS)
  }, [bus, mic, resetAttempt])

  const finishClip = useCallback(async (endpoint: EndpointResult, clip: Clip | null) => {
    if (!attempt.current) return
    if (endpoint.outcome !== 'speech' || !clip) {
      sendFinal(endpoint.outcome, '', 0)
      return
    }

    setThinkingMs(0)
    phaseStartedAt.current = performance.now()
    setPhase('thinking')
    const controller = new AbortController()
    asrAbort.current = controller
    const timeout = window.setTimeout(() => controller.abort('asr-timeout'), ASR_TIMEOUT_MS)
    try {
      const result = await transcribe(clip.audio, controller.signal)
      sendFinal('speech', result.text, result.confidence, result.serviceMs)
    }
    catch (cause) {
      if (controller.signal.aborted) {
        sendFinal('asr_timeout', '', 0)
      }
      else if (cause instanceof SttError && cause.failure === 'empty') {
        // Energy without reliable recognisable speech is noise, never learner
        // silence and never evidence of a wrong answer.
        sendFinal('noise_only', '', 0)
      }
      else {
        sendFinal('asr_unavailable', '', 0)
      }
    }
    finally {
      window.clearTimeout(timeout)
      asrAbort.current = null
    }
  }, [sendFinal])

  const finishEndpoint = useCallback((endpoint: EndpointResult) => {
    if (finishing.current) return
    finishing.current = true
    clearTimers()
    void mic.stop().then((clip) => finishClip(endpoint, clip))
  }, [clearTimers, finishClip, mic])

  async function finishInfrastructureFailure(failure: MicFailure): Promise<void> {
    if (finishing.current) return
    finishing.current = true
    clearTimers()
    asrAbort.current?.abort(failure)
    await mic.stop().catch(() => null)
    sendFinal('device_lost', '', 0)
    setError(describeMicFailure(failure))
  }

  const ready = useCallback(() => {
    const assigned = assignment
    const requested = capture
    if (!assigned || !requested || phase !== 'assigned') return
    if (
      assigned.assignmentId !== requested.assignmentId
      || assigned.responseTurnId !== requested.responseTurnId
      || assigned.expiresAt <= Date.now()
      || requested.readyDeadlineAt <= Date.now()
    ) {
      setError({ kind: 'assignment_expired', message: 'This turn has expired. Wait for Bright to call again.' })
      setPhase('error')
      return
    }
    if (isMicrophoneSuppressed()) {
      // The Stage intentionally keeps the microphone suppressed for a short
      // acoustic echo tail after its playback ACK. That is a normal transient,
      // not an endpoint failure: reporting `failed` here would make Core
      // safe-pause an otherwise healthy class. VoicePanel disables Ready until
      // this guard becomes false; retain the guard for stale/rapid clicks.
      return
    }

    setPhase('opening')
    setError(null)
    setLast(null)
    finishing.current = false
    const current: ActiveAttempt = {
      assignment: assigned,
      capture: requested,
      utteranceId: crypto.randomUUID(),
      requestedAt: performance.now(),
    }
    attempt.current = current

    void (async () => {
      try {
        await mic.prepare()
        if (attempt.current?.capture.captureId !== requested.captureId) return
        bus.send('response.capture.ready', {
          assignmentId: assigned.assignmentId,
          responseTurnId: assigned.responseTurnId,
          captureId: requested.captureId,
          status: 'ready',
        })
        detector.current = new ConservativeEndpointDetector({
          noiseFloor,
          maxDurationMs: requested.maxDurationMs,
          endSilenceMs: requested.endSilenceMs,
        })
        await mic.start(() => {
          // A non-terminal sample is expected for almost every audio frame.
          // Never coalesce it into deadline(): only Core's explicit onset
          // timer may declare no_speech/noise_only.
          const terminal = detector.current?.sample(mic.level(), performance.now())
          if (detector.current?.hasSpeech && deadlineTimer.current) {
            window.clearTimeout(deadlineTimer.current)
            deadlineTimer.current = 0
          }
          if (terminal) finishEndpoint(terminal)
        }, requested.maxDurationMs)
        captureStartedAt.current = performance.now()
        phaseStartedAt.current = captureStartedAt.current
        activeRef.current = true
        bus.send('response.capture.started', {
          assignmentId: assigned.assignmentId,
          responseTurnId: assigned.responseTurnId,
          captureId: requested.captureId,
        })
        setPhase('listening')
        endpointTimer.current = window.setInterval(() => {
          const terminal = detector.current?.sample(mic.level(), performance.now())
          if (detector.current?.hasSpeech && deadlineTimer.current) {
            window.clearTimeout(deadlineTimer.current)
            deadlineTimer.current = 0
          }
          if (terminal) finishEndpoint(terminal)
        }, ENDPOINT_TICK_MS)
        deadlineTimer.current = window.setTimeout(() => {
          const terminal = detector.current?.deadline(performance.now())
          if (terminal) finishEndpoint(terminal)
        }, Math.min(requested.speechOnsetDeadlineMs, requested.maxDurationMs))
      }
      catch (cause) {
        const failure = cause instanceof MicError
          ? describeMicFailure(cause.failure)
          : { kind: 'device_lost' as const, message: 'The answer-station microphone could not start.' }
        bus.send('response.capture.ready', {
          assignmentId: assigned.assignmentId,
          responseTurnId: assigned.responseTurnId,
          captureId: requested.captureId,
          status: 'failed',
          reason: failure.kind,
        })
        setLocalCapabilities({ microphone: failure.kind })
        setError(failure)
        setPhase('error')
        resetAttempt()
      }
    })()
  }, [assignment, bus, capture, finishEndpoint, mic, noiseFloor, phase, resetAttempt])

  const checkStation = useCallback(async (): Promise<StationCheck> => {
    let peak = 0
    const samples: number[] = []
    try {
      await mic.prepare()
      for (let i = 0; i < 20; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 40))
        const level = mic.level()
        peak = Math.max(peak, level)
        samples.push(level)
      }
      samples.sort((a, b) => a - b)
      const floor = Math.max(0.002, samples[Math.floor(samples.length * 0.8)] ?? 0.012)
      setNoiseFloor(floor)
      setLocalCapabilities({ microphone: true, mic_noise_floor: Number(floor.toFixed(4)) })
      return { ok: true, noiseFloor: floor, peak }
    }
    catch (cause) {
      const failure = cause instanceof MicError
        ? describeMicFailure(cause.failure)
        : { kind: 'device_lost' as const, message: 'The microphone check failed.' }
      setLocalCapabilities({ microphone: false, microphone_reason: failure.kind })
      return { ok: false, noiseFloor, peak, failure }
    }
    finally {
      mic.release()
    }
  }, [mic, noiseFloor])

  const cancel = useCallback(() => {
    if (attempt.current && !handledCaptureIds.current.has(attempt.current.capture.captureId))
      sendFinal('device_lost', '', 0)
    resetAttempt()
    setPhase('idle')
  }, [resetAttempt, sendFinal])

  useEffect(() => {
    publishAnswerStationActivity({
      phase,
      assignmentId: assignment?.assignmentId,
      captureId: capture?.captureId,
    })
  }, [assignment?.assignmentId, capture?.captureId, phase])

  useEffect(() => {
    if (!assignment || !capture) {
      if (!activeRef.current && phase !== 'thinking' && phase !== 'waiting') setPhase('idle')
      return
    }
    const same = assignment.assignmentId === capture.assignmentId
      && assignment.responseTurnId === capture.responseTurnId
    if (!same || handledCaptureIds.current.has(capture.captureId)) return
    if (attempt.current?.capture.captureId === capture.captureId) return
    resetAttempt()
    setError(null)
    setLast(null)
    setPhase('assigned')
  }, [assignment, capture, resetAttempt])

  useEffect(
    () => bus.on('student.response.accepted', ({ utteranceId }) => {
      if (utteranceId !== acceptedUtteranceId.current) return
      acceptedUtteranceId.current = null
      resetAttempt(false)
      setPhase('idle')
    }),
    [bus, resetAttempt],
  )

  useEffect(() => {
    if (phase !== 'listening' && phase !== 'thinking' && phase !== 'waiting') return
    const timer = window.setInterval(() => {
      const elapsed = performance.now() - phaseStartedAt.current
      if (phase === 'listening') setElapsedMs(elapsed)
      else if (phase === 'thinking') setThinkingMs(elapsed)
      else setWaitingMs(elapsed)
    }, 100)
    return () => window.clearInterval(timer)
  }, [phase])

  useEffect(() => () => resetAttempt(), [resetAttempt])

  return {
    phase,
    assignment,
    capture,
    elapsedMs: phase === 'listening' ? elapsedMs : 0,
    thinkingMs: phase === 'thinking' ? thinkingMs : 0,
    waitingMs: phase === 'waiting' ? waitingMs : 0,
    getLevel: mic.level,
    last,
    error,
    ready,
    checkStation,
    cancel,
  }
}

function describeMicFailure(failure: MicFailure): VoiceFailure {
  switch (failure) {
    case 'denied':
    case 'permission_lost':
      return { kind: 'denied', message: 'Microphone permission is blocked. Allow it, then run the check again.' }
    case 'unsupported':
      return { kind: 'unsupported', message: 'This browser cannot use the answer-station microphone.' }
    case 'device_lost':
      return { kind: 'device_lost', message: 'The answer-station microphone was unplugged. Reconnect it before continuing.' }
    case 'unavailable':
      return { kind: 'device_lost', message: 'No answer-station microphone is available.' }
  }
}
