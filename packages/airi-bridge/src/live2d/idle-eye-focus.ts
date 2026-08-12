/**
 * Ported from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/stage-ui-live2d/src/composables/live2d/animation.ts (v0.11.3 @ b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Renamed from `animation.ts` to say what it is. Deviations marked inline.
 */

import type { InternalModel } from 'pixi-live2d-display/cubism4'

import { randomSaccadeInterval } from './eye-motions'

// DEVIATION: upstream reaches into `three` for two one-line math helpers. Bright has
// no other reason to depend on three, so they are inlined here. Same formulas.
const randFloat = (low: number, high: number) => low + Math.random() * (high - low)
const lerp = (x: number, y: number, t: number) => (1 - t) * x + t * y

/**
 * This is to simulate idle eye saccades and focus (head) movements in a *pretty* naive way.
 * Not using any reactivity here as it's not yet needed.
 * Keeping it here as a composable for future extension.
 */
export function useLive2DIdleEyeFocus() {
  let nextSaccadeAfter = -1
  let focusTarget: [number, number] | undefined
  let lastSaccadeAt = -1

  // Function to handle idle eye saccades and focus (head) movements
  function update(model: InternalModel, now: number) {
    if (now >= nextSaccadeAfter || now < lastSaccadeAt) {
      focusTarget = [randFloat(-1, 1), randFloat(-1, 0.7)]
      lastSaccadeAt = now
      nextSaccadeAfter = now + (randomSaccadeInterval() / 1000)
      model.focusController.focus(focusTarget![0] * 0.5, focusTarget![1] * 0.5, false)
    }

    model.focusController.update(now - lastSaccadeAt)
    const coreModel = model.coreModel as any
    // TODO: After emotion mapper, stage editor, eye related parameters should be take cared to be dynamical instead of hardcoding
    coreModel.setParameterValueById('ParamEyeBallX', lerp(coreModel.getParameterValueById('ParamEyeBallX'), focusTarget![0], 0.3))
    coreModel.setParameterValueById('ParamEyeBallY', lerp(coreModel.getParameterValueById('ParamEyeBallY'), focusTarget![1], 0.3))
  }

  return { update }
}
