import { describe, expect, it } from 'vitest'

import { EMOTIONS } from '../contracts'
import {
  isActToken,
  isDelayToken,
  parseAct,
  parseDelay,
  parseSignal,
  resolveEmotion,
} from './parse-act'

describe('parseAct — emotion shapes (PROTOCOL.md §5)', () => {
  it('accepts a bare emotion string and defaults intensity to 1', () => {
    expect(parseAct('<|ACT {"emotion":"happy"}|>')).toEqual({
      emotion: { name: 'happy', intensity: 1 },
    })
  })

  it('accepts { name, intensity }', () => {
    expect(parseAct('<|ACT {"emotion":{"name":"think","intensity":0.6}}|>')).toEqual({
      emotion: { name: 'think', intensity: 0.6 },
    })
  })

  it('accepts intensity as a numeric STRING', () => {
    // Streamed payloads frequently arrive serialised.
    expect(parseAct('<|ACT {"emotion":{"name":"sad","intensity":"0.25"}}|>')).toEqual({
      emotion: { name: 'sad', intensity: 0.25 },
    })
  })

  it('clamps intensity into [0,1]', () => {
    expect(parseAct('<|ACT {"emotion":{"name":"angry","intensity":5}}|>'))
      .toEqual({ emotion: { name: 'angry', intensity: 1 } })
    expect(parseAct('<|ACT {"emotion":{"name":"angry","intensity":-3}}|>'))
      .toEqual({ emotion: { name: 'angry', intensity: 0 } })
    expect(parseAct('<|ACT {"emotion":{"name":"angry","intensity":"12"}}|>'))
      .toEqual({ emotion: { name: 'angry', intensity: 1 } })
  })

  it('falls back to intensity 1 when intensity is unparseable', () => {
    expect(parseAct('<|ACT {"emotion":{"name":"curious","intensity":"loud"}}|>'))
      .toEqual({ emotion: { name: 'curious', intensity: 1 } })
    expect(parseAct('<|ACT {"emotion":{"name":"curious","intensity":null}}|>'))
      .toEqual({ emotion: { name: 'curious', intensity: 1 } })
    expect(parseAct('<|ACT {"emotion":{"name":"curious"}}|>'))
      .toEqual({ emotion: { name: 'curious', intensity: 1 } })
  })

  it('normalises case and surrounding whitespace in the emotion name', () => {
    expect(parseAct('<|ACT {"emotion":" HAPPY "}|>'))
      .toEqual({ emotion: { name: 'happy', intensity: 1 } })
    expect(parseAct('<|ACT {"emotion":{"name":"Surprised"}}|>'))
      .toEqual({ emotion: { name: 'surprised', intensity: 1 } })
  })

  it('accepts all nine contract emotions and nothing else', () => {
    for (const emotion of EMOTIONS) {
      expect(parseAct(`<|ACT {"emotion":"${emotion}"}|>`))
        .toEqual({ emotion: { name: emotion, intensity: 1 } })
    }
    // 'surprise' (no d), 'joy', 'excited' are near misses that must not resolve.
    for (const bogus of ['surprise', 'joy', 'excited', 'thinking', '']) {
      expect(parseAct(`<|ACT {"emotion":"${bogus}"}|>`)).toEqual({})
    }
  })

  it('drops an unknown emotion but keeps the motion on the same token', () => {
    expect(parseAct('<|ACT {"emotion":"sleepy","motion":"nod"}|>'))
      .toEqual({ motion: 'nod' })
  })

  it('rejects a non-object emotion payload', () => {
    expect(parseAct('<|ACT {"emotion":42}|>')).toEqual({})
    expect(parseAct('<|ACT {"emotion":["happy"]}|>')).toEqual({})
    expect(parseAct('<|ACT {"emotion":null}|>')).toEqual({})
  })
})

describe('parseAct — motion', () => {
  it('trims the motion string', () => {
    expect(parseAct('<|ACT {"motion":"  nod  "}|>')).toEqual({ motion: 'nod' })
  })

  it('drops an empty or non-string motion', () => {
    expect(parseAct('<|ACT {"motion":"   "}|>')).toEqual({})
    expect(parseAct('<|ACT {"motion":7}|>')).toEqual({})
  })

  it('carries emotion and motion together', () => {
    expect(parseAct('<|ACT {"emotion":"happy","motion":"Wave"}|>')).toEqual({
      emotion: { name: 'happy', intensity: 1 },
      motion: 'Wave',
    })
  })
})

