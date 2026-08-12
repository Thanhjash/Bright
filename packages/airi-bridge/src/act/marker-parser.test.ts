import { describe, expect, it } from 'vitest'

import { TAG_TAIL_RETAIN } from '../contracts'
import { createMarkerParser, createMarkerParserWithHandlers, parseMarkerText } from './marker-parser'

interface Collected {
  literals: string[]
  specials: string[]
  /** everything the user would hear, in order */
  spoken: string
}

/** Feeds `chunks` in order and returns what came out. */
async function run(chunks: string[]): Promise<Collected> {
  const literals: string[] = []
  const specials: string[] = []

  const parser = createMarkerParser((event) => {
    if (event.type === 'literal')
      literals.push(event.text)
    else
      specials.push(event.raw)
  })

  for (const chunk of chunks)
    await parser.consume(chunk)
  await parser.end()

  return { literals, specials, spoken: literals.join('') }
}

/** Every way of cutting `text` into two chunks, including the degenerate ends. */
function allTwoWaySplits(text: string): [string, string][] {
  const splits: [string, string][] = []
  for (let i = 0; i <= text.length; i++)
    splits.push([text.slice(0, i), text.slice(i)])
  return splits
}

/** Every way of cutting `text` into three chunks. */
function allThreeWaySplits(text: string): [string, string, string][] {
  const splits: [string, string, string][] = []
  for (let i = 0; i <= text.length; i++) {
    for (let j = i; j <= text.length; j++)
      splits.push([text.slice(0, i), text.slice(i, j), text.slice(j)])
  }
  return splits
}

describe('createMarkerParser — the single-chunk baseline', () => {
  it('passes plain text straight through', async () => {
    const { spoken, specials } = await run(['Good morning, class.'])
    expect(spoken).toBe('Good morning, class.')
    expect(specials).toEqual([])
  })

  it('splits an ACT token out of surrounding text', async () => {
    const { spoken, specials } = await run(['Hello <|ACT {"emotion":"happy"}|> world'])
    expect(spoken).toBe('Hello  world')
    expect(specials).toEqual(['<|ACT {"emotion":"happy"}|>'])
  })

  it('handles a token at the very start and the very end', async () => {
    const { spoken, specials } = await run(['<|ACT {"emotion":"think"}|>hi<|DELAY 1.5|>'])
    expect(spoken).toBe('hi')
    expect(specials).toEqual(['<|ACT {"emotion":"think"}|>', '<|DELAY 1.5|>'])
  })

  it('handles back-to-back tokens with nothing between them', async () => {
    const { spoken, specials } = await run(['a<|DELAY 1|><|ACT {"motion":"nod"}|>b'])
    expect(spoken).toBe('ab')
    expect(specials).toEqual(['<|DELAY 1|>', '<|ACT {"motion":"nod"}|>'])
  })

  it('keeps text shorter than the retained tail until the stream ends', async () => {
    const literals: string[] = []
    const parser = createMarkerParserWithHandlers({ onLiteral: t => void literals.push(t) })

    await parser.consume('ok')
    expect(literals).toEqual([]) // 2 chars < TAG_TAIL_RETAIN, still held back

    await parser.end()
    expect(literals.join('')).toBe('ok')
  })
})

