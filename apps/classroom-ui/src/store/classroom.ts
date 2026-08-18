/**
 * The single client-side store.
 *
 * It is a **pure reflection of server events**. Every mutator below is called
 * from `bus/wiring.ts` in response to something classroom-core said. Nothing
 * in the UI advances the lesson, grades an answer, or picks the next scene —
 * components emit interaction events and wait (docs/design/runtime-topology.md §4, rule 2).
 *
 * The one exception is deliberate and local: optimistic *press* feedback on a
 * tapped card lives in component state, never here, so this invariant stays
 * literally true.
 */
import { create } from 'zustand'
import type {
  ActPayload,
  CaptureRequest,
  ClassSessionState,
  ClassroomStatusPayload,
  Emotion,
  Event,
  LessonPosition,
  Mode,
  ModeChangedPayload,
  Scene,
  SceneSnapshotPayload,
  SpeechSayPayload,
  StageLeaseGrantedPayload,
  TurnAssignment,
  TurnClosedPayload,
  ResponseCorrelation,
} from '@contracts'
import type { ConnectionStatus } from '../bus/types'
import { emotionIntensity, emotionName, scrubActTokens } from '../lib/act'

export type TranscriptKind = 'teacher' | 'student' | 'system'

export interface TranscriptEntry {
  id: string
  kind: TranscriptKind
  text: string
  ts: number
}

const TRANSCRIPT_MAX = 200

export interface AvatarState {
  emotion: Emotion
  /** 0…1 — how strongly the emotion is expressed */
  intensity: number
  speaking: boolean
  /** 0…0.7, written raw to ParamMouthOpenY by the Live2D driver (§6.5) */
  mouthOpen: number
  motion?: string
}

export interface ClassroomState {
  connection: ConnectionStatus
  /** highest stateVersion seen; sent back on `client.hello` */
  stateVersion: number
  scene: Scene | null
  lesson: LessonPosition | null
  session: ClassSessionState | null
  status: ClassroomStatusPayload | null
  assignment: TurnAssignment | null
  capture: CaptureRequest | null
  stageLease: StageLeaseGrantedPayload | null
  recovery: { reason: string; requiredAction?: string } | null
  speechLifecycle: { speechTurnId: string; status: 'queued' | 'playing' | 'terminal' } | null
  mode: Mode
  modeReason: string
  /** authoritative subtitle, from `scene.overlay.subtitle` */
  overlaySubtitle: string
  /** fallback subtitle, from the current `speech.say` */
  speechSubtitle: string
  currentTurnId: string | null
  avatar: AvatarState
  transcript: TranscriptEntry[]
  lastEventAt: number
  /** true between a gap/reconnect and the snapshot that repairs it */
  awaitingSnapshot: boolean

  // ── mutators: called only by bus/wiring.ts ──
  setConnection: (status: ConnectionStatus) => void
  discardLocalState: (reason: string) => void
  applySnapshot: (payload: SceneSnapshotPayload) => void
  applyScene: (scene: Scene) => void
  applyLesson: (lesson: LessonPosition) => void
  applySession: (session: ClassSessionState) => void
  applyStatus: (status: ClassroomStatusPayload) => void
  applyAssignment: (assignment: TurnAssignment) => void
  applyCapture: (capture: CaptureRequest) => void
  applyStageLease: (lease: StageLeaseGrantedPayload) => void
  closeTurn: (closed: TurnClosedPayload) => void
  applyMode: (payload: ModeChangedPayload) => void
  applySpeech: (payload: SpeechSayPayload) => void
  startSpeech: (turnId: string) => void
  updateSpeechText: (turnId: string, text: string) => void
  finishSpeechText: (turnId: string, text: string) => void
  cancelSpeech: (turnId: string) => void
  applyAct: (act: ActPayload) => void
  setSpeaking: (speaking: boolean) => void
  setMouthOpen: (value: number) => void
  noteEvent: (event: Event<unknown>) => void
  log: (kind: TranscriptKind, text: string) => void
}

const IDLE_AVATAR: AvatarState = {
  emotion: 'neutral',
  intensity: 1,
  speaking: false,
  mouthOpen: 0,
}

let transcriptSeq = 0

function appendTranscript(
  list: TranscriptEntry[],
  kind: TranscriptKind,
  text: string,
): TranscriptEntry[] {
  const clean = text.trim()
  if (!clean) return list
  const next = [...list, { id: `t${++transcriptSeq}`, kind, text: clean, ts: Date.now() }]
  return next.length > TRANSCRIPT_MAX ? next.slice(next.length - TRANSCRIPT_MAX) : next
}

