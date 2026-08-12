import type { ModelCapabilities } from './emotion-channel'
import type { Live2DModelBinding } from './model-binding'

import { describe, expect, it, vi } from 'vitest'

import { EMOTIONS } from '../contracts'
import { createEmotionResolver, resolveEmotionAction } from './emotion-channel'
import { buildExpressionIndex } from './expression-index'
import { DEFAULT_MODEL_BINDING, parseModelBinding } from './model-binding'

function binding(overrides: Partial<Live2DModelBinding> = {}): Live2DModelBinding {
  return { ...DEFAULT_MODEL_BINDING, id: 'test', modelPath: 'test.model3.json', ...overrides }
}

function capabilities(
  expressions: Array<{ Name?: string, File?: string }> = [],
  motionGroups: string[] = [],
): ModelCapabilities {
  return { expressions: buildExpressionIndex(expressions), motionGroups }
}

describe('resolveEmotionAction — the fallback chain', () => {
  const EXPRESSIONS = [
    { Name: 'e0', File: 'A.exp3.json' },
    { Name: 'e1', File: 'B.exp3.json' },
  ]

  it('1. takes the configured expression when the model has it', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({ emotionChannel: 'expression', emotionMap: { happy: { expression: 'B' } } }),
      capabilities(EXPRESSIONS, ['Idle']),
    )
    expect(result).toEqual({
      emotion: 'happy',
      action: { kind: 'expression', index: 1, id: 'B' },
      source: 'binding-expression',
    })
  })

  it('1b. treats an explicit null expression as "clear", not as "missing"', () => {
    const result = resolveEmotionAction(
      'neutral',
      binding({ emotionChannel: 'expression', emotionMap: { neutral: { expression: null } } }),
      capabilities(EXPRESSIONS, ['Idle']),
    )
    expect(result.action).toEqual({ kind: 'clear-expression' })
    expect(result.source).toBe('binding-clear-expression')
  })

  it('2. falls to the configured motion group when the expression is missing from the model', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({
        emotionChannel: 'expression',
        emotionMap: { happy: { expression: 'NOT_THERE', motion: 'Cheer' } },
      }),
      capabilities(EXPRESSIONS, ['Idle', 'Cheer']),
    )
    expect(result.action).toEqual({ kind: 'motion', group: 'Cheer' })
    expect(result.source).toBe('binding-motion')
  })

  it('2b. ignores the expression channel entirely when emotionChannel is motion', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({
        emotionChannel: 'motion',
        emotionMap: { happy: { expression: 'B', motion: 'Cheer' } },
      }),
      capabilities(EXPRESSIONS, ['Idle', 'Cheer']),
    )
    expect(result.action).toEqual({ kind: 'motion', group: 'Cheer' })
  })

  it('3. falls to the contract motion group when the binding names none', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({ emotionChannel: 'expression', emotionMap: { happy: {} } }),
      capabilities([], ['Idle', 'Happy']),
    )
    expect(result.action).toEqual({ kind: 'motion', group: 'Happy' })
    expect(result.source).toBe('contract-motion')
  })

  it('4. falls to motionGroups.fallback when the model has neither', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({
        emotionChannel: 'expression',
        emotionMap: { happy: { expression: 'NOT_THERE' } },
        motionGroups: { available: [], idle: 'Idle', fallback: 'Idle' },
      }),
      capabilities([], ['Idle', 'Tap']),
    )
    expect(result.action).toEqual({ kind: 'motion', group: 'Idle' })
    expect(result.source).toBe('fallback-motion')
  })

  it('5. gives up quietly when the model has nothing at all', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({
        emotionChannel: 'expression',
        emotionMap: { happy: { expression: 'NOT_THERE' } },
        motionGroups: { available: [], idle: 'Idle', fallback: 'Idle' },
      }),
      capabilities([], ['OnlyThis']),
    )
    expect(result.action).toEqual({ kind: 'none' })
    expect(result.source).toBe('unmapped')
  })

  it('never throws and never returns undefined, for any emotion or any binding', () => {
    const hostile = binding({
      emotionChannel: 'expression',
      emotionMap: {},
      motionGroups: { available: [], idle: '', fallback: '' },
    })
    for (const emotion of EMOTIONS) {
      expect(() => resolveEmotionAction(emotion, hostile, capabilities())).not.toThrow()
      expect(resolveEmotionAction(emotion, hostile, capabilities()).action).toBeDefined()
    }
  })

  it('trusts a group when neither the model nor the binding declared any', () => {
    // "We did not look" must not become "it does not exist".
    const result = resolveEmotionAction('happy', binding(), capabilities())
    expect(result.action).toEqual({ kind: 'motion', group: 'Happy' })
  })

  it('prefers what the model reports over what the binding declares', () => {
    const result = resolveEmotionAction(
      'happy',
      binding({ motionGroups: { available: ['Happy'], idle: 'Idle', fallback: 'Idle' } }),
      capabilities([], ['Idle']), // model really only has Idle
    )
    expect(result.action).toEqual({ kind: 'motion', group: 'Idle' })
    expect(result.source).toBe('fallback-motion')
  })
})

