/**
 * The stage's speech-output coordinator.
 *
 * It is deliberately keyed by the server's speech turn id. Text may arrive as
 * many deltas, and cancellation must retire only the addressed turn. The
 * facilitator console never configures this module, so it can observe speech
 * events without becoming a second loudspeaker.
 */
import { createSpeechPlayer, createWebAudioBackend } from '@bright/airi-bridge'
import type {
  LipSyncProfile,
  SpeechPlayer,
  SpeechTurn,
} from '@bright/airi-bridge'

import wlipsyncProfile from '@bright/airi-bridge/wlipsync-profile.json'
import { resolveAsset } from '../lib/assets'
import { SPEECH_URL } from '../lib/env'
import { useClassroom } from '../store/classroom'

function pickVoice(text: string): 'en' | 'vi' {
  const forced = import.meta.env.VITE_TTS_VOICE
  if (forced === 'en' || forced === 'vi') return forced
  const letters = text.replace(/\s+/g, '')
  if (!letters) return 'en'
  const latin = (letters.match(/[A-Za-z]/g) ?? []).length
  const viet = (letters.match(/[ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]/g) ?? []).length
  return viet > latin ? 'vi' : 'en'
}

export type PlaybackStatus = 'completed' | 'cancelled' | 'failed'
export type SpeechBehavior = 'queue' | 'interrupt' | 'replace'

export interface SpeechOutputCallbacks {
  onPlaybackStarted?: (speechTurnId: string, metrics?: Record<string, number>) => void
  onPlaybackFinished?: (
    speechTurnId: string,
    status: PlaybackStatus,
    reason?: string,
    reportToCore?: boolean,
    metrics?: Record<string, number>,
  ) => void
}

export interface SpeechStart {
  speechTurnId: string
  conversationTurnId?: string
  behavior?: SpeechBehavior
  audioAsset?: string
}

interface ManagedTurn {
  turn: SpeechTurn
  started: boolean
  terminal: boolean
  chain: Promise<void>
  audioAsset?: string
  assetConsumed: boolean
  reportTerminal: boolean
  openedAt: number
  playbackStartedAt?: number
}

let player: SpeechPlayer | null = null
const turns = new Map<string, ManagedTurn>()
const failedTurns = new Set<string>()
let callbacks: SpeechOutputCallbacks = {}
let enabled = false
let raf = 0

async function tts(
  text: string,
  context: { segmentId: string, turnId?: string },
  signal: AbortSignal,
): Promise<ArrayBuffer> {
  const managed = context.turnId ? turns.get(context.turnId) : undefined
  if (managed?.audioAsset) {
    if (managed.assetConsumed)
      return new ArrayBuffer(0)
    managed.assetConsumed = true
    const url = resolveAsset(managed.audioAsset)
    if (!url)
      throw new Error(`invalid audio asset for turn ${context.turnId}`)
    const asset = await fetch(url, { signal })
    if (!asset.ok)
      throw new Error(`audio asset ${asset.status} for turn ${context.turnId}`)
    return asset.arrayBuffer()
  }
  const res = await fetch(`${SPEECH_URL}/audio/speech`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: text, voice: pickVoice(text) }),
    signal,
  })
  if (!res.ok) {
    throw new Error(`TTS ${res.status} for ${JSON.stringify(text.slice(0, 40))}`)
  }
  return res.arrayBuffer()
}

function finish(speechTurnId: string, status: PlaybackStatus, reason?: string): void {
  const managed = turns.get(speechTurnId)
  if (!managed || managed.terminal)
    return
  managed.terminal = true
  turns.delete(speechTurnId)
  const now = performance.now()
  callbacks.onPlaybackFinished?.(
    speechTurnId,
    status,
    reason,
    managed.reportTerminal,
    {
      totalMs: Math.round(now - managed.openedAt),
      ...(managed.playbackStartedAt === undefined
        ? {}
        : { playbackMs: Math.round(now - managed.playbackStartedAt) }),
    },
  )
}

function ensurePlayer(): SpeechPlayer {
  if (player)
    return player

  player = createSpeechPlayer({
    tts,
    audio: createWebAudioBackend({ lipSyncProfile: wlipsyncProfile as unknown as LipSyncProfile }),
    onSegmentStart: ({ turnId, audioContextTime }) => {
      if (!turnId)
        return
      const managed = turns.get(turnId)
      if (!managed || managed.started)
        return
      managed.started = true
      managed.playbackStartedAt = performance.now()
      callbacks.onPlaybackStarted?.(turnId, {
        firstAudioMs: Math.round(managed.playbackStartedAt - managed.openedAt),
        ...(audioContextTime === undefined ? {} : { audioContextTime }),
      })
    },
    onTurnEnd: (turnId) => {
      const failed = failedTurns.delete(turnId)
      finish(turnId, failed ? 'failed' : 'completed', failed ? 'tts-error' : undefined)
    },
    onTurnCancel: (turnId, reason) => {
      const failed = failedTurns.delete(turnId)
      finish(turnId, failed ? 'failed' : 'cancelled', reason)
    },
    onEmotion: (emotion, intensity) => {
      useClassroom.getState().applyAct({ emotion: { name: emotion, intensity } })
    },
    onSpeakingChange: (speaking) => {
      useClassroom.getState().setSpeaking(speaking)
      if (speaking)
        startMouthLoop()
      else
        stopMouthLoop()
    },
    onError: (error, context) => {
      if (context?.turnId)
        failedTurns.add(context.turnId)
      console.error('[speech] turn failed:', error)
    },
  })
  return player
}

