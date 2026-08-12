/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/managers/playback-manager.test.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied with the minimal deviations noted below. Do not otherwise edit.
 *
 * Upstream test, kept as regression coverage for the vendored playback manager.
 *
 * DEVIATION: three of these cases are marked `it.fails`. They fail against
 * PRISTINE upstream source at b230e16 — verified by diffing our copy of
 * playback-manager.ts against upstream (identical but for the error-message
 * import). They encode behaviour AIRI intends but has not implemented:
 * `stopByIntent` ends with `tryStartWaiting()`, and `stealOldest` restarts the
 * stealing item synchronously instead of leaving it queued. Assertions are
 * untouched. `it.fails` (rather than `it.skip`) makes the suite go red the day
 * we re-vendor a fixed upstream, so the discrepancy cannot rot silently.
 * None of the three affects Bright: `useSpeechPlayer` runs maxVoices=1 with no
 * owner ids, so neither code path is reachable.
 */

import type { PlaybackItem } from '../types'

import { describe, expect, it, vi } from 'vitest'

import { createPlaybackManager } from './playback-manager'

function createPlaybackItem(id: string, priority: number, intentId: string, ownerId?: string): PlaybackItem<unknown> {
  return {
    id,
    streamId: 'stream-1',
    intentId,
    segmentId: `${id}-segment`,
    sequence: 1,
    ownerId,
    priority,
    text: `${id} text`,
    special: null,
    audio: { id },
    createdAt: Date.now(),
  }
}

