/**
 * MockBus — the `VITE_MOCK=1` driver.
 *
 * It implements the same `Bus` interface as `WsBus` and speaks the same
 * `Event<T>` envelopes, so every component downstream is bit-identical
 * between mock and live. It stands in for classroom-core: it owns the
 * position, grades the two interactive steps, honours control commands, and
 * replies to `client.hello` with a `scene.snapshot`.
 *
 * The UI still decides nothing. The mock decides — it is playing the server.
 */
import { PROTOCOL_VERSION } from '@contracts'
import type {
  ChoiceProps,
  Event,
  ExploreProps,
  LessonPosition,
  MatchingProps,
  Mode,
  Scene,
  SceneProps,
  SentenceBuilderProps,
  VocabularyProps,
} from '@contracts'
import { BusEmitter } from './emitter'
import { MOCK_LESSON, MOCK_STEPS, sceneFrom } from './fixtures'
import type {
  Bus,
  ClientEventMap,
  ClientEventType,
  ConnectionStatus,
  ServerEventMap,
  ServerEventType,
  ServerHandler,
  Unsubscribe,
} from './types'

const BOOT_MS = 350
const SAY_DELAY_MS = 240
const GRADE_DELAY_MS = 420
const AFTER_ANSWER_MS = 2200
/** §9.8 — the server's obligation, mocked, so /control reads the same in both modes. */
const HEARTBEAT_MS = 5_000

/**
 * `?step=<n>` jumps the fixture straight to an activity — the fast way to
 * work on, or demo, one particular scene kind. Mock mode only.
 */
function startIndex(): number {
  if (typeof location === 'undefined') return 0
  const raw = new URLSearchParams(location.search).get('step')
  const n = raw === null ? NaN : Number.parseInt(raw, 10)
  return Number.isFinite(n) ? Math.max(0, Math.min(MOCK_STEPS.length - 1, n)) : 0
}

export class MockBus implements Bus {
  readonly role: 'stage' | 'control'

  #emitter = new BusEmitter()
  #timers = new Set<ReturnType<typeof setTimeout>>()

