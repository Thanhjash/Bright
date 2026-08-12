/**
 * The avatar's column on the Stage.
 *
 * It lives BESIDE the board, never on top of it (docs/3-design/runtime-topology.md §4): the board
 * carries the pedagogy, the avatar carries presence. This layer owns nothing
 * but layout and the store subscription — swapping in the Live2D renderer
 * from packages/airi-bridge means changing the one `<Avatar>` line below.
 *
 * Subscriptions are field-by-field on purpose: `mouthOpen` updates at frame
 * rate and must not re-render anything except the avatar.
 *
 * ── THE CANVAS BOX ────────────────────────────────────────────────────────
 * `models/live2d/bright-model.json` owns where the model sits INSIDE its
 * canvas; this file owns how big that canvas is. The two multiply, and the
 * binding's `offsetY` alone decides how much of the model you ever see:
 *
 *     fitModel puts the model's CENTRE at  y = H_canvas · (1 − offsetY)
 *     ⇒ the lowest visible point of the model is the fraction
 *          v = 0.5 + offsetY · H_canvas / H_model
 *
 * With `offsetY: 0.12` and a canvas the height of the column, v ≈ 0.60 — she is
 * sliced off mid-thigh, which is exactly the bug this file exists to fix. Since
 * v only depends on the RATIO H_canvas / H_model, a canvas taller than the
 * column, anchored to its bottom, moves the cut line down without touching the
 * binding. Solve for the canvas height that puts the cut at `TARGET_VISIBLE`:
 *
 *     H_canvas = (v − 0.5) / offsetY · H_model
 *     H_model  = 2 · W_canvas · scale · (modelH / modelW)      ← width-limited fit
 *     ⇒ H_canvas / W_canvas = (v − 0.5)/offsetY · 2 · scale · (modelH/modelW)
 *
 * a pure aspect ratio, so one `aspect-ratio` rule covers every resolution and
 * the overflowing part is clipped by the wrapper. The cut line lands EXACTLY on
 * the canvas's bottom edge (substitute back — the offsetY terms cancel), so
 * bottom-anchoring is exact rather than approximate.
 *
 * The numbers are read from the binding at runtime, not baked in. Apply the
 * values this file's owner recommends (`scale: 0.94, offsetY: 0.33`) and the
 * ratio collapses to ~1 column-height on its own — the compensation disappears
 * instead of becoming a stale magic number.
 */
import { useEffect, useState } from 'react'
import { useClassroom } from '../../store/classroom'
import { Avatar, BINDING_URL } from './Avatar'

/**
 * How far down the model we want the column's bottom edge to cut, as a
 * fraction of the model's own height. Measured against Hiyori Pro by rendering
 * her whole canvas: hair 0.07, skirt hem 0.58, knee 0.71, feet 0.96. 0.78 is
 * "below the knee" with the socks showing — present, grounded, not a floating
 * bust, and not so tall that her head leaves the top of the column.
 */
const TARGET_VISIBLE = 0.78

/**
 * Hiyori Pro's intrinsic canvas, 2976 × 4175, read from the loaded model. The
 * binding is already per-model by construction ("One of these per Live2D
 * model"), so a per-model constant here is no less portable than the file it
 * reads. A different aspect only mis-sizes the reserve, never breaks rendering.
 */
const MODEL_ASPECT = 4175 / 2976

/** Plain column height. Used until the binding loads, and whenever it cannot help. */
const NO_COMPENSATION = 0

/**
 * `H_canvas / W_canvas` needed to reach TARGET_VISIBLE, or NO_COMPENSATION.
 *
 * `offsetY` near zero would demand an unboundedly tall canvas, and a ratio that
 * does not at least fill the column would shrink her instead — both fall back.
 */
function canvasRatio(scale: number, offsetY: number, columnRatio: number): number {
  if (!(offsetY > 0.02) || !(scale > 0)) return NO_COMPENSATION
  const ratio = ((TARGET_VISIBLE - 0.5) / offsetY) * 2 * scale * MODEL_ASPECT
  if (!Number.isFinite(ratio) || ratio < columnRatio || ratio > 8) return NO_COMPENSATION
  return ratio
}

export function AvatarLayer() {
  const emotion = useClassroom((s) => s.avatar.emotion)
  const speaking = useClassroom((s) => s.avatar.speaking)
  const mouthOpen = useClassroom((s) => s.avatar.mouthOpen)
  const ratio = useBindingCanvasRatio()

  return (
    <div className="relative flex h-full w-full items-end justify-center overflow-hidden">
      {/* Floor shadow. On the OUTER wrapper: the inner box is mostly empty
          canvas above her head, and a gradient pinned to its bottom would sit
          under her knees instead of on the floor. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-[22%] bg-gradient-to-t from-ink-950/45 to-transparent" />
      <div
        className="absolute inset-x-0 bottom-0"
        style={ratio === NO_COMPENSATION ? { top: 0 } : { aspectRatio: `1 / ${ratio}` }}
      >
        <Avatar
          emotion={emotion}
          speaking={speaking}
          mouthOpen={mouthOpen}
          className="h-full w-full"
        />
      </div>
    </div>
  )
}

/**
 * Reads `layout.scale` / `layout.offsetY` from the binding the Avatar is about
 * to load anyway, and turns them into the canvas aspect ratio above.
 *
 * A failed fetch is not an error worth showing: the model itself loads through
 * the same URL, so a real problem surfaces loudly in `<Avatar>` a moment later.
 * Here it just means "no compensation", which is the pre-existing behaviour.
 *
 * Below `lg` the avatar is a 26vh strip, not a column — there the fit is height-
 * limited and a taller canvas would push her out of frame entirely, so the
 * compensation is off. That branch is a dev-laptop convenience; the projector
 * is always wide.
 */
const COLUMN_QUERY = '(min-width: 1024px)'

function useBindingCanvasRatio(): number {
  const [ratio, setRatio] = useState(NO_COMPENSATION)
  const [isColumn, setIsColumn] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(COLUMN_QUERY).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(COLUMN_QUERY)
    const sync = () => setIsColumn(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const res = await fetch(BINDING_URL)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const doc = (await res.json()) as { layout?: { scale?: number; offsetY?: number } }
        if (!live) return
        // The column is `--avatar-col` of the width and all of the height, so
        // its own ratio is what "no compensation" would give us.
        const column = window.innerHeight / Math.max(1, window.innerWidth * 0.25)
        setRatio(canvasRatio(doc.layout?.scale ?? 1, doc.layout?.offsetY ?? 0, column))
      } catch (cause) {
        console.warn('[stage] avatar layout binding unreadable, using a plain column', cause)
      }
    })()
    return () => {
      live = false
    }
  }, [])

  return isColumn ? ratio : NO_COMPENSATION
}
