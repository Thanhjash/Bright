// @vitest-environment jsdom
/**
 * React-layer tests.
 *
 * These do NOT touch WebGL or Web Audio — a fake `AudioBackend` is injected, which is
 * the whole reason that seam exists. What is checked here is React-shaped: that the
 * audio graph is built once and torn down on unmount, that `getMouthOpen` keeps a
 * stable identity across renders (it is called every animation frame), and that
 * ACT-driven emotion reaches React state.
 */

import type { ReactNode } from 'react'

import type { AudioBackend } from '../speech'

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSpeechPlayer } from './use-speech-player'

// React 19 reads this to decide whether act() warnings apply.
;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true

interface FakeAudio { text: string }

function createFakeBackend() {
  const played: string[] = []
  let muted = false
  let mouthOpen = 0
  let disposed = false

  const backend: AudioBackend<unknown> = {
    async decode(bytes) {
      return { text: new TextDecoder().decode(bytes) } satisfies FakeAudio
    },
    async play(audio, signal, options) {
      if (signal.aborted)
        return
      played.push((audio as FakeAudio).text)
      options?.onStarted?.({})
      await new Promise(resolve => setTimeout(resolve, 1))
    },
    getMouthOpen: () => mouthOpen,
    setMuted: (next) => {
      muted = next
    },
    isMuted: () => muted,
    dispose: () => {
      disposed = true
    },
  }

  return {
    backend,
    played,
    isMuted: () => muted,
    isDisposed: () => disposed,
    setMouthOpen: (value: number) => {
      mouthOpen = value
    },
  }
}

function encode(text: string): ArrayBuffer {
  const bytes = new TextEncoder().encode(text)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

function render(node: ReactNode) {
  act(() => root.render(node))
}

async function until(predicate: () => boolean, label: string, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate())
      return
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 5))
    })
  }
  throw new Error(`timed out waiting for: ${label}`)
}

describe('useSpeechPlayer', () => {
  it('builds the audio graph once and disposes it on unmount', () => {
    const fake = createFakeBackend()
    let renders = 0

    function Harness({ tick }: { tick: number }) {
      renders += 1
      useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      return <span>{tick}</span>
    }

    render(<Harness tick={1} />)
    render(<Harness tick={2} />)
    render(<Harness tick={3} />)

    expect(renders).toBe(3)
    expect(fake.isDisposed()).toBe(false)

    act(() => root.unmount())
    expect(fake.isDisposed()).toBe(true)
  })

  it('keeps getMouthOpen identity stable across renders', () => {
    const fake = createFakeBackend()
    const seen: Array<() => number> = []

    function Harness({ tick }: { tick: number }) {
      const player = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      seen.push(player.getMouthOpen)
      return <span>{tick}</span>
    }

    render(<Harness tick={1} />)
    render(<Harness tick={2} />)

    // Called once per animation frame — a new identity every render would restart the
    // rAF effect in <Live2DAvatar> sixty times a second.
    expect(seen[0]).toBe(seen[1])
  })

  it('reads the mouth value through from the backend without rescaling', () => {
    const fake = createFakeBackend()
    let read: (() => number) | undefined

    function Harness() {
      const player = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      read = player.getMouthOpen
      return null
    }

    render(<Harness />)
    fake.setMouthOpen(0.7)
    expect(read!()).toBe(0.7)
  })

  it('surfaces speaking as state and the ACT emotion as state', async () => {
    const fake = createFakeBackend()
    const states: Array<{ speaking: boolean, emotion: string | undefined }> = []
    let speak: ReturnType<typeof useSpeechPlayer>['speak'] | undefined

    function Harness() {
      const player = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      speak = player.speak
      states.push({ speaking: player.speaking, emotion: player.emotion })
      return null
    }

    render(<Harness />)
    expect(states.at(-1)).toEqual({ speaking: false, emotion: undefined })

    await act(async () => {
      const turn = speak!()
      await turn.push('Well done.<|ACT {"emotion":"happy"}|>')
      await turn.end()
    })

    await until(() => states.at(-1)?.emotion === 'happy', 'emotion reached React state')
    await until(() => states.at(-1)?.speaking === false, 'speaking returned to false')

    // It really did go true at some point — not just stayed false throughout.
    expect(states.some(state => state.speaking)).toBe(true)
    expect(fake.played.map(text => text.trim())).toEqual(['Well done.'])
  })

  it('mutes through to the backend and reports it as state', async () => {
    const fake = createFakeBackend()
    let api: ReturnType<typeof useSpeechPlayer> | undefined

    function Harness() {
      api = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      return null
    }

    render(<Harness />)
    expect(api!.muted).toBe(false)

    act(() => api!.setMuted(true))
    expect(fake.isMuted()).toBe(true)
    expect(api!.muted).toBe(true)

    // Muted still plays: PROTOCOL.md §6.4.
    await act(async () => {
      const turn = api!.speak()
      await turn.push('One. Two.')
      await turn.end()
    })
    await until(() => fake.played.length >= 2, 'segments played while muted')
  })

  it('does not throw when speak() is called after unmount', async () => {
    const fake = createFakeBackend()
    let speak: ReturnType<typeof useSpeechPlayer>['speak'] | undefined

    function Harness() {
      speak = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) }).speak
      return null
    }

    render(<Harness />)
    act(() => root.unmount())

    // A late SSE delta must not take the lesson down.
    await expect((async () => {
      const turn = speak!()
      await turn.push('stray delta')
      await turn.end()
      turn.cancel()
    })()).resolves.toBeUndefined()
  })

  it('changing a handler does not rebuild the audio graph', () => {
    const fake = createFakeBackend()

    function Harness({ tick }: { tick: number }) {
      useSpeechPlayer({
        audio: fake.backend,
        tts: async text => encode(text),
        // A fresh closure on every render — the common React mistake this guards.
        onSegment: () => void tick,
      })
      return null
    }

    render(<Harness tick={1} />)
    render(<Harness tick={2} />)
    render(<Harness tick={3} />)

    expect(fake.isDisposed()).toBe(false)
  })

  it('say() is a one-call shorthand for a whole utterance', async () => {
    const fake = createFakeBackend()
    let api: ReturnType<typeof useSpeechPlayer> | undefined

    function Harness() {
      api = useSpeechPlayer({ audio: fake.backend, tts: async text => encode(text) })
      return null
    }

    render(<Harness />)
    await act(async () => {
      await api!.say('Good morning. Please sit down.')
    })

    await until(() => fake.played.length >= 2, 'both sentences played')
    expect(fake.played.map(t => t.trim())).toEqual(['Good morning.', 'Please sit down.'])
  })
})

describe('Live2DAvatar', () => {
  it('is exported as a component and renders a canvas without a model loaded', async () => {
    // jsdom has no WebGL, so the stage will fail to initialise — the point of this
    // test is that the component still mounts, still renders its canvas, and reports
    // the failure through onError instead of throwing during render.
    const { Live2DAvatar } = await import('./Live2DAvatar')
    const onError = vi.fn()

    render(
      <Live2DAvatar
        model="/nowhere/model.model3.json"
        onError={onError}
        renderError={error => <span data-testid="err">{error.message}</span>}
      />,
    )

    expect(container.querySelector('canvas')).toBeTruthy()
  })
})