export const useClassroom = create<ClassroomState>()((set) => ({
  connection: {
    state: 'closed',
    attempts: 0,
    retryInMs: 0,
    lastHeartbeatAt: 0,
    latencyMs: null,
    lastFrameAt: 0,
  },
  stateVersion: 0,
  scene: null,
  lesson: null,
  session: null,
  status: null,
  assignment: null,
  capture: null,
  stageLease: null,
  recovery: null,
  speechLifecycle: null,
  mode: 'FULL',
  modeReason: '',
  overlaySubtitle: '',
  speechSubtitle: '',
  currentTurnId: null,
  avatar: IDLE_AVATAR,
  transcript: [],
  lastEventAt: 0,
  awaitingSnapshot: true,

  setConnection: (connection) => set({ connection }),

  /** PROTOCOL.md §1: on a gap we discard, we never patch. `stateVersion` is
   *  kept because the next `client.hello` must report what we last saw. */
  discardLocalState: (reason) =>
    set((s) => ({
      scene: null,
      lesson: null,
      session: null,
      status: null,
      assignment: null,
      capture: null,
      stageLease: null,
      recovery: null,
      speechLifecycle: null,
      overlaySubtitle: '',
      speechSubtitle: '',
      currentTurnId: null,
      avatar: IDLE_AVATAR,
      awaitingSnapshot: true,
      transcript: appendTranscript(s.transcript, 'system', `state discarded — ${reason}`),
    })),

  applySnapshot: ({ scene, lesson, session, status, assignment, capture, speech, recovery }) =>
    set({
      scene,
      lesson,
      session: session ?? null,
      status: status ?? null,
      assignment: assignment ?? null,
      capture: capture ?? null,
      recovery: recovery ?? status?.recovery ?? null,
      speechLifecycle: speech ?? null,
      stateVersion: scene.stateVersion,
      overlaySubtitle: scene.overlay?.subtitle ?? '',
      speechSubtitle: '',
      awaitingSnapshot: false,
    }),

  applyScene: (scene) =>
    set((s) => ({
      scene,
      stateVersion: Math.max(s.stateVersion, scene.stateVersion),
      overlaySubtitle: scene.overlay?.subtitle ?? '',
      // A new scene retires the previous spoken line — otherwise a silent
      // activity keeps projecting the last thing said. Mid-utterance is the
      // exception: core may push a scene while the teacher is still talking.
      speechSubtitle: s.avatar.speaking ? s.speechSubtitle : '',
      awaitingSnapshot: false,
    })),

  applyLesson: (lesson) => set({ lesson }),

  applySession: (session) => set({ session }),

  applyStatus: (status) => set({ status, recovery: status.recovery ?? null }),

  applyAssignment: (assignment) => set({ assignment }),

  applyCapture: (capture) => set({ capture }),

  applyStageLease: (stageLease) => set({ stageLease }),

  closeTurn: (closed) => set((state) => state.assignment?.assignmentId === closed.assignmentId
    && state.assignment.responseTurnId === closed.responseTurnId
    ? { assignment: null, capture: null }
    : state),

  applyMode: ({ mode, reason }) =>
    set((s) => ({
      mode,
      modeReason: reason,
      transcript: appendTranscript(s.transcript, 'system', `mode → ${mode} (${reason})`),
    })),

  applySpeech: ({ text, turnId }) => {
    const { text: clean } = scrubActTokens(text)
    set((s) => ({
      speechSubtitle: clean,
      currentTurnId: turnId,
      avatar: {
        ...s.avatar,
      },
      transcript: appendTranscript(s.transcript, 'teacher', clean),
    }))
  },

  startSpeech: (turnId) => set({
    currentTurnId: turnId,
    speechSubtitle: '',
    speechLifecycle: { speechTurnId: turnId, status: 'queued' },
  }),

  updateSpeechText: (turnId, text) =>
    set((s) => s.currentTurnId === turnId ? { speechSubtitle: scrubActTokens(text).text } : s),

  finishSpeechText: (turnId, text) =>
    set((s) => ({
      transcript: appendTranscript(s.transcript, 'teacher', scrubActTokens(text).text),
      ...(s.currentTurnId === turnId ? { speechSubtitle: scrubActTokens(text).text } : {}),
    })),

  cancelSpeech: (turnId) =>
    set((s) =>
      s.currentTurnId && s.currentTurnId !== turnId
        ? s
        : {
            speechSubtitle: '',
            currentTurnId: null,
            speechLifecycle: { speechTurnId: turnId, status: 'terminal' },
            avatar: { ...s.avatar, speaking: false, mouthOpen: 0 },
          },
    ),

  applyAct: (act) =>
    set((s) => ({
      avatar: {
        ...s.avatar,
        emotion: emotionName(act) ?? s.avatar.emotion,
        intensity: emotionIntensity(act),
        motion: act.motion ?? s.avatar.motion,
      },
    })),

  setSpeaking: (speaking) =>
    set((s) => ({
      avatar: { ...s.avatar, speaking, mouthOpen: speaking ? s.avatar.mouthOpen : 0 },
    })),

  setMouthOpen: (value) =>
    set((s) => (s.avatar.mouthOpen === value ? s : { avatar: { ...s.avatar, mouthOpen: value } })),

  noteEvent: (event) => set({ lastEventAt: event.ts || Date.now() }),

  log: (kind, text) => set((s) => ({ transcript: appendTranscript(s.transcript, kind, text) })),
}))

// ── selectors ────────────────────────────────────────────────────────────

/** Overlay wins; `speech.say` fills in when the server sent no subtitle. */
export const selectSubtitle = (s: ClassroomState): string =>
  s.overlaySubtitle || s.speechSubtitle

export const selectStudentName = (s: ClassroomState): string | undefined =>
  s.scene?.overlay?.studentName

export const selectListening = (s: ClassroomState): boolean =>
  s.scene?.overlay?.listening === true

/** PROTOCOL.md §7: the badge is shown only in DEGRADED / OFFLINE. The scene
 *  overlay is authoritative; `mode.changed` is the fallback for a stale scene. */
export const selectModeBadge = (s: ClassroomState): Exclude<Mode, 'FULL'> | undefined =>
  s.scene?.overlay?.modeBadge ?? (s.mode === 'FULL' ? undefined : s.mode)

export const useSubtitle = () => useClassroom(selectSubtitle)
export const useModeBadge = () => useClassroom(selectModeBadge)

/** Correlation is server-issued authority; a board without it is display-only. */
export function currentResponseCorrelation(): ResponseCorrelation | null {
  const assignment = useClassroom.getState().assignment
  if (!assignment || assignment.expiresAt <= Date.now()) return null
  return {
    assignmentId: assignment.assignmentId,
    responseTurnId: assignment.responseTurnId,
  }
}
