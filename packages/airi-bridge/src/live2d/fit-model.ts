/**
 * Ported from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/stage-ui-live2d/src/composables/live2d/fit-model.ts (v0.11.3 @ b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * De-Vue'd: upstream is a `computed()` over `@vueuse/core` breakpoints; this is a pure
 * function. The normalisation maths is unchanged — `scale == 1` means the model is
 * twice the viewport height.
 *
 * DEVIATION: upstream picks the vertical offset from a Tailwind breakpoint (0.75 on
 * small web screens, 1 elsewhere). Bright renders on one projector at a fixed size, so
 * placement comes from `bright-model.json`'s `layout` block instead — `anchor` for the
 * gross position, `scale` / `offsetX` / `offsetY` for the tuning the projector needs.
 */

import type { LayoutBinding } from './model-binding'

export interface Dimensions {
  width: number
  height: number
}

export interface FittedPlacement {
  scale: number
  x: number
  y: number
}

/** Horizontal placement per anchor, as a fraction of canvas width. */
const ANCHOR_X: Record<LayoutBinding['anchor'], number> = {
  'center': 0.5,
  'bottom-center': 0.5,
  'bottom-left': 0.25,
  'bottom-right': 0.75,
}

/**
 * Normalises a model into a canvas.
 *
 * The model is anchored at (0.5, 0.5), so `y = height` puts the model's centre on the
 * bottom edge — which is upstream's "show the upper half of the body". That is the
 * behaviour for every anchor here; the anchors differ only horizontally.
 *
 * @param canvas logical canvas size
 * @param model the model's intrinsic size, read after load
 * @param layout the `layout` block from the model binding
 */
export function fitModel(
  canvas: Dimensions,
  model: Dimensions,
  layout: LayoutBinding = { anchor: 'center', scale: 1, offsetX: 0, offsetY: 0 },
): FittedPlacement {
  const heightScale = (canvas.height / model.height) * 2
  const widthScale = (canvas.width / model.width) * 2
  let minScale = Math.min(heightScale, widthScale)

  // A zero-sized or not-yet-measured model would otherwise produce Infinity/NaN and
  // put the model somewhere unrenderable. Upstream guards the same way.
  if (Number.isNaN(minScale) || minScale <= 0)
    minScale = 1e-6

  return {
    scale: minScale * (layout.scale || 1),
    x: canvas.width * ANCHOR_X[layout.anchor] + canvas.width * (layout.offsetX || 0),
    y: canvas.height - canvas.height * (layout.offsetY || 0),
  }
}