describe('createMarkerParser — chunk splitting (PROTOCOL.md §5 requirement 1)', () => {
  // The whole reason TAG_TAIL_RETAIN exists. A token cut anywhere must produce
  // byte-identical spoken text and exactly one special, no matter where the cut lands.
  const CASES: { name: string, text: string, spoken: string, specials: string[] }[] = [
    {
      name: 'ACT with emotion',
      text: 'Nice work <|ACT {"emotion":"happy"}|> everyone',
      spoken: 'Nice work  everyone',
      specials: ['<|ACT {"emotion":"happy"}|>'],
    },
    {
      name: 'ACT with object emotion and motion',
      text: 'Hmm <|ACT {"emotion":{"name":"think","intensity":0.6},"motion":"nod"}|> let me see',
      spoken: 'Hmm  let me see',
      specials: ['<|ACT {"emotion":{"name":"think","intensity":0.6},"motion":"nod"}|>'],
    },
    {
      name: 'DELAY',
      text: 'Ready<|DELAY 1.5|>go',
      spoken: 'Readygo',
      specials: ['<|DELAY 1.5|>'],
    },
    {
      name: 'token at index 0',
      text: '<|ACT {"emotion":"neutral"}|>Welcome back.',
      spoken: 'Welcome back.',
      specials: ['<|ACT {"emotion":"neutral"}|>'],
    },
    {
      name: 'token at the end',
      text: 'All done.<|ACT {"emotion":"happy"}|>',
      spoken: 'All done.',
      specials: ['<|ACT {"emotion":"happy"}|>'],
    },
    {
      name: 'two tokens far apart',
      text: 'a<|ACT {"emotion":"sad"}|>bbbbbbbbbb<|DELAY 2|>c',
      spoken: 'abbbbbbbbbbc',
      specials: ['<|ACT {"emotion":"sad"}|>', '<|DELAY 2|>'],
    },
    {
      name: 'JSON containing a pipe and an angle bracket',
      text: 'x<|ACT {"motion":"a|b<c"}|>y',
      spoken: 'xy',
      specials: ['<|ACT {"motion":"a|b<c"}|>'],
    },
  ]

  for (const testCase of CASES) {
    it(`never leaks ${testCase.name} at any 2-way split point`, async () => {
      for (const [head, tail] of allTwoWaySplits(testCase.text)) {
        const { spoken, specials } = await run([head, tail])
        expect(spoken, `split after ${head.length} chars: ${JSON.stringify([head, tail])}`)
          .toBe(testCase.spoken)
        expect(specials, `split after ${head.length} chars`).toEqual(testCase.specials)
      }
    })
  }

  it('never leaks an ACT token at any 3-way split point', async () => {
    const text = 'Hi <|ACT {"emotion":"happy","motion":"nod"}|> there'
    for (const chunks of allThreeWaySplits(text)) {
      const { spoken, specials } = await run(chunks)
      expect(spoken, JSON.stringify(chunks)).toBe('Hi  there')
      expect(specials, JSON.stringify(chunks)).toEqual(['<|ACT {"emotion":"happy","motion":"nod"}|>'])
    }
  })

  it('never leaks when every character arrives as its own chunk', async () => {
    const text = 'One<|ACT {"emotion":"surprised"}|>two<|DELAY 0.5|>three'
    const { spoken, specials } = await run([...text])
    expect(spoken).toBe('Onetwothree')
    expect(specials).toEqual(['<|ACT {"emotion":"surprised"}|>', '<|DELAY 0.5|>'])
  })

  it('holds back exactly TAG_TAIL_RETAIN characters while scanning', async () => {
    const literals: string[] = []
    const parser = createMarkerParser((e) => {
      if (e.type === 'literal')
        literals.push(e.text)
    })

    await parser.consume('abcdefghij') // 10 chars
    expect(literals.join('')).toBe('abcdefghij'.slice(0, 10 - TAG_TAIL_RETAIN))
    expect(literals.join('')).toBe('abcde')

    await parser.end()
    expect(literals.join('')).toBe('abcdefghij')
  })

  it('does not emit a lone `<` that turns out to open a token', async () => {
    const { spoken, specials } = await run(['ready<', '|ACT {"emotion":"happy"}|>'])
    expect(spoken).toBe('ready')
    expect(specials).toEqual(['<|ACT {"emotion":"happy"}|>'])
  })

  it('does not emit a `<|AC` prefix that turns out to open a token', async () => {
    const { spoken, specials } = await run(['ready<|AC', 'T {"emotion":"happy"}|>done'])
    expect(spoken).toBe('readydone')
    expect(specials).toEqual(['<|ACT {"emotion":"happy"}|>'])
  })

  it('does not emit a token whose closer is split across chunks', async () => {
    const { spoken, specials } = await run(['<|ACT {"emotion":"happy"}|', '>ok'])
    expect(spoken).toBe('ok')
    expect(specials).toEqual(['<|ACT {"emotion":"happy"}|>'])
  })
})

