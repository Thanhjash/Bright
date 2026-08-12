/**
 * Conservative energy endpointing for the fixed answer station.
 *
 * This is intentionally not presented as voice activity detection.  A child
 * presses Ready to bind the physical turn to Core's assignment; this detector
 * only rejects digital silence/isolated noise and stops a recording after the
 * speaker has become quiet.  faster-whisper remains responsible for trimming
 * the submitted clip and recognising speech.
 */

export type EnergyCaptureOutcome = 'speech' | 'no_speech' | 'noise_only'
export type EndpointReason = 'end_silence' | 'max_duration' | 'start_deadline'

export interface EndpointResult {
  outcome: EnergyCaptureOutcome
  reason: EndpointReason
  durationMs: number
  speechMs: number
  peak: number
}

export interface EndpointConfig {
  /** Calibrated 0..1 meter value while the answer station is quiet. */
  noiseFloor: number
  /** Sustained energy required before a take is considered speech-like. */
  onsetMs: number
  /** Minimum active duration before trailing silence may close the take. */
  minSpeechMs: number
  /** Quiet tail that ends a speech-like take. */
  endSilenceMs: number
  /** Absolute take cap supplied by Core. */
  maxDurationMs: number
}

const DEFAULT_CONFIG: EndpointConfig = {
  noiseFloor: 0.012,
  onsetMs: 180,
  minSpeechMs: 320,
  endSilenceMs: 800,
  maxDurationMs: 8_000,
}

export class ConservativeEndpointDetector {
  readonly config: EndpointConfig

  #startedAt: number | null = null
  #candidateAt: number | null = null
  #speechAt: number | null = null
  #lastActiveAt: number | null = null
  #sawNoise = false
  #peak = 0
  #terminal: EndpointResult | null = null

  constructor(config: Partial<EndpointConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  /** True only after energy has remained active for the conservative onset. */
  get hasSpeech(): boolean {
    return this.#speechAt !== null
  }

  /**
   * Feed the current meter level and a monotonic timestamp. Returns once.
   */
  sample(level: number, nowMs: number): EndpointResult | null {
    if (this.#terminal)
      return this.#terminal
    if (this.#startedAt === null)
      this.#startedAt = nowMs

    const clean = Number.isFinite(level) ? Math.max(0, Math.min(1, level)) : 0
    this.#peak = Math.max(this.#peak, clean)
    const threshold = Math.max(0.035, this.config.noiseFloor * 2.8 + 0.008)
    const active = clean >= threshold

    if (active) {
      this.#sawNoise = true
      this.#lastActiveAt = nowMs
      if (this.#candidateAt === null)
        this.#candidateAt = nowMs
      if (this.#speechAt === null && nowMs - this.#candidateAt >= this.config.onsetMs)
        this.#speechAt = this.#candidateAt
    }
    else if (this.#speechAt === null) {
      // An isolated bump is noise, not the beginning of an utterance.
      this.#candidateAt = null
    }

    const elapsed = nowMs - this.#startedAt
    if (elapsed >= this.config.maxDurationMs)
      return this.#finish(this.#speechAt === null ? this.#emptyOutcome() : 'speech', 'max_duration', nowMs)

    if (
      this.#speechAt !== null
      && this.#lastActiveAt !== null
      && this.#lastActiveAt - this.#speechAt >= this.config.minSpeechMs
      && nowMs - this.#lastActiveAt >= this.config.endSilenceMs
    ) {
      return this.#finish('speech', 'end_silence', nowMs)
    }

    return null
  }

  /**
   * Close a take whose Core-issued *speech onset* window has expired.
   * Once onset is established this deadline no longer applies; trailing
   * silence or maxDuration closes the take instead.
   */
  deadline(nowMs: number): EndpointResult | null {
    if (this.#terminal)
      return this.#terminal
    if (this.#speechAt !== null)
      return null
    return this.#finish(this.#emptyOutcome(), 'start_deadline', nowMs)
  }

  #emptyOutcome(): Exclude<EnergyCaptureOutcome, 'speech'> {
    return this.#sawNoise ? 'noise_only' : 'no_speech'
  }

  #finish(outcome: EnergyCaptureOutcome, reason: EndpointReason, nowMs: number): EndpointResult {
    const started = this.#startedAt ?? nowMs
    this.#terminal = {
      outcome,
      reason,
      durationMs: Math.max(0, nowMs - started),
      speechMs: this.#speechAt === null || this.#lastActiveAt === null
        ? 0
        : Math.max(0, this.#lastActiveAt - this.#speechAt),
      peak: this.#peak,
    }
    return this.#terminal
  }
}
