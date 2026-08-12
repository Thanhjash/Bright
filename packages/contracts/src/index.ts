/**
 * Bright wire contracts. Mirror of PROTOCOL.md.
 * Python mirror: packages/contracts/python/bright_contracts/__init__.py
 * Change PROTOCOL.md first, then both mirrors.
 */

export const PROTOCOL_VERSION = 2 as const

// ─────────────────────────── Event envelope ───────────────────────────

export interface Event<T = unknown> {
  v: typeof PROTOCOL_VERSION
  type: EventType
  seq: number
  stateVersion: number
  ts: number
  payload: T
}

export type EventType =
  // server → client
  | 'scene.update'
  | 'scene.snapshot'
  | 'speech.say'
  | 'speech.turn.started'
  | 'speech.text.delta'
  | 'speech.turn.ended'
  | 'speech.cancel'
  | 'speech.barge_in.ack'
  | 'avatar.act'
  | 'lesson.position'
  | 'lesson.started'
  | 'student.response.accepted'
  | 'mode.changed'
  | 'error'
  /** §9.8 liveness. Consumes no `seq`, never bumps `stateVersion`. */
  | 'heartbeat'
  // client → server
  | 'client.hello'
  | 'interaction.choice'
  | 'interaction.point'
  | 'interaction.drag'
  | 'control.command'
  | 'lesson.start'
  | 'student.speech.final'
  | 'speech.playback.started'
  | 'speech.playback.finished'
  | 'speech.barge_in'
  | 'heartbeat.ack'

export type Mode = 'FULL' | 'DEGRADED' | 'OFFLINE'

export interface SceneSnapshotPayload { scene: Scene; lesson: LessonPosition }
export interface SpeechSayPayload {
  text: string
  audioAsset?: string
  turnId: string
  conversationId?: string
  replyToUtteranceId?: string
}
export type SpeechBehavior = 'queue' | 'interrupt' | 'replace'
export type SpeechSource = 'authored' | 'agent' | 'system'
export interface SpeechTurnStartedPayload {
  speechTurnId: string
  behavior: SpeechBehavior
  source: SpeechSource
  conversationTurnId: string
  activityId?: string
  activityGeneration?: number
  audioAsset?: string
}
export interface SpeechTextDeltaPayload { speechTurnId: string; delta: string }
export interface SpeechTurnEndedPayload {
  speechTurnId: string
  status: 'completed' | 'cancelled' | 'error'
  reason?: string
}
export interface SpeechCancelPayload { speechTurnId: string; reason?: string }
export interface SpeechBargeInPayload {
  requestId: string
  speechTurnId: string
  activityId: string
  activityGeneration: number
}
export interface SpeechBargeInAckPayload {
  requestId: string
  speechTurnId: string
  accepted: boolean
  reason?: string
}
export interface SpeechPlaybackStartedPayload { speechTurnId: string }
export interface SpeechPlaybackFinishedPayload {
  speechTurnId: string
  status: 'completed' | 'cancelled' | 'failed'
  reason?: string
  metrics?: Record<string, number>
}
export interface ModeChangedPayload { mode: Mode; reason: string }
export interface ErrorPayload { code: string; message: string }
export interface HeartbeatPayload { ts: number }

export interface ClientHelloPayload { role: 'stage' | 'control'; stateVersion?: number }
export interface InteractionChoicePayload { optionId: string; studentId?: string }
export interface InteractionPointPayload { targetId: string; x: number; y: number }
export interface InteractionDragPayload { fromId: string; toId: string }
export interface StudentSpeechFinalPayload {
  text: string
  studentId?: string
  confidence: number
  utteranceId: string
  activityId: string
  activityGeneration: number
}

export interface StudentResponseAcceptedPayload {
  utteranceId: string
  outcome: 'correct' | 'near' | 'wrong' | 'silence' | 'timeout' | 'rejected'
}

export interface LessonStartPayload {
  requestId: string
  index?: number
  studentId?: string
  studentName?: string
}

export interface LessonStartedPayload {
  requestId: string
  sessionId: string
  conversationId: string
  lessonId: string
  studentId?: string
  index: number
  stateVersion: number
}

export type ControlCommand =
  | 'pause' | 'resume' | 'skip' | 'repeat' | 'back' | 'takeover'
export interface ControlCommandPayload { cmd: ControlCommand; arg?: string }

// ───────────────────────────────── Scene ─────────────────────────────────

export type SceneKind =
  | 'idle' | 'text' | 'image' | 'video' | 'vocabulary' | 'choice'
  | 'matching' | 'sentence_builder' | 'pronunciation' | 'roleplay' | 'explore'

export interface SceneOverlay {
  subtitle?: string
  studentName?: string
  listening?: boolean
  modeBadge?: Exclude<Mode, 'FULL'>
}

export interface Scene {
  v: typeof PROTOCOL_VERSION
  stateVersion: number
  kind: SceneKind
  props: SceneProps
  overlay?: SceneOverlay
}

/** `asset://<id>` — resolved by core at GET /assets/<id>. Never a filesystem path. */
export type AssetRef = string