/** Enables physical playback for the stage and installs wire ACK callbacks. */
export function configureSpeechOutput(next: SpeechOutputCallbacks): () => void {
  enabled = true
  callbacks = next
  return () => {
    stop('speech-output-unmounted', false)
    callbacks = {}
    enabled = false
  }
}

export function hasSpeechTurn(speechTurnId: string): boolean {
  return turns.has(speechTurnId)
}

export function startSpeech({
  speechTurnId,
  conversationTurnId,
  behavior = 'queue',
  audioAsset,
}: SpeechStart): void {
  if (turns.has(speechTurnId))
    return
  if (!enabled)
    configureSpeechOutput(callbacks)
  const turn = ensurePlayer().speak({
    turnId: speechTurnId,
    ownerId: conversationTurnId,
    behavior,
  })
  turns.set(speechTurnId, {
    turn,
    started: false,
    terminal: false,
    chain: Promise.resolve(),
    audioAsset,
    assetConsumed: false,
    reportTerminal: true,
    openedAt: performance.now(),
  })
}

export async function pushSpeech(speechTurnId: string, delta: string): Promise<void> {
  const managed = turns.get(speechTurnId)
  if (!managed || managed.terminal || !delta)
    return
  managed.chain = managed.chain.then(async () => {
    if (!managed.terminal)
      await managed.turn.push(delta)
  })
  await managed.chain
}

export async function endSpeech(speechTurnId: string): Promise<void> {
  const managed = turns.get(speechTurnId)
  if (!managed || managed.terminal)
    return
  managed.chain = managed.chain.then(async () => {
    if (!managed.terminal)
      await managed.turn.end()
  })
  await managed.chain
}

export function cancelSpeech(speechTurnId: string, reason = 'cancelled'): void {
  const managed = turns.get(speechTurnId)
  if (!managed || managed.terminal)
    return
  managed.turn.cancel(reason)
}

export function failSpeech(speechTurnId: string, reason = 'speech-error'): void {
  const managed = turns.get(speechTurnId)
  if (!managed || managed.terminal)
    return
  failedTurns.add(speechTurnId)
  managed.turn.cancel(reason)
}

/** Compatibility adapter for v1/full-text authored speech. */
export function speak(text: string, speechTurnId: string = crypto.randomUUID()): void {
  startSpeech({ speechTurnId })
  void pushSpeech(speechTurnId, text).then(
    () => endSpeech(speechTurnId),
    (error) => {
      console.error('[speech] turn failed:', error)
      cancelSpeech(speechTurnId, 'pipeline-error')
    },
  )
}

function startMouthLoop(): void {
  if (raf || typeof requestAnimationFrame !== 'function')
    return
  const tick = () => {
    const value = player?.getMouthOpen() ?? 0
    // Driver emits 0…0.7; Hiyori ParamMouthOpenY is 0…1. Stretch so speech reads.
    const open = Math.min(1, Math.round((value / 0.62) * 100) / 100)
    useClassroom.getState().setMouthOpen(open)
    raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

function stopMouthLoop(): void {
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
  useClassroom.getState().setMouthOpen(0)
}

export function stop(reason = 'cancelled', reportToCore = true): void {
  if (!reportToCore) {
    for (const managed of turns.values())
      managed.reportTerminal = false
  }
  player?.stopAll(reason)
  // The pipeline normally reports every cancellation synchronously. This loop
  // is a defensive terminal path for a player that failed during construction.
  for (const speechTurnId of [...turns.keys()])
    finish(speechTurnId, 'cancelled', reason)
  stopMouthLoop()
  useClassroom.getState().setSpeaking(false)
}

export function isSpeechPlaying(): boolean {
  return player?.isSpeaking() ?? false
}

let unlockInstalled = false

export function unlockAudioOnFirstGesture(): void {
  if (typeof window === 'undefined' || unlockInstalled)
    return
  unlockInstalled = true
  const unlock = () => {
    try {
      ensurePlayer()
    } catch {
      // AudioContext may still be blocked; the next gesture retries.
    }
    window.removeEventListener('pointerdown', unlock)
    window.removeEventListener('keydown', unlock)
  }
  window.addEventListener('pointerdown', unlock, { once: true })
  window.addEventListener('keydown', unlock, { once: true })
}
