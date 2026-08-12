/**
 * Manual Live2D parameter overrides.
 *
 * Ported from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/stage-ui-live2d/src/stores/model-parameters.ts (v0.11.3 @ b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Upstream keeps these in a Pinia store backed by localStorage so a user can tune
 * the avatar from a settings panel. Bright has no such panel: this is a plain
 * object with upstream's defaults, passed into the stage and mutated in place if a
 * caller ever needs to.
 *
 * The motion-manager plugins treat `leftEyeOpen` / `rightEyeOpen` as MULTIPLIERS on
 * whatever the blink and motion curves produce, so 1 means "don't interfere".
 */

export interface Live2DModelParameters {
  angleX: number
  angleY: number
  angleZ: number
  leftEyeOpen: number
  rightEyeOpen: number
  leftEyeSmile: number
  rightEyeSmile: number
  leftEyebrowLR: number
  rightEyebrowLR: number
  leftEyebrowY: number
  rightEyebrowY: number
  leftEyebrowAngle: number
  rightEyebrowAngle: number
  leftEyebrowForm: number
  rightEyebrowForm: number
  mouthOpen: number
  mouthForm: number
  cheek: number
  bodyAngleX: number
  bodyAngleY: number
  bodyAngleZ: number
  breath: number
}

/** Upstream's `defaultModelParameters`, value for value. */
export const DEFAULT_MODEL_PARAMETERS: Live2DModelParameters = {
  angleX: 0,
  angleY: 0,
  angleZ: 0,
  leftEyeOpen: 1,
  rightEyeOpen: 1,
  leftEyeSmile: 0,
  rightEyeSmile: 0,
  leftEyebrowLR: 0,
  rightEyebrowLR: 0,
  leftEyebrowY: 0,
  rightEyebrowY: 0,
  leftEyebrowAngle: 0,
  rightEyebrowAngle: 0,
  leftEyebrowForm: 0,
  rightEyebrowForm: 0,
  mouthOpen: 0,
  mouthForm: 0,
  cheek: 0,
  bodyAngleX: 0,
  bodyAngleY: 0,
  bodyAngleZ: 0,
  breath: 0,
}

export function createModelParameters(
  overrides: Partial<Live2DModelParameters> = {},
): Live2DModelParameters {
  return { ...DEFAULT_MODEL_PARAMETERS, ...overrides }
}

/** Cubism parameter id for each entry above, in the order upstream applies them. */
export const MODEL_PARAMETER_IDS: Array<[keyof Live2DModelParameters, string]> = [
  ['angleX', 'ParamAngleX'],
  ['angleY', 'ParamAngleY'],
  ['angleZ', 'ParamAngleZ'],
  ['leftEyeOpen', 'ParamEyeLOpen'],
  ['rightEyeOpen', 'ParamEyeROpen'],
  ['leftEyeSmile', 'ParamEyeSmile'],
  ['leftEyebrowLR', 'ParamBrowLX'],
  ['rightEyebrowLR', 'ParamBrowRX'],
  ['leftEyebrowY', 'ParamBrowLY'],
  ['rightEyebrowY', 'ParamBrowRY'],
  ['leftEyebrowAngle', 'ParamBrowLAngle'],
  ['rightEyebrowAngle', 'ParamBrowRAngle'],
  ['leftEyebrowForm', 'ParamBrowLForm'],
  ['rightEyebrowForm', 'ParamBrowRForm'],
  ['mouthOpen', 'ParamMouthOpenY'],
  ['mouthForm', 'ParamMouthForm'],
  ['cheek', 'ParamCheek'],
  ['bodyAngleX', 'ParamBodyAngleX'],
  ['bodyAngleY', 'ParamBodyAngleY'],
  ['bodyAngleZ', 'ParamBodyAngleZ'],
  ['breath', 'ParamBreath'],
]
