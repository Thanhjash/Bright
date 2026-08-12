/**
 * Integration tests against the REAL Live2D model in `models/live2d/`.
 *
 * A passing unit test that never loaded a moc3 is not evidence. These tests load
 * `live2dcubismcore.min.js` and `haru_greeter_t03.moc3` for real (WebGL is not needed
 * to instantiate a Cubism model — only to draw one), read the real
 * `haru_greeter_t03.model3.json` and the real `bright-model.json`, and drive the
 * emotion resolver with capabilities discovered from those files rather than invented.
 *
 * They skip themselves if `models/live2d/` is absent, so the suite still runs in a
 * checkout without the model. The skip is loud.
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

import { beforeAll, describe, expect, it, vi } from 'vitest'

import { EMOTIONS } from '../contracts'
import { createEmotionResolver, resolveEmotionAction } from './emotion-channel'
import { buildExpressionIndex, resolveExpressionRef } from './expression-index'
import { DEFAULT_MODEL_BINDING, parseModelBinding } from './model-binding'

const MODEL_DIR = fileURLToPath(new URL('../../../../models/live2d/', import.meta.url))
const HAS_MODEL = existsSync(join(MODEL_DIR, 'bright-model.json'))

if (!HAS_MODEL) {
  console.warn(
    `[airi-bridge] real-model tests SKIPPED: no model at ${MODEL_DIR}. `
    + `The emotion-channel unit tests still ran, but nothing here loaded a moc3.`,
  )
}

interface CubismCore {
  Version: { csmGetVersion: () => number }
  Logging: { csmSetLogFunction: (fn: (message: string) => void) => void }
  Moc: { fromArrayBuffer: (buffer: ArrayBuffer) => unknown }
  Model: {
    fromMoc: (moc: unknown) => {
      parameters: {
        ids: string[]
        minimumValues: Float32Array
        maximumValues: Float32Array
        values: Float32Array
      }
      drawables: { ids: string[] }
      update: () => void
    }
  }
}

/**
 * Loads the Cubism core in a Node VM.
 *
 * The core is an Emscripten bundle that expects a browser: it reads
 * `document.currentScript`, decodes its embedded WASM with `atob`, and instantiates
 * asynchronously. Supplying those four globals is enough — no jsdom, no WebGL.
 */
async function loadCubismCore(): Promise<CubismCore> {
  const source = readFileSync(join(MODEL_DIR, 'live2dcubismcore.min.js'), 'utf8')

  const sandbox: Record<string, unknown> = {
    console,
    TextDecoder,
    TextEncoder,
    WebAssembly,
    performance,
    setTimeout,
    clearTimeout,
    atob: (value: string) => Buffer.from(value, 'base64').toString('binary'),
    btoa: (value: string) => Buffer.from(value, 'binary').toString('base64'),
    document: { currentScript: { src: 'file:///live2dcubismcore.min.js' } },
    location: { href: 'file:///' },
  }
  sandbox.window = sandbox
  sandbox.self = sandbox
  sandbox.globalThis = sandbox

  const context = vm.createContext(sandbox)
  vm.runInContext(source, context, { filename: 'live2dcubismcore.min.js' })

  const core = context.Live2DCubismCore as CubismCore
  expect(core, 'the Cubism core did not export Live2DCubismCore').toBeTruthy()

  // WASM instantiation is async. Poll until the module answers.
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      if (core.Version.csmGetVersion() > 0)
        return core
    }
    catch {
      // not ready yet
    }
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  throw new Error('Cubism core did not finish initialising')
}

function readJson(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(MODEL_DIR, name), 'utf8'))
}

