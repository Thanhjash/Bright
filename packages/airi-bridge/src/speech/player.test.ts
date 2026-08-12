/**
 * The PROTOCOL.md §6 invariants, exercised through a fake audio backend.
 *
 * Every test here is about ORDER, not about sound. That is deliberate: the ordering
 * rules are what break audibly and are what a Node test can actually prove.
 */

import type { ActSignal } from '../act'
import type { AudioBackend } from './audio-backend'

import { describe, expect, it, vi } from 'vitest'

import { createSpeechPlayer } from './player'

interface FakeAudio {
  text: string
}

interface FakeBackend extends AudioBackend<unknown> {
  played: string[]
  mouthOpen: number
}

/**
 * Records what was played, in the order it was played.
 *
 * `playDurationMs` is deliberately non-zero so out-of-order TTS completion has a real
 * chance to reorder playback if the sequence gate is broken.
 */
function createFakeBackend(playDurationMs = 1): FakeBackend {
  const played: string[] = []
  let muted = false

  const backend: FakeBackend = {
    played,
    mouthOpen: 0,
    async decode(bytes) {
      return { text: new TextDecoder().decode(bytes) } satisfies FakeAudio
    },
    async play(audio, signal) {
      // A muted backend MUST still take the full duration. Short-circuiting here is
      // exactly the bug PROTOCOL.md §6.4 forbids.
      if (signal.aborted)
        return
      played.push((audio as FakeAudio).text)
      await new Promise(resolve => setTimeout(resolve, playDurationMs))
    },
    getMouthOpen: () => backend.mouthOpen,
    setMuted: (next) => {
      muted = next
    },
    isMuted: () => muted,
    dispose: () => {},
  }

  return backend
}

function encode(text: string): ArrayBuffer {
  const bytes = new TextEncoder().encode(text)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

/** Waits until `predicate` holds, or fails the test. */
async function until(predicate: () => boolean, label: string, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate())
      return
    await new Promise(resolve => setTimeout(resolve, 5))
  }
  throw new Error(`timed out waiting for: ${label}`)
}

describe('createSpeechPlayer — playback order (PROTOCOL.md §6.2)', () => {
  it('plays segments in TEXT order even when TTS finishes out of order', async () => {
    const backend = createFakeBackend()
    // Deliberately invert latency: later segments finish first.
    const delays = [80, 60, 40, 20, 1]
    let call = 0

    const player = createSpeechPlayer({
      audio: backend,
      tts: async (text) => {
        const delay = delays[Math.min(call++, delays.length - 1)]
        await new Promise(resolve => setTimeout(resolve, delay))
        return encode(text)
      },
    })

    const turn = player.speak()
    await turn.push('One. Two. Three. Four. Five.')
    await turn.end()

    await until(() => backend.played.length >= 5, 'five segments played')

    expect(backend.played.map(text => text.trim())).toEqual([
      'One.',
      'Two.',
      'Three.',
      'Four.',
      'Five.',
    ])
  })

  it('advances past a failed segment instead of deadlocking', async () => {
    const backend = createFakeBackend()

    const player = createSpeechPlayer({
      audio: backend,
      onError: () => {},
      tts: async (text) => {
        if (text.includes('Two'))
          throw new Error('provider exploded')
        return encode(text)
      },
    })

    const turn = player.speak()
    await turn.push('One. Two. Three.')
    await turn.end()

    await until(() => backend.played.length >= 2, 'the segments after the failure played')

    const played = backend.played.map(text => text.trim())
    expect(played).toContain('One.')
    expect(played).toContain('Three.')
    expect(played).not.toContain('Two.')
    // Order is still preserved around the hole.
    expect(played.indexOf('One.')).toBeLessThan(played.indexOf('Three.'))
  })

  it('advances past a segment the provider returns nothing for', async () => {
    const backend = createFakeBackend()
    const player = createSpeechPlayer({
      audio: backend,
      tts: async text => (text.includes('Two') ? new ArrayBuffer(0) : encode(text)),
    })

    const turn = player.speak()
    await turn.push('One. Two. Three.')
    await turn.end()

    await until(() => backend.played.length >= 2, 'segments played')
    expect(backend.played.map(t => t.trim())).toEqual(['One.', 'Three.'])
  })
})

