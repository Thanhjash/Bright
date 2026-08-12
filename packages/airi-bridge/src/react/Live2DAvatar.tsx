/**
 * `<Live2DAvatar>` — the React face of `createLive2DStage`.
 *
 * The component owns a canvas and a stage; React state never drives the render loop.
 * Props are pushed into the stage through effects, and the mouth is sampled every
 * animation frame from the `getMouthOpen` function you pass in. Re-rendering this
 * component sixty times a second to animate a mouth would be the wrong shape, so it
 * does not: the only thing that re-renders is the loading/error overlay.
 *
 * AIRI's `Model.vue` is the reference for what happens inside; none of its Vue
 * reactivity is reproduced here.
 */

import type { CSSProperties, ReactNode } from 'react'

import type { Emotion } from '../contracts'
import type { Live2DModelBinding } from '../live2d'
import type { Live2DStage, Live2DStageOptions } from '../live2d'

import { useEffect, useRef, useState } from 'react'

import { createLive2DStage, ensureCubismCore, loadModelBinding } from '../live2d'

export interface Live2DAvatarProps {
  /** URL of the model entry file (`*.model3.json`). Required. */
  model: string
  /**
   * Per-model binding: a `Live2DModelBinding`, or a URL to a `bright-model.json`.
   *
   * Omit and the contract table (`EMOTION_MOTION_GROUP`) is used — correct for a
   * model that ships per-emotion motion groups, silently inert for one that does
   * not. Supply a binding for any real model.
   */
  binding?: Live2DModelBinding | string
  /**
   * URL of `live2dcubismcore.min.js`. Loaded before the model if given.
   *
   * The Cubism core is not on npm and cannot be bundled — Live2D's licence forbids
   * redistribution. Either pass it here or load it with a `<script>` tag yourself.
   */
  cubismCore?: string
  /** Current emotion. Dispatched through the binding's channel with full fallback. */
  emotion?: Emotion
  /**
   * True for the whole utterance, including the silent gaps between phonemes.
   * Drives the lip-sync release tail and the forced mouth-close handoff.
   */
  speaking?: boolean
  /**
   * Sampled every frame for the mouth position. Pass `player.getMouthOpen` from
   * `useSpeechPlayer`. Returns 0…0.7 and is written RAW — do not rescale it.
   */
  getMouthOpen?: () => number
  className?: string
  style?: CSSProperties
  /** Rendered over the canvas while the model loads. */
  fallback?: ReactNode
  /** Rendered over the canvas if loading fails. Receives the error. */
  renderError?: (error: Error) => ReactNode
  stageOptions?: Omit<Live2DStageOptions, 'model' | 'binding' | 'onLoaded' | 'onError'>
  onReady?: (stage: Live2DStage) => void
  onError?: (error: Error) => void
}

/**
 * @example
 * const player = useSpeechPlayer({ tts })
 * <Live2DAvatar
 *   model="/models/live2d/haru_greeter_t03.model3.json"
 *   binding="/models/live2d/bright-model.json"
 *   cubismCore="/models/live2d/live2dcubismcore.min.js"
 *   emotion={emotion}
 *   speaking={player.speaking}
 *   getMouthOpen={player.getMouthOpen}
 * />
 */
export function Live2DAvatar(props: Live2DAvatarProps) {
  const {
    model,
    binding,
    cubismCore,
    emotion,
    speaking = false,
    getMouthOpen,
    className,
    style,
    fallback,
    renderError,
    stageOptions,
    onReady,
    onError,
  } = props

  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const stageRef = useRef<Live2DStage | null>(null)

  // Held in refs so the render-loop effect never restarts when a callback identity
  // changes. Tearing down a WebGL stage because a parent re-rendered is a real bug.
  const getMouthOpenRef = useRef(getMouthOpen)
  getMouthOpenRef.current = getMouthOpen
  const onReadyRef = useRef(onReady)
  onReadyRef.current = onReady
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError
  const stageOptionsRef = useRef(stageOptions)
  stageOptionsRef.current = stageOptions

  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<Error | null>(null)

  // Create / destroy the stage. Only the identity of the model and its binding may
  // cause a reload.
  const bindingKey = typeof binding === 'string' ? binding : binding?.id
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container)
      return

    let disposed = false
    let stage: Live2DStage | undefined

    setStatus('loading')
    setError(null)

    const fail = (cause: unknown) => {
      const wrapped = cause instanceof Error ? cause : new Error(String(cause))
      if (disposed)
        return
      setError(wrapped)
      setStatus('error')
      onErrorRef.current?.(wrapped)
    }

    void (async () => {
      try {
        if (cubismCore)
          await ensureCubismCore(cubismCore)
        if (disposed)
          return

        // ZIP models need the zip loader, and it must be imported DYNAMICALLY,
        // here — after the Cubism Core script is in the document.
        //
        // The loader patches pixi-live2d-display's static `ZipLoader`, so
        // importing it pulls that module in. A static `import` at the top of a
        // consumer file therefore evaluates pixi-live2d-display before
        // `ensureCubismCore` has run, and the plugin throws
        // "Could not find Cubism 4 runtime". Auto-detecting the `.zip` here
        // removes the footgun entirely rather than documenting it.
        if (/\.zip(?:[?#]|$)/i.test(model))
          await import('../live2d/live2d-zip-loader')
        if (disposed)
          return

        const resolvedBinding = typeof binding === 'string'
          ? await loadModelBinding(binding)
          : binding
        if (disposed)
          return

        const rect = container.getBoundingClientRect()
        stage = createLive2DStage(canvas, {
          ...stageOptionsRef.current,
          model,
          binding: resolvedBinding,
          width: Math.max(1, Math.round(rect.width)),
          height: Math.max(1, Math.round(rect.height)),
          onError: fail,
        })
        stageRef.current = stage

        await stage.ready()
        if (disposed)
          return

        setStatus('ready')
        onReadyRef.current?.(stage)
      }
      catch (cause) {
        fail(cause)
      }
    })()

    return () => {
      disposed = true
      stageRef.current = null
      stage?.destroy()
    }
  }, [model, bindingKey, cubismCore])

  // Track container size. The stage renders at `resolution`x internally, so this is
  // about layout, not sharpness.
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof ResizeObserver === 'undefined')
      return

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (width > 0 && height > 0)
        stageRef.current?.resize(Math.round(width), Math.round(height))
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Emotion. Runs after `status` flips to ready so the first emotion is not lost to
  // a model that had not finished loading.
  useEffect(() => {
    if (status !== 'ready' || !emotion)
      return
    stageRef.current?.setEmotion(emotion)
  }, [emotion, status])

  useEffect(() => {
    stageRef.current?.setSpeaking(speaking)
  }, [speaking, status])

  // The mouth. One rAF loop for the life of the component, reading through a ref.
  useEffect(() => {
    if (typeof requestAnimationFrame === 'undefined')
      return

    let frame = 0
    const tick = () => {
      const read = getMouthOpenRef.current
      if (read)
        stageRef.current?.setMouthOpen(read())
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'relative', width: '100%', height: '100%', ...style }}
    >
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block', objectFit: 'contain' }}
      />
      {status === 'loading' && fallback}
      {status === 'error' && error && renderError?.(error)}
    </div>
  )
}