describe.skipIf(!HAS_MODEL)('real model — haru_greeter_t03', () => {
  let core: CubismCore
  let modelJson: Record<string, any>
  let bindingJson: Record<string, unknown>

  beforeAll(async () => {
    core = await loadCubismCore()
    modelJson = readJson('haru_greeter_t03.model3.json')
    // The Haru-specific block reads a FIXTURE, not the shipping binding.
    // What ships is Hiyori (see the block below); Haru is retained only
    // because its Name/File off-by-one is worth a regression test.
    bindingJson = readJson('haru.bright-model.json')
  }, 30_000)

  describe('the moc3 actually loads', () => {
    it('instantiates a Cubism model from the real moc3', () => {
      const file = readFileSync(join(MODEL_DIR, 'haru_greeter_t03.moc3'))
      const moc = core.Moc.fromArrayBuffer(
        file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength),
      )
      const model = core.Model.fromMoc(moc)

      expect(model.parameters.ids.length).toBeGreaterThan(0)
      expect(model.drawables.ids.length).toBeGreaterThan(0)
    })

    it('confirms THE SCALE TRAP: the lip-sync parameter is 0…1 and takes 0.7 raw', () => {
      // PROTOCOL.md §6.5. `getMouthOpen()` returns 0…0.7. Written raw, 0.7 is a wide
      // open mouth. Rescaled to 0-100 it would clamp to 1 and the mouth would be
      // pinned open for the whole utterance — the exact bug the invariant prevents.
      const file = readFileSync(join(MODEL_DIR, 'haru_greeter_t03.moc3'))
      const model = core.Model.fromMoc(core.Moc.fromArrayBuffer(
        file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength),
      ))

      const binding = parseModelBinding(bindingJson)
      const index = model.parameters.ids.indexOf(binding.lipSync.parameter)
      expect(index, `${binding.lipSync.parameter} is not a parameter of this model`).toBeGreaterThanOrEqual(0)

      expect(model.parameters.minimumValues[index]).toBe(0)
      expect(model.parameters.maximumValues[index]).toBe(1)
      expect(binding.lipSync.range).toEqual([0, 1])

      model.parameters.values[index] = 0.7
      model.update()
      expect(model.parameters.values[index]).toBeCloseTo(0.7, 5)

      // And the counterfactual: the "rescale to 0-100" bug saturates the parameter.
      model.parameters.values[index] = 70
      model.update()
      expect(model.parameters.values[index]).toBe(1)
    })

    it('declares the lip-sync parameter in the model LipSync group', () => {
      const binding = parseModelBinding(bindingJson)
      const lipSyncGroup = (modelJson.Groups as Array<{ Name: string, Ids: string[] }>)
        .find(group => group.Name === 'LipSync')
      expect(lipSyncGroup?.Ids).toContain(binding.lipSync.parameter)
    })
  })

  describe('the finding that motivated config-driven emotions', () => {
    it('has motion groups Idle and Tap ONLY — no per-emotion groups', () => {
      const groups = Object.keys(modelJson.FileReferences.Motions)
      expect(groups.sort()).toEqual(['Idle', 'Tap'])

      // Which means the contract table misses on eight of nine emotions here.
      for (const emotion of EMOTIONS) {
        if (emotion === 'neutral')
          continue
        expect(groups).not.toContain(
          DEFAULT_MODEL_BINDING.emotionMap[emotion]?.motion,
        )
      }
    })

    it('degrades every non-neutral emotion to Idle under the CONTRACT default binding', () => {
      // This is the silent failure the binding file exists to prevent: with no
      // binding, the avatar would look like it worked while doing nothing distinct.
      const contractBinding = {
        ...DEFAULT_MODEL_BINDING,
        id: 'haru-contract-default',
        modelPath: 'haru_greeter_t03.model3.json',
      }
      const capabilities = {
        expressions: buildExpressionIndex(modelJson.FileReferences.Expressions),
        motionGroups: Object.keys(modelJson.FileReferences.Motions),
      }

      const happy = resolveEmotionAction('happy', contractBinding, capabilities)
      expect(happy.source).toBe('fallback-motion')
      expect(happy.action).toEqual({ kind: 'motion', group: 'Idle' })

      // neutral is the one that survives, because the contract maps it to Idle and
      // this model has Idle. `binding-motion` rather than `contract-motion` because
      // DEFAULT_MODEL_BINDING materialises the contract table INTO an emotionMap, so
      // step 2 of the chain matches before step 3 ever runs. Either way it is not a
      // degraded resolution — which is the part that matters.
      const neutral = resolveEmotionAction('neutral', contractBinding, capabilities)
      expect(neutral.source).toBe('binding-motion')
      expect(neutral.action).toEqual({ kind: 'motion', group: 'Idle' })

      // Nothing ever dead-ends, even in the degraded case.
      for (const emotion of EMOTIONS)
        expect(resolveEmotionAction(emotion, contractBinding, capabilities).action.kind).not.toBe('none')
    })
  })

  describe('bright-model.json against the real model files', () => {
    it('parses into an expression-channel binding covering all nine emotions', () => {
      const binding = parseModelBinding(bindingJson)
      expect(binding.emotionChannel).toBe('expression')
      expect(binding.id).toBe('haru_greeter_t03')
      for (const emotion of EMOTIONS)
        expect(binding.emotionMap[emotion], `no mapping for ${emotion}`).toBeDefined()
    })

    it('references only expressions the model actually declares and ships', () => {
      const binding = parseModelBinding(bindingJson)
      const index = buildExpressionIndex(modelJson.FileReferences.Expressions)
      const filesOnDisk = readdirSync(join(MODEL_DIR, 'expressions'))

      for (const emotion of EMOTIONS) {
        const reference = binding.emotionMap[emotion]?.expression
        if (reference === null || reference === undefined)
          continue

        const resolved = resolveExpressionRef(index, reference)
        expect(resolved, `${emotion} → "${String(reference)}" is not an expression of this model`).toBeTruthy()
        expect(filesOnDisk).toContain(`${resolved!.file}.exp3.json`)
      }
    })

    it('resolves the Name/file-basename off-by-one that would silently shift every emotion', () => {
      // model3.json pairs Name "f04" with File "expressions/F05.exp3.json". A human
      // writes "F05"; naive Name matching would land on f05 → F06 — one emotion off,
      // and it would still "work".
      const index = buildExpressionIndex(modelJson.FileReferences.Expressions)

      const byFile = resolveExpressionRef(index, 'F05')
      expect(byFile).toMatchObject({ index: 4, name: 'f04', file: 'F05' })

      const byName = resolveExpressionRef(index, 'f04')
      expect(byName?.index).toBe(4)

      expect(resolveExpressionRef(index, 'F99')).toBeUndefined()
    })

    it('drives all nine emotions through the expression channel with no fallback', () => {
      const binding = parseModelBinding(bindingJson)
      const capabilities = {
        expressions: buildExpressionIndex(modelJson.FileReferences.Expressions),
        motionGroups: Object.keys(modelJson.FileReferences.Motions),
      }

      const warn = vi.fn()
      const resolver = createEmotionResolver(binding, capabilities, { warn })

      for (const emotion of EMOTIONS) {
        const resolution = resolver.resolve(emotion)
        expect(
          ['binding-expression', 'binding-clear-expression'],
          `${emotion} resolved via ${resolution.source}`,
        ).toContain(resolution.source)
      }

      expect(resolver.resolve('happy').action).toEqual({ kind: 'expression', index: 4, id: 'F05' })
      expect(resolver.resolve('neutral').action).toEqual({ kind: 'clear-expression' })

      // A fully mapped model must produce no warnings at all.
      expect(resolver.degradedEmotions()).toEqual([])
      expect(warn).not.toHaveBeenCalled()
    })

    it('declares motion groups matching what the model ships', () => {
      const binding = parseModelBinding(bindingJson)
      expect(binding.motionGroups.available.sort())
        .toEqual(Object.keys(modelJson.FileReferences.Motions).sort())
      expect(binding.motionGroups.idle).toBe('Idle')
      expect(Object.keys(modelJson.FileReferences.Motions)).toContain(binding.motionGroups.fallback)
    })

    it('points at a model file that exists', () => {
      const binding = parseModelBinding(bindingJson)
      expect(existsSync(join(MODEL_DIR, binding.modelPath))).toBe(true)
      expect(binding.cubismCore && existsSync(join(MODEL_DIR, binding.cubismCore))).toBe(true)
    })

    it('carries a licence block, because shipping this model is not yet decided', () => {
      const binding = parseModelBinding(bindingJson)
      expect(binding.license).toBeDefined()
      expect(String(binding.license?.commercialUse)).toMatch(/RESTRICTED/i)
    })
  })
})