describe('createSpeechPlayer — special tokens (PROTOCOL.md §6.3)', () => {
  it('fires a special AFTER its segment audio finishes', async () => {
    const backend = createFakeBackend(20)
    const timeline: string[] = []

    const player = createSpeechPlayer({
      audio: backend,
      tts: async text => encode(text),
      onSegmentStart: segment => void timeline.push(`play:${segment.text.trim()}`),
      onSignal: signal => void timeline.push(`signal:${signal.kind}`),
    })

    const turn = player.speak()
    await turn.push('Well done.<|ACT {"emotion":"happy"}|> Next question.')
    await turn.end()

    await until(() => timeline.filter(e => e.startsWith('play:')).length >= 2, 'both segments played')
    await until(() => timeline.includes('signal:act'), 'the ACT signal fired')

    const playIndex = timeline.indexOf('play:Well done.')
    const signalIndex = timeline.indexOf('signal:act')
    const nextIndex = timeline.indexOf('play:Next question.')

    expect(playIndex).toBeGreaterThanOrEqual(0)
    // The emotion lands on the sentence it belongs to: after that sentence, and
    // before the following one.
    expect(signalIndex).toBeGreaterThan(playIndex)
    expect(signalIndex).toBeLessThan(nextIndex)
  })

  it('reports the emotion and its intensity from an ACT token', async () => {
    const backend = createFakeBackend()
    const onEmotion = vi.fn()

    const player = createSpeechPlayer({
      audio: backend,
      tts: async text => encode(text),
      onEmotion,
    })

    const turn = player.speak()
    await turn.push('Hmm.<|ACT {"emotion":{"name":"think","intensity":0.6}}|>')
    await turn.end()

    await until(() => onEmotion.mock.calls.length > 0, 'emotion dispatched')
    expect(onEmotion.mock.calls[0][0]).toBe('think')
    expect(onEmotion.mock.calls[0][1]).toBe(0.6)
  })

  it('reports DELAY without sleeping — the caller decides what to do', async () => {
    const backend = createFakeBackend()
    const onDelay = vi.fn()

    const player = createSpeechPlayer({
      audio: backend,
      tts: async text => encode(text),
      onDelay,
    })

    const started = Date.now()
    const turn = player.speak()
    await turn.push('Ready.<|DELAY 5|> Go.')
    await turn.end()

    await until(() => onDelay.mock.calls.length > 0, 'delay dispatched')
    expect(onDelay.mock.calls[0][0]).toBe(5)
    expect(Date.now() - started).toBeLessThan(2000) // it did NOT sleep 5s
  })

  it('never lets a token split across deltas reach the TTS', async () => {
    const backend = createFakeBackend()
    const spoken: string[] = []
    const signals: ActSignal[] = []

    const player = createSpeechPlayer({
      audio: backend,
      tts: async (text) => {
        spoken.push(text)
        return encode(text)
      },
      onSignal: signal => void signals.push(signal),
    })

    const turn = player.speak()
    // The token arrives in four pieces, cut at the worst places.
    await turn.push('Nice work<|A')
    await turn.push('CT {"emo')
    await turn.push('tion":"happy"}|')
    await turn.push('> Keep going.')
    await turn.end()

    await until(() => signals.length > 0, 'the signal fired')

    expect(spoken.join(' ')).not.toContain('<|')
    expect(spoken.join(' ')).not.toContain('ACT')
    expect(spoken.join(' ')).not.toContain('|>')
    expect(signals[0].kind).toBe('act')
  })
})

describe('createSpeechPlayer — muting (PROTOCOL.md §6.4)', () => {
  it('dispatches specials in the same order whether muted or not', async () => {
    async function run(muted: boolean) {
      const backend = createFakeBackend(10)
      const timeline: string[] = []

      const player = createSpeechPlayer({
        audio: backend,
        tts: async text => encode(text),
        onSegmentStart: segment => void timeline.push(`play:${segment.text.trim()}`),
        onSignal: signal => void timeline.push(`signal:${signal.raw}`),
      })
      player.setMuted(muted)

      const turn = player.speak()
      await turn.push('One.<|ACT {"emotion":"happy"}|> Two.<|ACT {"emotion":"neutral"}|>')
      await turn.end()

      await until(
        () => timeline.filter(e => e.startsWith('signal:')).length >= 2,
        `both signals fired (muted=${muted})`,
      )
      return timeline
    }

    const loud = await run(false)
    const silent = await run(true)

    // Muting changes the volume and nothing else: identical event sequence.
    expect(silent).toEqual(loud)
    expect(silent.filter(e => e.startsWith('signal:'))).toHaveLength(2)
  })

  it('still plays every segment when muted — mute is gain, never skip', async () => {
    const backend = createFakeBackend()
    const player = createSpeechPlayer({ audio: backend, tts: async text => encode(text) })
    player.setMuted(true)

    const turn = player.speak()
    await turn.push('One. Two. Three.')
    await turn.end()

    await until(() => backend.played.length >= 3, 'all segments played while muted')
    expect(backend.played.map(t => t.trim())).toEqual(['One.', 'Two.', 'Three.'])
    expect(player.isMuted()).toBe(true)
  })
})

