export type {
  EmotionAction,
  EmotionActionSource,
  EmotionResolution,
  EmotionResolver,
  ModelCapabilities,
} from './emotion-channel'

export {
  createEmotionResolver,
  EMPTY_CAPABILITIES,
  resolveEmotionAction,
} from './emotion-channel'

export type { ExpressionEntry, ExpressionIndex, ExpressionRef } from './expression-index'
export { buildExpressionIndex, resolveExpressionRef } from './expression-index'

export type { Dimensions, FittedPlacement } from './fit-model'
export { fitModel } from './fit-model'

export { useLive2DIdleEyeFocus } from './idle-eye-focus'

export type {
  EmotionBinding,
  EmotionChannel,
  LayoutBinding,
  LipSyncBinding,
  Live2DModelBinding,
  MotionGroupBinding,
} from './model-binding'

export {
  DEFAULT_MODEL_BINDING,
  loadModelBinding,
  parseModelBinding,
} from './model-binding'

export type { Live2DModelParameters } from './model-parameters'
export {
  createModelParameters,
  DEFAULT_MODEL_PARAMETERS,
  MODEL_PARAMETER_IDS,
} from './model-parameters'

export type {
  MotionManagerPlugin,
  MotionManagerPluginContext,
  MotionManagerUpdateContext,
  PixiLive2DInternalModel,
  UseLive2DMotionManagerUpdateOptions,
} from './motion-manager'

export {
  useLive2DMotionManagerUpdate,
  useMotionUpdatePluginAutoEyeBlink,
  useMotionUpdatePluginIdleDisable,
  useMotionUpdatePluginIdleFocus,
  useMotionUpdatePluginLipSync,
} from './motion-manager'

export type { MaybeRefOrGetter, ReadonlyRef, Ref } from './ref'
export { computedRef, ref, toValue } from './ref'

export type { Live2DStage, Live2DStageOptions } from './stage'
export { createLive2DStage, ensureCubismCore } from './stage'

export { randomSaccadeInterval } from './eye-motions'

// `./live2d-zip-loader` is deliberately NOT re-exported: importing it patches
// pixi-live2d-display's static loaders. Import it explicitly, and only if you load
// `.zip` or directory-upload models:
//   import '@bright/airi-bridge/live2d/zip-loader'
export { decodeZipFileName } from './decode-zip-filename'
