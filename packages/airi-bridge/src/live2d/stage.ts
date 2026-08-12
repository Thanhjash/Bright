/**
 * `createLive2DStage` — the framework-free Live2D runtime.
 *
 * This is the rewritten replacement for AIRI's `Canvas.vue` + `Model.vue`
 * (~940 lines of Vue). The ported logic those files call into — `motion-manager.ts`,
 * `idle-eye-focus.ts`, `fit-model.ts` — lives in sibling modules and is unchanged.
 * What is rewritten here is only the glue: Pixi setup, model load, placement,
 * plugin registration, teardown.
 *
 * THE SCALE TRAP (PROTOCOL.md §6.5). `getMouthOpen()` returns 0…0.7 and is written
 * RAW to the lip-sync parameter, which expects 0…1. `Model.vue` contains
 * `Math.max(0, Math.min(100, props.mouthOpenSize))` — the `100` is dead code, not a
 * 0-100 scale, and clamping to 100 does nothing to a value that never exceeds 0.7.
 * `setMouthOpen` below clamps to [0,1] and does not rescale. Do not "fix" this.
 *
 * RUNTIME PREREQUISITE. pixi-live2d-display needs the Cubism 4 core script
 * (`live2dcubismcore.min.js`) on `globalThis.Live2DCubismCore`. It is not on npm and
 * cannot be bundled — Live2D's licence forbids redistribution. Call
 * `ensureCubismCore(url)` first, or load it with a `<script>` tag.
 */

import type { Application as PixiApplication } from '@pixi/app'
import type { Live2DModel as Live2DModelType } from 'pixi-live2d-display/cubism4'

type Cubism4Module = typeof import('pixi-live2d-display/cubism4')

import type { Emotion } from '../contracts'
import type { EmotionResolution, ModelCapabilities } from './emotion-channel'
import type { Live2DModelBinding } from './model-binding'
import type { Live2DModelParameters } from './model-parameters'
import type { PixiLive2DInternalModel } from './motion-manager'

// NOTE: @pixi/* and pixi-live2d-display are imported LAZILY, inside `load()`.
// `pixi-live2d-display/cubism4` THROWS at module scope when `window.Live2DCubismCore`
// is missing ("Could not find Cubism 4 runtime"). A static import therefore makes the
// whole package unimportable during server-side rendering, in a Node test, or in any
// build step that merely touches the entry point — long before anyone asked for an
// avatar. Deferring costs one dynamic import per stage.

import { createEmotionResolver } from './emotion-channel'
import { buildExpressionIndex } from './expression-index'
import { fitModel } from './fit-model'
import { DEFAULT_MODEL_BINDING, parseModelBinding } from './model-binding'
import { createModelParameters, MODEL_PARAMETER_IDS } from './model-parameters'
import {
  useLive2DMotionManagerUpdate,
  useMotionUpdatePluginAutoEyeBlink,
  useMotionUpdatePluginIdleDisable,
  useMotionUpdatePluginIdleFocus,
  useMotionUpdatePluginLipSync,
} from './motion-manager'
import { ref } from './ref'

export interface Live2DStageOptions {
  /** URL of the model entry file (`*.model3.json`), or a `.zip` if the zip loader is imported. */
  model: string
  /**
   * Per-model binding. Omit to use the contract default (`EMOTION_MOTION_GROUP`,
   * motion channel). See `loadModelBinding`.
   */
  binding?: Live2DModelBinding | unknown
  /** Logical canvas size in CSS pixels. Defaults to the canvas element's own size. */
  width?: number
  height?: number
  /** Internal render scale. 2 is AIRI's default and looks right on a projector. */
  resolution?: number
  /** Ticker cap. 0 (default) means uncapped. */
  maxFps?: number
  modelParameters?: Partial<Live2DModelParameters>
  idleAnimation?: boolean
  forceIdleEyeAnimation?: boolean
  autoBlink?: boolean
  forceAutoBlink?: boolean
  eyeTracking?: boolean
  onLoaded?: (stage: Live2DStage) => void
  onError?: (error: Error) => void
}

export interface Live2DStage {
  /** The Pixi application. Undefined until the stage has finished starting. */
  readonly app: PixiApplication | undefined
  readonly model: Live2DModelType<PixiLive2DInternalModel> | undefined
  readonly binding: Live2DModelBinding
  /** What the loaded model can actually do. Empty until the model loads. */
  capabilities: () => ModelCapabilities
  /** Resolves after the model is on the stage. Rejects only on a fatal load error. */
  ready: () => Promise<void>