describe('createSpeechPlayer — speaking state', () => {
  it('aborts in-flight TTS and reports the exact cancelled turn', async () => {
    const backend = createFakeBackend()
    const onTurnCancel = vi.fn()
    let receivedSignal: AbortSignal | undefined

    const player = createSpeechPlayer({
      audio: backend,
      onTurnCancel,
      tts: async (_text, _context, signal) => {
        receivedSignal = signal
        await new Promise<void>((resolve) => {
          signal.addEventListener('abort', () => resolve(), { once: true })
        })
        return new ArrayBuffer(0)
      },
    })

    const turn = player.speak({ turnId: 'speech-42' })
    await turn.push('This request should be cancelled.')
    const ending = turn.end()
    await until(() => receivedSignal !== undefined, 'TTS request started')
    turn.cancel('superseded')
    await ending

    await until(() => onTurnCancel.mock.calls.length === 1, 'turn cancellation reported')
    expect(receivedSignal?.aborted).toBe(true)
    expect(onTurnCancel).toHaveBeenCalledWith('speech-42', 'superseded')
    expect(backend.played).toEqual([])
  })

  it('reports speaking across the whole utterance, not per segment gap', async () => {
    const backend = createFakeBackend(10)
    const changes: boolean[] = []

    const player = createSpeechPlayer({
      audio: backend,
      tts: async text => encode(text),
      onSpeakingChange: speaking => void changes.push(speaking),
    })

    expect(player.isSpeaking()).toBe(false)

    const turn = player.speak()
    await turn.push('One. Two. Three.')
    await turn.end()

    await until(() => changes.length >= 2 && changes.at(-1) === false, 'speaking ended')

    // Exactly one transition each way, for the WHOLE utterance. Flapping between
    // segments would restart the lip-sync 200 ms release tail mid-sentence and make
    // the mouth stutter shut between clauses. [true, false] — nothing else passes.
    expect(changes).toEqual([true, false])
    expect(player.isSpeaking()).toBe(false)
  })

  it('passes getMouthOpen through from the backend without rescaling', () => {
    const backend = createFakeBackend()
    const player = createSpeechPlayer({ audio: backend, tts: async text => encode(text) })

    backend.mouthOpen = 0.7
    expect(player.getMouthOpen()).toBe(0.7)
    backend.mouthOpen = 0.35
    expect(player.getMouthOpen()).toBe(0.35)
  })
})

describe('createSpeechPlayer — chunking (PROTOCOL.md §6.1)', () => {
  it('emits the first two segments early via boost = 2', async () => {
    const backend = createFakeBackend()
    const requests: string[] = []

    const player = createSpeechPlayer({
      audio: backend,
      tts: async (text) => {
        requests.push(text)
        return encode(text)
      },
    })

    const turn = player.speak()
    // Short clauses that would NOT meet the 4-word minimum without the boost.
    await turn.push('Hi. Ok. Now let us look at the picture together carefully.')
    await turn.end()

    await until(() => requests.length >= 3, 'segments requested')
    expect(requests[0].trim()).toBe('Hi.')
    expect(requests[1].trim()).toBe('Ok.')
  })

  it('cancelling a turn stops further playback', async () => {
    const backend = createFakeBackend(50)
    const player = createSpeechPlayer({ audio: backend, tts: async text => encode(text) })

    const turn = player.speak()
    await turn.push('One. Two. Three. Four. Five. Six.')
    await turn.end()

    await until(() => backend.played.length >= 1, 'playback started')
    const atCancel = backend.played.length
    turn.cancel('test')

    await new Promise(resolve => setTimeout(resolve, 120))
    expect(backend.played.length).toBeLessThanOrEqual(atCancel + 1)
  })
})
