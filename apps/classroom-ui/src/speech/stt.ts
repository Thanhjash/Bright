/**
 * Speech-to-text — the other half of `speakingDriver.ts`.
 *
 *     mic → Blob → POST /audio/transcriptions (multipart, field `file`)
 *                → { text, confidence }
 *
 * The service is Whisper `small.en` through faster-whisper. **It costs ~3.4 s a
 * call regardless of how long the child spoke**, because Whisper always
 * processes a 30-second window: a one-second "yes" and a twenty-second sentence
 * cost the same. That single fact drives the whole UX around it — see
 * `useVoiceInput.ts`. It also means batching is free and chunking is pure loss,
 * so this module deliberately sends ONE request per utterance.
 *
 * Every failure path here throws a `SttError` carrying a sentence a facilitator
 * can act on. Nothing is swallowed: a silent no-op in front of a class looks
 * exactly like a broken product.
 */
import { SPEECH_URL } from '../lib/env'

export type SttFailure =
  /** the service could not be reached at all — down, or a CORS refusal */
  | 'unreachable'
  /** it answered, but not with a transcript */
  | 'rejected'
  /** nobody spoke, or the microphone heard nothing */
  | 'empty'

export class SttError extends Error {
  readonly failure: SttFailure
  constructor(failure: SttFailure, message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'SttError'
    this.failure = failure
  }
}

export interface Transcript {
  text: string
  /** Which language the decoder settled on. Not a score -- the label itself.
   *  A beginner falling back to their home language is the clearest "I am
   *  lost" signal a classroom has, and the room used to discard it here. */
  language: string | null
  /** 0…1 */
  confidence: number
  /** what the service reported spending, in ms */
  serviceMs: number
  queueMs: number
  inferMs: number
  noSpeechProbability: number
}

/**
 * An Opus-encoded clip of digital silence is a few hundred bytes however long it
 * runs, so this is a SILENCE test, not a duration test — a muted or unplugged
 * microphone records a perfectly valid file that Whisper transcribes to "".
 * Catching it here saves 3.4 s of pointless waiting and names the real cause.
 * Duration is checked separately, by the caller, which is the only place that
 * knows how long the button was held.
 */
const MIN_BYTES = 1200
const NO_SPEECH_THRESHOLD = 0.6

/**
 * Current provider-neutral service response. Confidence and no-speech values
 * are conservative heuristics until calibrated on consented child-room data.
 */
interface TranscriptionResponse {
  text?: unknown
  language?: unknown
  ms?: unknown
  confidence?: unknown
  avgLogprob?: unknown
  languageProbability?: unknown
  noSpeechProbability?: unknown
  queueMs?: unknown
  inferMs?: unknown
}

/**
 * `languageProbability` is deliberately NOT used: it scores "was this English",
 * not "did I hear this right", and it is 1.0 for every English utterance — zero
 * signal wearing a confidence-shaped hat. Core consumes the calibrated field
 * conservatively; missing confidence maps to zero rather than permission to pass.
 */
function readConfidence(body: TranscriptionResponse): number {
  if (typeof body.confidence === 'number' && Number.isFinite(body.confidence))
    return clamp01(body.confidence)
  // faster-whisper's avg_logprob is a mean log-probability per token; e^x maps
  // it back into 0…1 with the right ordering.
  if (typeof body.avgLogprob === 'number' && Number.isFinite(body.avgLogprob))
    return clamp01(Math.exp(body.avgLogprob))
  // Missing calibration is uncertainty, never permission to mark a child
  // correct. Core's threshold will turn this into `near` at best.
  return 0
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}