  /** Plays a motion group by name. Unknown groups are a no-op, never a throw. */
  setMotion: (group: string, index?: number) => Promise<void>
  /** Applies an expression by `Name`, file basename or index. `null` clears it. */
  setExpression: (ref: string | number | null) => void
  /**
   * Drives emotion through whichever channel the binding says, with the full
   * fallback chain. Returns what it decided, for logging and tests.
   */
  setEmotion: (emotion: Emotion) => EmotionResolution
  /**
   * Mouth open, 0…1, written RAW to the model's lip-sync parameter.
   * Feed it `getMouthOpen()` from the lip-sync driver, unscaled.
   */
  setMouthOpen: (value: number) => void
  /**
   * Speech boundary for the lip-sync plugin. Must be `true` for the whole
   * utterance, including silent gaps between phonemes — the 200 ms release tail and
   * the mouth-close handoff key off this, not off `mouthOpen > 0`.
   */
  setSpeaking: (speaking: boolean) => void
  /** Head/eye focus target in [-1,1]. */
  setFocus: (x: number, y: number) => void
  resize: (width: number, height: number) => void
  destroy: () => void
}

let cubismCorePromise: Promise<void> | undefined

/**
 * Loads the Cubism 4 core script once, if it is not already on the page.
 *
 * Idempotent across calls; concurrent callers share one load.
 */
export function ensureCubismCore(url: string): Promise<void> {
  if ((globalThis as Record<string, unknown>).Live2DCubismCore)
    return Promise.resolve()
  if (cubismCorePromise)
    return cubismCorePromise

  cubismCorePromise = new Promise<void>((resolve, reject) => {
    if (typeof document === 'undefined') {
      reject(new Error('[airi-bridge] ensureCubismCore needs a DOM. Load the script yourself in other runtimes.'))
      return
    }
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      cubismCorePromise = undefined
      reject(new Error(`[airi-bridge] failed to load the Cubism core from ${url}`))
    }
    document.head.appendChild(script)
  })

  return cubismCorePromise
}

function resolveMaxFps(limit?: number) {
  if (!limit || limit <= 0)
    return 0
  return Math.max(1, Math.round(limit))
}

/**
 * Creates and starts a Live2D stage on an existing canvas element.
 *
 * The returned stage is usable immediately — `setEmotion` / `setMouthOpen` before the
 * model finishes loading are absorbed, not dropped errors. Await `ready()` if you
 * need to know the model is really there.
 */
