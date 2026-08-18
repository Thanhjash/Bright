/**
 * Avatar — the teacher's face. A real Live2D character, or a loud failure.
 *
 *     <Avatar emotion={Emotion} speaking={boolean} mouthOpen={number} />
 *
 * There is deliberately NO drawn fallback. An earlier version fell back to a
 * hand-drawn SVG face, which was a mistake: Live2D failed for a whole session
 * and the screen looked fine, so the real error went unnoticed. A failure here
 * must be visible and retryable, never papered over.
 *
 * `mouthOpen` is 0…0.7 — the value Live2D writes raw to `ParamMouthOpenY`
 * (PROTOCOL.md §6.5). Do not rescale it on the way in.
 *
 * EMOTIONS ARE NOT WIRED YET, on purpose. Hiyori ships motion groups
 * `Idle / Flick / Tap` and no expressions at all, so the contract's emotion →
 * motion-group table matches exactly one of nine. Every other emotion resolves
 * harmlessly to `Idle` through airi-bridge's fallback chain. Worth knowing:
 * AIRI has the same gap on its own default model, and says so in a TODO
 * (`Model.vue:489`). Fixing it means driving Hiyori's 70 parameters directly —
 * deferred until lip-sync is proven.
 */
import { useCallback, useState } from 'react'
import { Live2DAvatar } from '@bright/airi-bridge/react'
import type { Live2DStage } from '@bright/airi-bridge'
import type { Emotion } from '@contracts'

export interface AvatarProps {
  emotion: Emotion
  speaking: boolean
  /** 0…0.7 */
  mouthOpen: number
  className?: string
}

/**
 * Hiyori Pro — AIRI's own default character, fetched from the same CDN AIRI
 * uses (`dist.ayaka.moe`). Served from `public/live2d`, a symlink to the repo's
 * `models/live2d`.
 *
 * Overridable so a different character drops in without a rebuild — which one
 * we ship is an open product decision, not a constant
 * (docs/STATE.md §9).
 */
const MODEL_URL = import.meta.env.VITE_LIVE2D_MODEL ?? '/live2d/hiyori_pro_zh/runtime/hiyori_pro_t11.model3.json'
/** Exported: AvatarLayer reads the same document to size the canvas box. */
export const BINDING_URL = import.meta.env.VITE_LIVE2D_BINDING ?? '/live2d/bright-model.json'
const CUBISM_CORE = import.meta.env.VITE_CUBISM_CORE ?? '/live2d/live2dcubismcore.min.js'

export function Avatar({ emotion, speaking, mouthOpen, className }: AvatarProps) {
  const [error, setError] = useState<Error | null>(null)
  // Bumping this remounts Live2DAvatar, which is what actually retries the load.
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setError(null)
    setAttempt((n) => n + 1)
  }, [])

  // Dev-only handle, the sibling of `window.__bright`. The projector has no
  // devtools, and tuning `bright-model.json`'s `layout` block against a real
  // column means reading the model's intrinsic size and the placement the fit
  // actually chose. Without this the only instrument is a screenshot.
  const onReady = useCallback((stage: Live2DStage) => {
    if (!import.meta.env.DEV) return
    ;(window as unknown as Record<string, unknown>).__brightStage = stage
  }, [])

  if (error) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-red-500/60 bg-red-950/40 p-6 text-center ${className ?? ''}`}
        role="alert"
      >
        <div className="text-3xl">⚠️</div>
        <div className="text-lg font-bold text-red-200">Live2D failed to load</div>
        <div className="max-w-[28ch] break-words font-mono text-xs leading-relaxed text-red-300/90">
          {error.message}
        </div>
        <button
          type="button"
          onClick={retry}
          className="rounded-lg bg-red-500/90 px-5 py-2 text-base font-semibold text-white transition hover:bg-red-400"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <Live2DAvatar
      key={attempt}
      model={MODEL_URL}
      binding={BINDING_URL}
      cubismCore={CUBISM_CORE}
      emotion={emotion}
      speaking={speaking}
      getMouthOpen={() => mouthOpen}
      className={className}
      onReady={onReady}
      fallback={
        <div
          className={`flex items-center justify-center ${className ?? ''}`}
          aria-label="loading character"
        >
          <div className="h-16 w-16 animate-spin rounded-full border-4 border-white/15 border-t-white/70" />
        </div>
      }
      onError={setError}
    />
  )
}