describe('createMarkerParser — unterminated tokens are dropped, never spoken', () => {
  it('drops a bare opener at stream end', async () => {
    const { spoken, specials } = await run(['Say something <|'])
    expect(spoken).toBe('Say something ')
    expect(specials).toEqual([])
  })

  it('drops a half-written ACT token at stream end', async () => {
    const { spoken, specials } = await run(['Say something <|ACT {"emotion":"hap'])
    expect(spoken).toBe('Say something ')
    expect(specials).toEqual([])
  })

  it('drops a token that lost its closer across several chunks', async () => {
    const { spoken, specials } = await run(['ok <|ACT ', '{"emotion":', '"happy"}'])
    expect(spoken).toBe('ok ')
    expect(specials).toEqual([])
  })

  it('reports being mid-token so callers can tell why nothing was flushed', async () => {
    const parser = createMarkerParser(() => {})
    await parser.consume('hello <|ACT {')
    expect(parser.isInToken()).toBe(true)
    await parser.end()
    expect(parser.isInToken()).toBe(false)
  })

  it('recovers after end() so the parser can serve the next turn', async () => {
    const literals: string[] = []
    const parser = createMarkerParserWithHandlers({ onLiteral: t => void literals.push(t) })

    await parser.consume('turn one <|ACT {')
    await parser.end()
    await parser.consume('turn two')
    await parser.end()

    expect(literals.join('')).toBe('turn one turn two')
  })

  it('drops buffered state on reset()', async () => {
    const literals: string[] = []
    const parser = createMarkerParserWithHandlers({ onLiteral: t => void literals.push(t) })

    await parser.consume('abandoned text')
    parser.reset()
    await parser.end()

    // 'abandoned text' is 14 chars; 5 were still held as the tail when reset() hit.
    expect(literals.join('')).toBe('abandoned')
    expect(literals.join('')).not.toContain('abandoned text')
  })
})

describe('createMarkerParser — text that merely looks like a token', () => {
  it('speaks a lone closer', async () => {
    const { spoken, specials } = await run(['the arrow |> points right'])
    expect(spoken).toBe('the arrow |> points right')
    expect(specials).toEqual([])
  })

  it('speaks a less-than that never becomes an opener', async () => {
    const { spoken, specials } = await run(['5 < 6 and 7 < 8'])
    expect(spoken).toBe('5 < 6 and 7 < 8')
    expect(specials).toEqual([])
  })

  it('treats an unknown token syntax as a special, not as text', async () => {
    // Anything between `<|` and `|>` is a control token. Unknown ones are the
    // caller's problem to ignore — but they must never reach the TTS.
    const { spoken, specials } = await run(['a<|WHATEVER 1|>b'])
    expect(spoken).toBe('ab')
    expect(specials).toEqual(['<|WHATEVER 1|>'])
  })

  it('unescapes the escaped marker syntax before scanning', async () => {
    // Upstream lets a model write about the syntax without triggering it.
    const { spoken, specials } = await run([`x<{'|'}ACT {"emotion":"happy"}{'|'}>y`])
    expect(spoken).toBe('xy')
    expect(specials).toEqual(['<|ACT {"emotion":"happy"}|>'])
  })
})

describe('createMarkerParser — back-pressure (PROTOCOL.md §5 requirement 3)', () => {
  it('awaits an async handler before consume() resolves', async () => {
    const order: string[] = []
    const parser = createMarkerParser(async (event) => {
      order.push(`start:${event.type}`)
      await new Promise(resolve => setTimeout(resolve, 5))
      order.push(`end:${event.type}`)
    })

    await parser.consume('hello there <|ACT {"emotion":"happy"}|> bye bye')
    await parser.end()

    // No interleaving: every handler ran to completion before the next started.
    for (let i = 0; i < order.length; i += 2) {
      expect(order[i].startsWith('start:')).toBe(true)
      expect(order[i + 1].startsWith('end:')).toBe(true)
    }
  })

  it('keeps literal and special events in stream order', async () => {
    const seen: string[] = []
    const parser = createMarkerParser(async (event) => {
      await new Promise(resolve => setTimeout(resolve, 1))
      seen.push(event.type === 'literal' ? `L(${event.text})` : `S(${event.raw})`)
    })

    await parser.consume('one<|DELAY 1|>')
    await parser.consume('two<|DELAY 2|>')
    await parser.end()

    expect(seen).toEqual(['L(one)', 'S(<|DELAY 1|>)', 'L(two)', 'S(<|DELAY 2|>)'])
  })
})

describe('parseMarkerText', () => {
  it('returns ordered events for a complete string', async () => {
    expect(await parseMarkerText('a<|ACT {"emotion":"happy"}|>b')).toEqual([
      { type: 'literal', text: 'a' },
      { type: 'special', raw: '<|ACT {"emotion":"happy"}|>' },
      { type: 'literal', text: 'b' },
    ])
  })

  it('drops an unterminated trailing token', async () => {
    expect(await parseMarkerText('a<|ACT {')).toEqual([
      { type: 'literal', text: 'a' },
    ])
  })
})