describe('createEmotionResolver — logging', () => {
  it('warns once per distinct unmapped emotion, not once per call', () => {
    const warn = vi.fn()
    const resolver = createEmotionResolver(
      binding({ motionGroups: { available: [], idle: 'Idle', fallback: 'Idle' } }),
      capabilities([], ['Idle', 'Tap']),
      { warn },
    )

    for (let i = 0; i < 10; i++) {
      resolver.resolve('happy')
      resolver.resolve('sad')
    }

    expect(warn).toHaveBeenCalledTimes(2)
    expect(resolver.degradedEmotions()).toEqual(['happy', 'sad'])
  })

  it('stays silent for emotions the model can express', () => {
    const warn = vi.fn()
    const resolver = createEmotionResolver(binding(), capabilities([], ['Idle', 'Happy']), { warn })
    resolver.resolve('happy')
    resolver.resolve('neutral')
    expect(warn).not.toHaveBeenCalled()
    expect(resolver.degradedEmotions()).toEqual([])
  })
})

describe('parseModelBinding — tolerance', () => {
  it('returns the contract default for junk input', () => {
    for (const junk of [null, undefined, 42, 'nope', []]) {
      const parsed = parseModelBinding(junk)
      expect(parsed.emotionChannel).toBe('motion')
      expect(parsed.motionGroups.fallback).toBe('Idle')
      expect(parsed.lipSync.parameter).toBe('ParamMouthOpenY')
    }
  })

  it('ignores $comment keys and unknown emotions', () => {
    const parsed = parseModelBinding({
      $comment: 'ignore me',
      id: 'x',
      modelPath: 'x.model3.json',
      emotionChannel: 'expression',
      emotionMap: {
        happy: { expression: 'F01' },
        sleepy: { expression: 'F02' },
        elated: 'not even an object',
      },
    })
    expect(Object.keys(parsed.emotionMap)).toEqual(['happy'])
  })

  it('keeps expression:null distinct from an absent expression key', () => {
    const parsed = parseModelBinding({
      emotionChannel: 'expression',
      emotionMap: { neutral: { expression: null }, happy: { motion: 'Happy' } },
    })
    expect('expression' in parsed.emotionMap.neutral!).toBe(true)
    expect(parsed.emotionMap.neutral!.expression).toBeNull()
    expect('expression' in parsed.emotionMap.happy!).toBe(false)
  })

  it('falls back to the contract table when emotionMap is empty', () => {
    // An expression-channel binding with no map would silently do nothing forever.
    const parsed = parseModelBinding({ emotionChannel: 'expression', emotionMap: {} })
    expect(parsed.emotionMap.happy?.motion).toBe('Happy')
    expect(parsed.emotionMap.neutral?.motion).toBe('Idle')
  })

  it('defaults fallback to idle when only idle is given', () => {
    const parsed = parseModelBinding({ motionGroups: { idle: 'Loop' } })
    expect(parsed.motionGroups.fallback).toBe('Loop')
  })

  it('accepts a numeric expression reference', () => {
    const parsed = parseModelBinding({
      emotionChannel: 'expression',
      emotionMap: { happy: { expression: 3 } },
    })
    expect(parsed.emotionMap.happy?.expression).toBe(3)
  })
})

describe('DEFAULT_MODEL_BINDING', () => {
  it('mirrors the contract table, including neutral → Idle', () => {
    expect(DEFAULT_MODEL_BINDING.emotionMap.neutral?.motion).toBe('Idle')
    expect(DEFAULT_MODEL_BINDING.emotionMap.happy?.motion).toBe('Happy')
    expect(DEFAULT_MODEL_BINDING.emotionMap.surprised?.motion).toBe('Surprise')
    expect(Object.keys(DEFAULT_MODEL_BINDING.emotionMap).sort()).toEqual([...EMOTIONS].sort())
  })
})