describe('parseAct — malformed tokens', () => {
  it('returns undefined for a non-ACT token', () => {
    expect(parseAct('<|DELAY 1.5|>')).toBeUndefined()
    expect(parseAct('<|CALL ["x"]|>')).toBeUndefined()
    expect(parseAct('just text')).toBeUndefined()
  })

  it('returns undefined for invalid JSON', () => {
    expect(parseAct('<|ACT {"emotion":}|>')).toBeUndefined()
    expect(parseAct('<|ACT not json|>')).toBeUndefined()
  })

  it('returns undefined when the body is not a JSON object', () => {
    expect(parseAct('<|ACT ["happy"]|>')).toBeUndefined()
    expect(parseAct('<|ACT "happy"|>')).toBeUndefined()
    expect(parseAct('<|ACT 3|>')).toBeUndefined()
  })

  it('returns an empty payload for a well-formed but empty ACT', () => {
    expect(parseAct('<|ACT {}|>')).toEqual({})
  })

  it('requires the space after ACT', () => {
    expect(parseAct('<|ACT{"emotion":"happy"}|>')).toBeUndefined()
  })

  it('tolerates whitespace around the whole token', () => {
    expect(parseAct('  <|ACT {"emotion":"happy"}|>  '))
      .toEqual({ emotion: { name: 'happy', intensity: 1 } })
  })
})

describe('parseDelay', () => {
  it('accepts the SPACE separated form', () => {
    expect(parseDelay('<|DELAY 1.5|>')).toBe(1.5)
    expect(parseDelay('<|DELAY 2|>')).toBe(2)
    expect(parseDelay('<|DELAY 0.25|>')).toBe(0.25)
  })

  it('REJECTS the colon separated form', () => {
    // The single most common misreading of the grammar. PROTOCOL.md §5.
    expect(parseDelay('<|DELAY:1.5|>')).toBeUndefined()
    expect(isDelayToken('<|DELAY:1.5|>')).toBe(false)
  })

  it('rejects zero, negatives and non-numbers', () => {
    expect(parseDelay('<|DELAY 0|>')).toBeUndefined()
    expect(parseDelay('<|DELAY -1|>')).toBeUndefined()
    expect(parseDelay('<|DELAY soon|>')).toBeUndefined()
    expect(parseDelay('<|DELAY |>')).toBeUndefined()
    expect(parseDelay('<|DELAY 1e3|>')).toBeUndefined()
  })

  it('returns undefined for a non-DELAY token', () => {
    expect(parseDelay('<|ACT {"emotion":"happy"}|>')).toBeUndefined()
  })
})

describe('isActToken / isDelayToken', () => {
  it('recognises well-formed tokens by syntax alone', () => {
    expect(isActToken('<|ACT {"emotion":"happy"}|>')).toBe(true)
    expect(isActToken('<|ACT garbage|>')).toBe(true) // syntax yes, payload no
    expect(isActToken('<|DELAY 1|>')).toBe(false)
    expect(isDelayToken('<|DELAY 1|>')).toBe(true)
  })
})

describe('parseSignal', () => {
  it('discriminates ACT, DELAY and unknown', () => {
    expect(parseSignal('<|ACT {"emotion":"happy"}|>')).toEqual({
      kind: 'act',
      act: { emotion: { name: 'happy', intensity: 1 } },
      raw: '<|ACT {"emotion":"happy"}|>',
    })
    expect(parseSignal('<|DELAY 1.5|>')).toEqual({
      kind: 'delay',
      seconds: 1.5,
      raw: '<|DELAY 1.5|>',
    })
    expect(parseSignal('<|CALL ["plugin.x"]|>').kind).toBe('unknown')
    expect(parseSignal('<|ACT bad json|>').kind).toBe('unknown')
  })
})

describe('resolveEmotion', () => {
  it('normalises both contract emotion shapes', () => {
    expect(resolveEmotion({ emotion: 'happy' })).toEqual({ name: 'happy', intensity: 1 })
    expect(resolveEmotion({ emotion: { name: 'sad', intensity: 0.4 } }))
      .toEqual({ name: 'sad', intensity: 0.4 })
  })

  it('clamps and repairs a hand-built payload', () => {
    expect(resolveEmotion({ emotion: { name: 'angry', intensity: 9 } }))
      .toEqual({ name: 'angry', intensity: 1 })
    expect(resolveEmotion({ emotion: { name: 'angry', intensity: Number.NaN } }))
      .toEqual({ name: 'angry', intensity: 1 })
  })

  it('returns undefined when there is no emotion', () => {
    expect(resolveEmotion(undefined)).toBeUndefined()
    expect(resolveEmotion({})).toBeUndefined()
    expect(resolveEmotion({ motion: 'nod' })).toBeUndefined()
  })
})