  #seq = 0
  #stateVersion = 0
  #index = 0
  #paused = false
  #mode: Mode = 'FULL'
  #started = false
  #answered = false
  /**
   * A working copy of the current step's props.
   *
   * The mock is playing the server, so grading MUTATES scene props (a matched
   * pair, a placed token, a new explore focus). Writing that back into the
   * shared `MOCK_STEPS` fixture would make `repeat` replay an already-finished
   * board, so every `#goto` takes a fresh deep copy and the fixture stays
   * pristine.
   */
  #props: SceneProps = {}
  #beat: ReturnType<typeof setInterval> | null = null
  #status: ConnectionStatus = {
    state: 'closed',
    attempts: 0,
    retryInMs: 0,
    lastHeartbeatAt: 0,
    latencyMs: null,
    lastFrameAt: 0,
  }

  constructor(role: 'stage' | 'control') {
    this.role = role
  }

  // ── lifecycle ──────────────────────────────────────────────────────────

  connect(): void {
    if (this.#started) return
    this.#started = true
    this.#setStatus({
      state: 'mock',
      attempts: 0,
      retryInMs: 0,
      lastFrameAt: Date.now(),
      lastHeartbeatAt: Date.now(),
      latencyMs: 0,
    })
    // A mock link is a healthy link: beat like a compliant server would, so
    // the console's §9.8 readout is exercised with no backend at all.
    this.#beat = setInterval(() => {
      const now = Date.now()
      this.#setStatus({ lastHeartbeatAt: now, lastFrameAt: now, latencyMs: 0 })
    }, HEARTBEAT_MS)
    this.#emitter.emitReset('mock boot')
    this.#later(() => this.#goto(startIndex()), BOOT_MS)
  }

  close(): void {
    this.#started = false
    this.#clearTimers()
    if (this.#beat !== null) {
      clearInterval(this.#beat)
      this.#beat = null
    }
    this.#setStatus({ state: 'closed', attempts: 0, retryInMs: 0, latencyMs: null })
  }

  // ── inbound from the UI ────────────────────────────────────────────────

  send<K extends ClientEventType>(type: K, payload: ClientEventMap[K]): void {
    switch (type) {
      case 'client.hello':
        this.#later(() => this.#snapshot(), 40)
        break
      case 'control.command':
        this.#command((payload as ClientEventMap['control.command']).cmd)
        break
      case 'lesson.start': {
        const request = payload as ClientEventMap['lesson.start']
        const index = request.index ?? 0
        this.#goto(index)
        this.#later(() => this.#emit('lesson.started', {
          requestId: request.requestId,
          sessionId: `mock-session-${request.requestId}`,
          conversationId: `mock-conversation-${request.requestId}`,
          lessonId: MOCK_LESSON.lessonId,
          studentId: request.studentId,
          index,
          stateVersion: this.#stateVersion,
        }), 40)
        break
      }
      case 'interaction.choice':
        this.#gradeChoice((payload as ClientEventMap['interaction.choice']).optionId)
        break
      case 'interaction.point':
        this.#gradePoint((payload as ClientEventMap['interaction.point']).targetId)
        break
      case 'interaction.drag': {
        const p = payload as ClientEventMap['interaction.drag']
        this.#gradeDrag(p.fromId, p.toId)
        break
      }
      case 'student.speech.final': {
        const utteranceId = (payload as ClientEventMap['student.speech.final']).utteranceId
        this.#later(() => this.#emit('student.response.accepted', {
          utteranceId,
          outcome: 'rejected',
        }), 40)
        break
      }
      case 'speech.barge_in': {
        const request = payload as ClientEventMap['speech.barge_in']
        this.#later(() => this.#emit('speech.barge_in.ack', {
          requestId: request.requestId,
          speechTurnId: request.speechTurnId,
          accepted: true,
        }), 20)
        break
      }
      default:
        // Playback acknowledgements are observed but do not drive the fixture.
        break
    }
  }

  requestSnapshot(reason: string): void {
    this.#emitter.emitReset(reason)
    this.#snapshot()
  }

  // ── the mock "server" ──────────────────────────────────────────────────

  get #step() {
    return MOCK_STEPS[this.#index]
  }

  #lessonPosition(): LessonPosition {
    return {
      ...MOCK_LESSON,
      activityIndex: this.#index,
      activityCount: MOCK_STEPS.length,
      stage: this.#step.stage,
      activityId: this.#step.id,
      activityGeneration: this.#stateVersion,
    }
  }

  #scene(extraOverlay?: Scene['overlay']): Scene {
    const badge = this.#mode === 'FULL' ? undefined : this.#mode
    return sceneFrom({ ...this.#step, props: this.#props }, this.#stateVersion, {
      ...extraOverlay,
      ...(badge ? { modeBadge: badge } : {}),
    })
  }

  #goto(index: number): void {
    this.#clearTimers()
    this.#index = Math.max(0, Math.min(MOCK_STEPS.length - 1, index))
    this.#answered = false
    this.#props = structuredClone(MOCK_STEPS[this.#index].props)
    this.#stateVersion += 1

    this.#emit('scene.update', this.#scene())
    this.#emit('lesson.position', this.#lessonPosition())
    this.#speak()
    this.#armAdvance()
  }

  #speak(): void {
    const say = this.#step.say
    if (!say) return
    this.#later(() => {
      this.#emit('speech.say', { text: say, turnId: `mock-${this.#step.id}-${this.#stateVersion}` })
    }, SAY_DELAY_MS)
  }

  #armAdvance(): void {
    const hold = this.#step.holdMs
    if (!hold || this.#paused) return
    if (this.#index >= MOCK_STEPS.length - 1) return
    this.#later(() => this.#goto(this.#index + 1), hold)
  }

  #command(cmd: ClientEventMap['control.command']['cmd']): void {
    switch (cmd) {
      case 'pause':
        this.#paused = true
        this.#clearTimers()
        break
      case 'resume':
        this.#paused = false
        if (this.#mode !== 'FULL') this.#setMode('FULL', 'facilitator handed control back')
        this.#armAdvance()
        break
      case 'skip':
        this.#paused = false
        this.#goto(this.#index + 1)
        break
      case 'back':
        this.#paused = false
        this.#goto(this.#index - 1)
        break
      case 'repeat':
        this.#goto(this.#index)
        break
      case 'takeover':
        this.#paused = true
        this.#clearTimers()
        this.#setMode('DEGRADED', 'facilitator took over')
        break
    }
  }

  #setMode(mode: Mode, reason: string): void {
    this.#mode = mode
    this.#stateVersion += 1
    this.#emit('mode.changed', { mode, reason })
    // The badge lives on the scene overlay, so the scene is resent whole.
    this.#emit('scene.update', this.#scene())
  }

  #gradeChoice(optionId: string): void {
    const step = this.#step
    if (step.kind !== 'choice' || this.#answered) return
    this.#answered = true
    const props = this.#props as ChoiceProps
    const correctId = step.correct ?? props.options[0]?.id ?? ''
    const right = optionId === correctId

    this.#later(() => {
      this.#stateVersion += 1
      const revealedProps: ChoiceProps = {
        ...props,
        revealed: { correctId, chosenId: optionId },
      }
      this.#emit('scene.update', {
        v: PROTOCOL_VERSION,
        stateVersion: this.#stateVersion,
        kind: 'choice',
        props: revealedProps,
        overlay: this.#scene().overlay,
      })
      this.#emit('avatar.act', { emotion: right ? 'happy' : 'curious' })
      this.#emit('speech.say', {
        text: right ? 'Yes! That is a banana. Well done.' : 'Not quite — this one is the banana.',
        turnId: `mock-grade-${this.#stateVersion}`,
      })
      this.#later(() => this.#goto(this.#index + 1), AFTER_ANSWER_MS)
    }, GRADE_DELAY_MS)
  }

  /**
   * `interaction.drag` — matching and sentence_builder.
   *
   * Grading mirrors classroom-core's `grade()`: the candidates are `toId` and
   * the pair form `fromId>toId`, either of which may appear in `correct`.
   *
   * Where it deliberately differs: core allows exactly ONE graded answer per
   * activity, so a real matching activity ends on the first pair. The mock lets
   * the child finish all the pairs, because its job is to show the board
   * working end to end with no backend. It also does what core does not yet do
   * and sends back an updated `solved` / `placed` — the authoritative path the
   * board is written against.
   */
  #gradeDrag(fromId: string, toId: string): void {
    const step = this.#step
    const candidates = [toId, `${fromId}>${toId}`]
    const right = step.correct ? candidates.includes(step.correct) : true

    if (step.kind === 'matching') {
      const props = this.#props as MatchingProps
      const already = props.solved ?? []
      if (!right || already.some(([l, r]) => l === fromId || r === toId)) {
        this.#nudge(right, 'Try that one again.')
        return
      }
      const solved: Array<[string, string]> = [...already, [fromId, toId]]
      this.#props = { ...props, solved } satisfies MatchingProps
      this.#clearTimers()
      this.#later(() => {
        this.#stateVersion += 1
        this.#emit('scene.update', this.#scene())
        this.#emit('avatar.act', { emotion: 'happy' })
        const done = solved.length >= Math.min(props.left.length, props.right.length)
        this.#emit('speech.say', {
          text: done ? 'All matched. Excellent!' : 'Yes! That is a pair.',
          turnId: `mock-drag-${this.#stateVersion}`,
        })
        if (done) this.#later(() => this.#goto(this.#index + 1), AFTER_ANSWER_MS)
      }, GRADE_DELAY_MS)
      return
    }

    if (step.kind === 'sentence_builder') {
      const props = this.#props as SentenceBuilderProps
      const placed = props.placed ?? []
      if (placed.includes(fromId)) return
      const next = [...placed, fromId]
      this.#props = { ...props, placed: next } satisfies SentenceBuilderProps
      this.#clearTimers()
      this.#later(() => {
        this.#stateVersion += 1
        this.#emit('scene.update', this.#scene())
        const done = next.length >= props.tokens.length
        if (done) {
          this.#emit('avatar.act', { emotion: 'happy' })
          this.#emit('speech.say', {
            text: 'I would like an apple. Perfect!',
            turnId: `mock-built-${this.#stateVersion}`,
          })
          this.#later(() => this.#goto(this.#index + 1), AFTER_ANSWER_MS)
        }
      }, GRADE_DELAY_MS)
    }
  }

  /** A short spoken correction that does not advance the lesson. */
  #nudge(right: boolean, text: string): void {
    this.#later(() => {
      this.#emit('avatar.act', { emotion: right ? 'curious' : 'question' })
      this.#emit('speech.say', { text, turnId: `mock-nudge-${Date.now()}` })
    }, GRADE_DELAY_MS)
  }

  #gradePoint(targetId: string): void {
    const step = this.#step

    // `explore` is not graded: a child choosing what to look at cannot be
    // wrong. The tap moves the focus and that is the whole interaction.
    if (step.kind === 'explore') {
      const props = this.#props as ExploreProps
      if (!props.nodes.some((n) => n.id === targetId)) return
      this.#props = { ...props, focusId: targetId } satisfies ExploreProps
      this.#clearTimers()
      this.#stateVersion += 1
      this.#emit('scene.update', this.#scene())
      this.#emit('avatar.act', { emotion: 'curious' })
      this.#emit('speech.say', {
        text: `Good choice. Let us look at ${props.nodes.find((n) => n.id === targetId)?.label}.`,
        turnId: `mock-explore-${this.#stateVersion}`,
      })
      return
    }

    if (step.kind !== 'vocabulary' || this.#answered) return
    this.#answered = true
    const props = this.#props as VocabularyProps
    const right = targetId === (step.correct ?? props.items[0]?.id)

    this.#later(() => {
      this.#stateVersion += 1
      const highlighted: VocabularyProps = { ...props, highlightId: targetId }
      this.#emit('scene.update', {
        v: PROTOCOL_VERSION,
        stateVersion: this.#stateVersion,
        kind: 'vocabulary',
        props: highlighted,
        overlay: { ...this.#scene().overlay, listening: false },
      })
      this.#emit('avatar.act', { emotion: right ? 'happy' : 'curious' })
      this.#emit('speech.say', {
        text: right ? 'That is right! Apple.' : 'Almost — try again. Find the apple.',
        turnId: `mock-point-${this.#stateVersion}`,
      })
      if (right) this.#later(() => this.#goto(this.#index + 1), AFTER_ANSWER_MS)
      else this.#later(() => (this.#answered = false), 900)
    }, GRADE_DELAY_MS)
  }

  #snapshot(): void {
    this.#emit('scene.snapshot', { scene: this.#scene(), lesson: this.#lessonPosition() })
  }

  // ── plumbing ───────────────────────────────────────────────────────────

  #emit<K extends ServerEventType>(type: K, payload: ServerEventMap[K]): void {
    const event: Event<unknown> = {
      v: PROTOCOL_VERSION,
      type,
      seq: ++this.#seq,
      stateVersion: this.#stateVersion,
      ts: Date.now(),
      payload,
    }
    this.#emitter.emit(event)
  }

  #later(fn: () => void, ms: number): void {
    const t = setTimeout(() => {
      this.#timers.delete(t)
      fn()
    }, ms)
    this.#timers.add(t)
  }

  #clearTimers(): void {
    for (const t of this.#timers) clearTimeout(t)
    this.#timers.clear()
  }

  on<K extends ServerEventType>(type: K, handler: ServerHandler<K>): Unsubscribe {
    return this.#emitter.on(type, handler)
  }

  onAny(handler: (event: Event<unknown>) => void): Unsubscribe {
    return this.#emitter.onAny(handler)
  }

  onStatus(handler: (status: ConnectionStatus) => void): Unsubscribe {
    return this.#emitter.onStatus(handler)
  }

  onReset(handler: (reason: string) => void): Unsubscribe {
    return this.#emitter.onReset(handler)
  }

  status(): ConnectionStatus {
    return this.#status
  }

  #setStatus(patch: Partial<ConnectionStatus>): void {
    this.#status = { ...this.#status, ...patch }
    this.#emitter.emitStatus(this.#status)
  }
}