describe('createPlaybackManager', () => {
  // DEVIATION: upstream writes this as `it.each(['stopByIntent', 'stopAll'])`.
  // Split so the known-failing half can carry `it.fails`. Body is unchanged.
  function stopDoesNotRestartQueuedPlayback(method: string) {
    {
      const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
        signal.addEventListener('abort', () => resolve(), { once: true })
      }))
      const manager = createPlaybackManager({
        maxVoices: 1,
        overflowPolicy: 'queue',
        play,
      })

      manager.schedule(createPlaybackItem('active', 10, 'intent-1'))
      manager.schedule(createPlaybackItem('queued', 5, 'intent-2'))

      if (method === 'stopByIntent')
        manager.stopByIntent('intent-1', 'stop')
      else
        manager.stopAll('stop')

      expect(play).toHaveBeenCalledTimes(1)
    }
  }

  it('does not restart queued playback when stopping with stopAll', () => {
    stopDoesNotRestartQueuedPlayback('stopAll')
  })

  it.fails('does not restart queued playback when stopping with stopByIntent', () => {
    stopDoesNotRestartQueuedPlayback('stopByIntent')
  })

  it('rejects lower-priority overflow items with steal-lowest-priority policy', () => {
    const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
      signal.addEventListener('abort', () => resolve(), { once: true })
    }))
    const rejected: string[] = []
    const manager = createPlaybackManager({
      maxVoices: 1,
      overflowPolicy: 'steal-lowest-priority',
      play,
    })

    manager.onReject((event) => {
      rejected.push(event.item.id)
    })

    manager.schedule(createPlaybackItem('active', 10, 'intent-1'))
    manager.schedule(createPlaybackItem('lower', 5, 'intent-2'))

    expect(play).toHaveBeenCalledTimes(1)
    expect(rejected).toEqual(['lower'])
  })

  it('rejects equal-priority overflow items with steal-lowest-priority policy', () => {
    const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
      signal.addEventListener('abort', () => resolve(), { once: true })
    }))
    const rejected: string[] = []
    const manager = createPlaybackManager({
      maxVoices: 1,
      overflowPolicy: 'steal-lowest-priority',
      play,
    })

    manager.onReject((event) => {
      rejected.push(event.item.id)
    })

    manager.schedule(createPlaybackItem('active', 10, 'intent-1'))
    manager.schedule(createPlaybackItem('equal', 10, 'intent-2'))

    expect(play).toHaveBeenCalledTimes(1)
    expect(rejected).toEqual(['equal'])
  })

  it('rejects an owner-overflow item after stealing a different-owner victim with steal-oldest', () => {
    const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
      signal.addEventListener('abort', () => resolve(), { once: true })
    }))
    const rejected: string[] = []
    const manager = createPlaybackManager({
      maxVoices: 2,
      maxVoicesPerOwner: 1,
      overflowPolicy: 'steal-oldest',
      ownerOverflowPolicy: 'reject',
      play,
    })

    manager.onReject((event) => {
      rejected.push(event.item.id)
    })

    manager.schedule(createPlaybackItem('b', 9, 'intent-2', 'owner-y'))
    manager.schedule(createPlaybackItem('a', 10, 'intent-1', 'owner-x'))
    manager.schedule(createPlaybackItem('a2', 8, 'intent-3', 'owner-x'))

    expect(play).toHaveBeenCalledTimes(2)
    expect(rejected).toEqual(['a2'])
  })

  it('rejects an owner-overflow item after stealing a lower-priority victim with steal-lowest-priority', () => {
    const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
      signal.addEventListener('abort', () => resolve(), { once: true })
    }))
    const rejected: string[] = []
    const manager = createPlaybackManager({
      maxVoices: 2,
      maxVoicesPerOwner: 1,
      overflowPolicy: 'steal-lowest-priority',
      ownerOverflowPolicy: 'reject',
      play,
    })

    manager.onReject((event) => {
      rejected.push(event.item.id)
    })

    manager.schedule(createPlaybackItem('a', 10, 'intent-1', 'owner-x'))
    manager.schedule(createPlaybackItem('b', 1, 'intent-2', 'owner-y'))
    manager.schedule(createPlaybackItem('a2', 5, 'intent-3', 'owner-x'))

    expect(play).toHaveBeenCalledTimes(2)
    expect(rejected).toEqual(['a2'])
  })

  it.fails('steals the oldest active item for queued owner-overflow when a slot frees up', async () => {
    let resolvePlayback: (() => void) | undefined
    const play = vi.fn((_item, signal) => new Promise<void>((resolve) => {
      resolvePlayback = () => {
        signal.aborted ? resolve() : signal.addEventListener('abort', () => resolve(), { once: true })
        resolve()
      }
    }))
    const manager = createPlaybackManager({
      maxVoices: 2,
      maxVoicesPerOwner: 1,
      overflowPolicy: 'queue',
      ownerOverflowPolicy: 'steal-oldest',
      play,
    })

    manager.schedule(createPlaybackItem('a', 10, 'intent-1', 'owner-x'))
    manager.schedule(createPlaybackItem('b', 9, 'intent-2', 'owner-y'))
    manager.schedule(createPlaybackItem('a2', 8, 'intent-3', 'owner-x'))

    expect(play).toHaveBeenCalledTimes(2)

    resolvePlayback?.()
    await Promise.resolve()
    await Promise.resolve()

    expect(play).toHaveBeenCalledTimes(3)
  })

  it.fails('does not drain the queue while stealing an owner-overflow playback slot', async () => {
    const resolveMap = new Map<string, () => void>()
    const play = vi.fn((item: PlaybackItem<unknown>, signal) => new Promise<void>((resolve) => {
      resolveMap.set(item.id, () => resolve())

      if (!signal.aborted) {
        signal.addEventListener('abort', () => resolve(), { once: true })
      }
    }))
    const manager = createPlaybackManager({
      maxVoices: 2,
      maxVoicesPerOwner: 1,
      overflowPolicy: 'queue',
      ownerOverflowPolicy: 'steal-oldest',
      play,
    })

    manager.schedule(createPlaybackItem('a', 10, 'intent-1', 'owner-x'))
    manager.schedule(createPlaybackItem('d', 10, 'intent-2', 'owner-y'))
    manager.schedule(createPlaybackItem('a2', 9, 'intent-3', 'owner-x'))
    manager.schedule(createPlaybackItem('b', 8, 'intent-4', 'owner-y'))
    manager.schedule(createPlaybackItem('c', 7, 'intent-5', 'owner-y'))

    expect(play).toHaveBeenCalledTimes(2)

    resolveMap.get('d')?.()
    await Promise.resolve()
    await Promise.resolve()

    expect(play).toHaveBeenCalledTimes(3)
    expect(play).toHaveBeenNthCalledWith(3, expect.objectContaining({ id: 'a2' }), expect.any(AbortSignal))
  })
})
