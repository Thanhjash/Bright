import { describe, expect, it, vi } from 'vitest'

import { createWebAudioBackend } from './audio-backend'

function until(predicate: () => boolean, label: string, timeoutMs = 3000) {
  return new Promise<void>((resolve, reject) => {
    const deadline = Date.now() + timeoutMs
    const check = () => {
      if (predicate()) {
        resolve()
        return
      }
      if (Date.now() >= deadline) {
        reject(new Error(`timed out waiting for: ${label}`))
        return
      }
      setTimeout(check, 5)
    }
    check()
  })
}

describe('createWebAudioBackend', () => {
  it('acknowledges playback only after AudioBufferSourceNode.start and finishes on onended', async () => {
    const timeline: string[] = []
    const source = {
      buffer: null as AudioBuffer | null,
      onended: null as ((event: Event) => void) | null,
      connect: vi.fn(),
      disconnect: vi.fn(),
      start: vi.fn(() => timeline.push('source.start')),
      stop: vi.fn(),
    }
    const gain = {
      gain: { value: 0 },
      connect: vi.fn(),
      disconnect: vi.fn(),
    }
    const context = {
      state: 'running',
      currentTime: 42.25,
      destination: {} as AudioDestinationNode,
      createGain: vi.fn(() => gain),
      createBufferSource: vi.fn(() => source),
      decodeAudioData: vi.fn(),
      resume: vi.fn(),
      close: vi.fn(),
    } as unknown as AudioContext
    const backend = createWebAudioBackend({ audioContext: context })
    let settled = false
    const playing = backend.play({} as AudioBuffer, new AbortController().signal, {
      onStarted: ({ audioContextTime }) => timeline.push(`started:${audioContextTime}`),
    }).then(() => {
      settled = true
      timeline.push('play.resolved')
    })

    await until(() => source.start.mock.calls.length === 1, 'source start')
    expect(timeline).toEqual(['source.start', 'started:42.25'])
    expect(settled).toBe(false)

    timeline.push('source.onended')
    source.onended?.(new Event('ended'))
    await playing

    expect(timeline).toEqual([
      'source.start',
      'started:42.25',
      'source.onended',
      'play.resolved',
    ])
  })

  it('does not acknowledge playback when source.start throws', async () => {
    const source = {
      buffer: null as AudioBuffer | null,
      onended: null as ((event: Event) => void) | null,
      connect: vi.fn(),
      disconnect: vi.fn(),
      start: vi.fn(() => { throw new Error('output unavailable') }),
      stop: vi.fn(),
    }
    const context = {
      state: 'running',
      currentTime: 42.25,
      destination: {} as AudioDestinationNode,
      createGain: vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn(), disconnect: vi.fn() })),
      createBufferSource: vi.fn(() => source),
      decodeAudioData: vi.fn(),
      resume: vi.fn(),
      close: vi.fn(),
    } as unknown as AudioContext
    const onStarted = vi.fn()
    const backend = createWebAudioBackend({ audioContext: context })

    await expect(backend.play({} as AudioBuffer, new AbortController().signal, { onStarted })).rejects.toThrow('output unavailable')
    expect(onStarted).not.toHaveBeenCalled()
    expect(source.disconnect).toHaveBeenCalledOnce()
  })
})