export interface TranscribeOptions {
  signal?: AbortSignal
  /**
   * Pin the decoder to one language instead of letting it detect.
   *
   * Used for the second and later phrases of a sentence, taken from what the
   * first phrase came back as. Two effects: it skips a whole `detect_language`
   * pass per phrase (the service's own header measures forcing at ~35% faster),
   * and it stops one sentence flapping between `en` and `vi` halfway through.
   */
  language?: string | null
  /**
   * Return an empty transcript instead of throwing when nothing was heard.
   *
   * A phrase that turns out to be a breath is ordinary and must not break the
   * chain of phrases around it. A whole UTTERANCE that turns out to be nothing
   * is still an error, so the default is unchanged.
   */
  allowEmpty?: boolean
}

/**
 * Transcribe one utterance, or one phrase of one.
 *
 * @throws {SttError} on every failure — unless `allowEmpty`, which downgrades
 *   "nothing was heard" to an empty result.
 */
export async function transcribe(
  audio: Blob,
  options: AbortSignal | TranscribeOptions = {},
): Promise<Transcript> {
  // Historically the second argument was the signal itself; keep that working.
  const opts: TranscribeOptions =
    options instanceof AbortSignal ? { signal: options } : options
  const { signal, language, allowEmpty } = opts

  if (audio.size < MIN_BYTES) {
    if (allowEmpty) return emptyTranscript(language ?? null)
    throw new SttError(
      'empty',
      'No sound reached the microphone. Check it is not muted, then try again.',
    )
  }

  const form = new FormData()
  // The field name is `file` — that is the service's contract, not a convention.
  form.append('file', audio, `utterance.${extensionFor(audio.type)}`)
  if (language) form.append('language', language)

  let res: Response
  try {
    res = await fetch(`${SPEECH_URL}/audio/transcriptions`, {
      method: 'POST',
      body: form,
      ...(signal ? { signal } : {}),
    })
  } catch (cause) {
    if (signal?.aborted) throw cause
    throw new SttError(
      'unreachable',
      `Could not reach the speech service at ${SPEECH_URL}. Is it running?`,
      { cause },
    )
  }

  if (!res.ok) {
    const detail = (await res.text().catch(() => '')).slice(0, 200)
    throw new SttError(
      'rejected',
      `Speech service answered ${res.status}${detail ? ` — ${detail}` : ''}`,
    )
  }

  let body: TranscriptionResponse
  try {
    body = (await res.json()) as TranscriptionResponse
  } catch (cause) {
    throw new SttError('rejected', 'Speech service sent something that was not JSON.', { cause })
  }

  const text = typeof body.text === 'string' ? body.text.trim() : ''
  const noSpeechProbability =
    typeof body.noSpeechProbability === 'number'
      ? clamp01(body.noSpeechProbability)
      : 0
  if (noSpeechProbability >= NO_SPEECH_THRESHOLD) {
    if (allowEmpty) return emptyTranscript(readLanguage(body), noSpeechProbability)
    throw new SttError(
      'empty',
      'No reliable speech was detected. Move closer to the microphone and try again.',
    )
  }
  if (!text) {
    if (allowEmpty) return emptyTranscript(readLanguage(body), noSpeechProbability)
    throw new SttError('empty', 'Nothing was heard. Check the microphone and try again.')
  }

  return {
    text,
    language: readLanguage(body),
    confidence: readConfidence(body),
    serviceMs: typeof body.ms === 'number' ? body.ms : 0,
    queueMs: typeof body.queueMs === 'number' ? body.queueMs : 0,
    inferMs: typeof body.inferMs === 'number' ? body.inferMs : 0,
    noSpeechProbability,
  }
}

/** Cosmetic — the service decodes from the bytes, not the name. */
function extensionFor(mime: string): string {
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4')) return 'mp4'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

function readLanguage(body: TranscriptionResponse): string | null {
  return typeof body.language === 'string' && body.language ? body.language : null
}

/** A phrase that carried no words. Not an error, and not a result either. */
function emptyTranscript(language: string | null, noSpeechProbability = 1): Transcript {
  return {
    text: '',
    language,
    confidence: 0,
    serviceMs: 0,
    queueMs: 0,
    inferMs: 0,
    noSpeechProbability,
  }
}