export interface MediaItem { id: string; text?: string; asset?: AssetRef; audioAsset?: AssetRef }

export interface IdleProps {}
export interface TextProps { text: string; size?: 'sm' | 'md' | 'lg' | 'xl' }
export interface ImageProps { asset: AssetRef; caption?: string }
export interface VideoProps { asset: AssetRef; caption?: string; autoplay?: boolean }
export interface VocabularyProps {
  items: MediaItem[]
  interaction: 'none' | 'point' | 'tap'
  highlightId?: string
}
export interface ChoiceProps {
  prompt: string
  options: MediaItem[]
  /** present only after an answer has been given */
  revealed?: { correctId: string; chosenId?: string }
}
export interface MatchingProps {
  left: MediaItem[]
  right: MediaItem[]
  solved: Array<[string, string]>
}
export interface SentenceBuilderProps {
  tokens: Array<{ id: string; text: string }>
  placed: string[]
  target?: string
}
export interface PronunciationProps {
  word: string
  phonemes: Array<{ symbol: string; status: 'pending' | 'good' | 'retry' }>
}
export interface RoleplayProps {
  environment: string
  aiRole: string
  studentRole: string
  targetPhrases: string[]
}
export interface ExploreProps {
  topic: string
  nodes: Array<{ id: string; label: string; asset?: AssetRef }>
  focusId?: string
}

export type SceneProps =
  | IdleProps | TextProps | ImageProps | VideoProps | VocabularyProps
  | ChoiceProps | MatchingProps | SentenceBuilderProps | PronunciationProps
  | RoleplayProps | ExploreProps

// ───────────────────────────── Lesson ─────────────────────────────

export interface LessonPosition {
  lessonId: string
  classId: string
  activityIndex: number
  activityCount: number
  stage: string
  activityId: string
  activityGeneration: number
  currentStudentId?: string
}

export interface Narration {
  text: string
  /** pre-rendered at authoring time. Present ⇒ skip live TTS. */
  audioAsset?: AssetRef
  act?: ActPayload
}

export type ExpectKind = 'choice' | 'point' | 'drag' | 'speech' | 'none'
export interface Expect {
  kind: ExpectKind
  correct?: string | string[]
  /** near-miss transcripts → outcome 'near' */
  acceptFuzzy?: string[]
}

export type BranchOn = 'correct' | 'near' | 'wrong' | 'silence' | 'timeout' | 'always'
export interface Branch {
  on: BranchOn
  goto: string
  narration?: Narration[]
}

export interface Activity {
  id: string
  scene: SceneKind
  props: SceneProps
  narration?: Narration[]
  durationS?: number
  expect?: Expect
  branches?: Branch[]
}

export interface LessonRun {
  v: typeof PROTOCOL_VERSION
  lessonId: string
  classId: string
  title: string
  focus: string[]
  review: string[]
  studentsToCheck: string[]
  activities: Activity[]
  mediaManifest: AssetRef[]
}

// ─────────────────────────── ACT tokens ───────────────────────────

export const EMOTIONS = [
  'happy', 'sad', 'angry', 'think', 'surprised',
  'awkward', 'question', 'curious', 'neutral',
] as const
export type Emotion = typeof EMOTIONS[number]

/** Live2D motion group per emotion. Note: neutral → 'Idle', not 'Neutral'. */
export const EMOTION_MOTION_GROUP: Record<Emotion, string> = {
  happy: 'Happy', sad: 'Sad', angry: 'Angry', think: 'Think',
  surprised: 'Surprise', awkward: 'Awkward', question: 'Question',
  curious: 'Curious', neutral: 'Idle',
}

export interface ActPayload {
  emotion?: Emotion | { name: Emotion; intensity: number }
  /** free-form Live2D motion group name; ignored on VRM */
  motion?: string
}

export const TAG_OPEN = '<|'
export const TAG_CLOSE = '|>'
/** Retain this many trailing chars when scanning, so a tag split across
 *  two SSE chunks never leaks as spoken text. Do not lower. */
export const TAG_TAIL_RETAIN = 5

// ───────────────────────── Agent boundary ─────────────────────────

export interface AvailableAction {
  id: string
  label: string
  params?: string[]
}

/**
 * What actually happened, as graded by core. The observable subset of
 * `BranchOn` — `always` is a branch directive, not an observed outcome.
 *
 * `silence` and `timeout` belong here: a child who says nothing needs a
 * different response from a child who answers wrongly. An earlier version
 * omitted them, making it impossible to tell the agent a student had gone
 * quiet — caught the first time a silence was fed through a live turn.
 */
export type Outcome = 'correct' | 'near' | 'wrong' | 'silence' | 'timeout'

export interface TurnContext {
  stateVersion: number
  lesson: LessonPosition
  scene: Scene
  student?: { id: string; name: string; skills: Record<string, number> }
  lastInteraction?: { kind: string; detail: string; outcome?: Outcome }
  availableActions: AvailableAction[]
  recalled?: Array<{ text: string; when: string }>
}

export type AgentEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'act'; act: ActPayload }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; ok: boolean; result?: unknown }
  | { type: 'done'; reason: 'complete' | 'error' | 'cancelled' }