export function createLive2DStage(
  canvas: HTMLCanvasElement,
  options: Live2DStageOptions,
): Live2DStage {
  const binding: Live2DModelBinding = isBinding(options.binding)
    ? options.binding
    : options.binding !== undefined
      ? parseModelBinding(options.binding, options.model)
      : { ...DEFAULT_MODEL_BINDING, id: options.model, modelPath: options.model }

  const resolution = options.resolution ?? 2
  let width = options.width ?? canvas.clientWidth ?? 512
  let height = options.height ?? canvas.clientHeight ?? 512

  let app: PixiApplication | undefined
  let cubism: Cubism4Module | undefined

  async function createPixiApp(): Promise<PixiApplication> {
    const [{ Application }, { extensions }, { Ticker, TickerPlugin }, cubism4] = await Promise.all([
      import('@pixi/app'),
      import('@pixi/extensions'),
      import('@pixi/ticker'),
      import('pixi-live2d-display/cubism4'),
    ])
    cubism = cubism4

    // https://guansss.github.io/pixi-live2d-display/#package-importing
    cubism4.Live2DModel.registerTicker(Ticker)
    extensions.add(TickerPlugin)

    const created = new Application({
      view: canvas,
      width: width * resolution,
      height: height * resolution,
      backgroundAlpha: 0,
      preserveDrawingBuffer: true,
      autoDensity: false,
      resolution: 1,
    })

    // Upstream's render guard: a Pixi throw must stop the ticker and surface once,
    // not repeat sixty times a second into a dead canvas.
    const guardedRender = () => {
      try {
        created.render()
      }
      catch (error) {
        created.ticker.stop()
        fail(error)
      }
    }
    created.ticker.remove(created.render, created)
    created.ticker.add(guardedRender)
    created.ticker.maxFPS = resolveMaxFps(options.maxFps)
    created.stage.scale.set(resolution)

    return created
  }

  const modelParameters = ref<Live2DModelParameters>(createModelParameters(options.modelParameters))
  const mouthOpenSize = ref(0)
  const nowSpeaking = ref(false)
  const lastUpdateTime = ref(0)
  const live2dIdleAnimationEnabled = ref(options.idleAnimation ?? true)
  const live2dForceIdleEyeAnimation = ref(options.forceIdleEyeAnimation ?? true)
  const live2dAutoBlinkEnabled = ref(options.autoBlink ?? true)
  const live2dForceAutoBlinkEnabled = ref(options.forceAutoBlink ?? false)
  const live2dEyeTrackingEnabled = ref(options.eyeTracking ?? false)
  const live2dEyeFocusSourceActive = ref(false)

  let model: Live2DModelType<PixiLive2DInternalModel> | undefined
  let initialModelWidth = 0
  let initialModelHeight = 0
  let destroyed = false
  let capabilities: ModelCapabilities = { expressions: [], motionGroups: [] }
  let emotionResolver = createEmotionResolver(binding, capabilities)

  function fail(error: unknown) {
    const wrapped = error instanceof Error ? error : new Error(String(error))
    console.error('[airi-bridge/live2d]', wrapped)
    options.onError?.(wrapped)
  }

  function place() {
    if (!model)
      return
    const normalized = fitModel(
      { width, height },
      { width: initialModelWidth, height: initialModelHeight },
      binding.layout,
    )
    model.scale.set(normalized.scale, normalized.scale)
    model.x = normalized.x
    model.y = normalized.y
  }

  // Declared here so `stage.ready()` can close over it; assigned below `stage` so the
  // loader can hand the finished stage to `onLoaded`.
  let loadPromise: Promise<void>

  async function load(): Promise<void> {
    app = await createPixiApp()
    if (destroyed) {
      app.destroy(false)
      return
    }

    const live2DModel = new cubism!.Live2DModel<PixiLive2DInternalModel>()
    // The source MUST be the bare URL string.
    //
    // Every middleware that can turn a source into settings is gated on
    // `typeof source === 'string'` — `urlToJSON` (cubism4.js:4509) and
    // `ZipLoader.factory` (:5148) both are. Passing an object such as
    // `{ url, id }` silently skips all of them, and `jsonToSettings` then
    // receives an object that is not settings JSON and throws the
    // uninformative "Unknown settings format". It fails identically for a
    // `.model3.json` URL and for a `.zip`, which makes it very easy to
    // misdiagnose as a model-format problem.
    await cubism!.Live2DFactory.setupLive2DModel(
      live2DModel,
      options.model,
      { autoInteract: false },
    )

    if (destroyed) {
      live2DModel.destroy()
      return
    }

    model = live2DModel
    app.stage.addChild(live2DModel)
    initialModelWidth = live2DModel.width
    initialModelHeight = live2DModel.height
    live2DModel.anchor.set(0.5, 0.5)
    place()

    const internalModel = live2DModel.internalModel
    const coreModel = internalModel.coreModel
    const motionManager = internalModel.motionManager

    // Discover what this model can do. Never assumed, always read off the model.
    const settings = internalModel.settings as unknown as {
      expressions?: Array<{ Name?: unknown, File?: unknown }>
    }
    capabilities = {
      expressions: buildExpressionIndex(settings?.expressions),
      motionGroups: Object.keys(motionManager.definitions ?? {}),
    }
    emotionResolver = createEmotionResolver(binding, capabilities)

    // AIRI's idle-motion quirk fix: idle motion curves fight the idle eye-focus
    // animation, so the eye-ball curves in the idle group are renamed out of the way.
    // FIXME (inherited from upstream): a model whose ONLY group is idle then cannot blink.
    if (motionManager.groups.idle) {
      motionManager.motionGroups[motionManager.groups.idle]?.forEach((motion) => {
        (motion as unknown as { _motionData: { curves: Array<{ id: string }> } })
          ._motionData.curves.forEach((curve) => {
            if (curve.id === 'ParamEyeBallX' || curve.id === 'ParamEyeBallY')
              curve.id = `_${curve.id}`
          })
      })
    }

    const motionManagerUpdate = useLive2DMotionManagerUpdate({
      internalModel,
      motionManager,
      modelParameters,
      live2dEyeTrackingEnabled,
      live2dEyeFocusSourceActive,
      live2dIdleAnimationEnabled,
      live2dForceIdleEyeAnimation,
      live2dAutoBlinkEnabled,
      live2dForceAutoBlinkEnabled,
      lastUpdateTime,
    })

    motionManagerUpdate.register(useMotionUpdatePluginIdleDisable(), 'pre')
    motionManagerUpdate.register(useMotionUpdatePluginIdleFocus(), 'post')
    // 'final' runs regardless of `handled`. Blink first, then lip-sync, so lip-sync
    // owns the mouth parameter last and nothing can reopen it behind its back.
    motionManagerUpdate.register(useMotionUpdatePluginAutoEyeBlink(ref(false)), 'final')
    motionManagerUpdate.register(
      useMotionUpdatePluginLipSync(mouthOpenSize, nowSpeaking, binding.lipSync.parameter),
      'final',
    )

    const hookedUpdate = motionManager.update as (
      coreModel: PixiLive2DInternalModel['coreModel'],
      now: number,
    ) => boolean
    motionManager.update = function (target: PixiLive2DInternalModel['coreModel'], now: number) {
      return motionManagerUpdate.hookUpdate(target, now, hookedUpdate)
    }

    for (const [key, parameterId] of MODEL_PARAMETER_IDS)
      coreModel.setParameterValueById(parameterId, modelParameters.value[key])

    options.onLoaded?.(stage)
  }

  const stage: Live2DStage = {
    get app() {
      return app
    },
    get model() {
      return model
    },
    binding,
    capabilities: () => capabilities,
    ready: () => loadPromise,

    async setMotion(group, index) {
      if (!model)
        return
      try {
        await model.motion(group, index, cubism?.MotionPriority.FORCE)
      }
      catch (error) {
        // A missing group is normal on models that do not ship per-emotion motions.
        console.warn(`[airi-bridge/live2d] motion "${group}" did not start`, error)
      }
    },

    setExpression(reference) {
      if (!model)
        return
      const manager = model.internalModel.motionManager.expressionManager
      if (!manager)
        return

      try {
        if (reference === null) {
          // MUST be resetExpression(), not setExpression(undefined).
          // pixi-live2d-display's setExpression runs `getExpressionIndex(undefined)`,
          // gets -1, and returns `false` — silently, without throwing. Clearing via
          // that path would leave the avatar stuck in its last emotion forever, and
          // the catch below would never fire. `neutral` maps to `expression: null` on
          // the demo model, so this is the difference between neutral working and the
          // avatar smiling for the rest of the lesson.
          manager.resetExpression()
          return
        }

        // setExpression resolves to false rather than throwing when the reference is
        // out of range, so a rejected promise is not the only failure mode to watch.
        void Promise.resolve(manager.setExpression(reference as never)).then((applied) => {
          if (applied === false) {
            console.warn(
              `[airi-bridge/live2d] expression "${String(reference)}" was rejected by the model `
              + `(out of range, or already active).`,
            )
          }
        })
      }
      catch (error) {
        console.warn(`[airi-bridge/live2d] expression "${String(reference)}" did not apply`, error)
      }
    },

    setEmotion(emotion) {
      const resolution = emotionResolver.resolve(emotion)
      switch (resolution.action.kind) {
        case 'expression':
          stage.setExpression(resolution.action.index)
          break
        case 'clear-expression':
          stage.setExpression(null)
          break
        case 'motion':
          void stage.setMotion(resolution.action.group)
          break
        case 'none':
          break
      }
      return resolution
    },

    setMouthOpen(value) {
      // Clamp only. `getMouthOpen()` returns 0…0.7 and the parameter wants 0…1;
      // rescaling here is the bug this comment exists to prevent.
      mouthOpenSize.value = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0
    },

    setSpeaking(speaking) {
      nowSpeaking.value = speaking
    },

    setFocus(x, y) {
      model?.focus(x, y)
      live2dEyeFocusSourceActive.value = true
    },

    resize(nextWidth, nextHeight) {
      width = nextWidth
      height = nextHeight
      if (!app)
        return
      app.renderer.resize(width * resolution, height * resolution)
      app.stage.scale.set(resolution)
      place()
    },

    destroy() {
      if (destroyed)
        return
      destroyed = true
      try {
        if (model && app) {
          app.stage.removeChild(model)
          model.destroy()
          model = undefined
        }
        app?.destroy(false)
        app = undefined
      }
      catch (error) {
        console.warn('[airi-bridge/live2d] teardown was not clean', error)
      }
    },
  }

  loadPromise = load()
  loadPromise.catch(fail)

  return stage
}

function isBinding(value: unknown): value is Live2DModelBinding {
  return (
    typeof value === 'object'
    && value !== null
    && 'emotionChannel' in value
    && 'motionGroups' in value
    && 'lipSync' in value
    && 'layout' in value
  )
}
