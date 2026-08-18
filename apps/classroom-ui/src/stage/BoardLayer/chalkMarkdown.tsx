import type { ReactNode } from 'react'

/**
 * Chalkboard markdown — the exact grammar Core's `_clean_board_markdown`
 * (services/classroom-core/teacher_os.py) actually lets through and nothing
 * more: `#`/`##`/`###` headings, `-`/`*`/`1.` list items, `**bold**` and
 * `*italic*`/`_italic_`, blank-line paragraph breaks. Core caps the raw
 * string at 400 characters and 8 lines before it ever reaches here.
 *
 * No HTML is ever produced — every node below is a real React element or a
 * plain string, never `dangerouslySetInnerHTML`. Anything that doesn't match
 * a rule falls through as a plain line of text: SceneRouter wraps boards in
 * an error boundary precisely so a bad board never goes blank on the
 * projector, and this parser must never throw its way into triggering it.
 */

type ChalkBlock =
  | { kind: 'rule' }
  | { kind: 'heading'; level: 1 | 2 | 3; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'paragraph'; text: string }

const HEADING_RE = /^(#{1,3})\s+(.+)$/
// She writes `---` between a model sentence and the child's version of it.
// Observed live, so it draws as a chalk rule rather than three dashes.
const RULE_RE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/
const UL_RE = /^[-*]\s+(.+)$/
const OL_RE = /^\d+\.\s+(.+)$/
// Sized to the chalk rect, not to the viewport. `t-board-lg` caps at 6rem,
// which broke "Hello. I'm Ben." across three lines on a 1920x1080 projector
// because the board is only ~55% of the screen wide. Legibility from the back
// of a room is a floor, not a target: bigger is not better once it wraps.
const HEADING_CLASS: Record<1 | 2 | 3, string> = {
  1: 'text-[clamp(1.9rem,3.6vw,3.6rem)]',
  2: 'text-[clamp(1.7rem,3vw,3rem)]',
  3: 'text-[clamp(1.5rem,2.4vw,2.4rem)]',
}

function parseChalkBlocks(raw: string): ChalkBlock[] {
  const lines = (raw ?? '').replace(/\r\n?/g, '\n').split('\n')
  const blocks: ChalkBlock[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') {
      i++
      continue
    }
    if (RULE_RE.test(line)) {
      blocks.push({ kind: 'rule' })
      i++
      continue
    }
    const heading = HEADING_RE.exec(line)
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length as 1 | 2 | 3, text: heading[2].trim() })
      i++
      continue
    }
    const ul = UL_RE.exec(line)
    const ol = ul ? null : OL_RE.exec(line)
    if (ul || ol) {
      const ordered = !!ol
      const items = [(ul ?? ol)![1].trim()]
      i++
      while (i < lines.length) {
        const m = ordered ? OL_RE.exec(lines[i]) : UL_RE.exec(lines[i])
        if (!m) break
        items.push(m[1].trim())
        i++
      }
      blocks.push({ kind: 'list', ordered, items })
      continue
    }
    blocks.push({ kind: 'paragraph', text: line.trim() })
    i++
  }
  // Whitespace-only or empty input: never render nothing, show what we got.
  if (blocks.length === 0) blocks.push({ kind: 'paragraph', text: raw ?? '' })
  return blocks
}

const INLINE_RE = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|_[^_\n]+_)/g

function renderInline(text: string, keyBase: string): ReactNode[] {
  return text
    .split(INLINE_RE)
    .filter((part) => part !== '')
    .map((part, idx) => {
      const key = `${keyBase}-${idx}`
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={key} className="font-black">
            {part.slice(2, -2)}
          </strong>
        )
      }
      if ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_'))) {
        return (
          <em key={key} className="italic">
            {part.slice(1, -1)}
          </em>
        )
      }
      return part
    })
}

/** Renders Core's narrow chalkboard grammar as chalk, never as raw punctuation. */
export function ChalkMarkdown({ text, textSizeClass }: { text: string; textSizeClass: string }) {
  const blocks = parseChalkBlocks(text)
  return (
    <div className="flex max-w-[26ch] flex-col items-center gap-[1.4vh] text-center">
      {blocks.map((block, i) => {
        const key = `b-${i}`
        if (block.kind === 'rule') {
          return <hr key={key} className="my-[0.4vh] h-px w-[42%] border-0 bg-cream/35" />
        }
        if (block.kind === 'heading') {
          return (
            <h2
              key={key}
              className={`${HEADING_CLASS[block.level]} max-w-full font-display font-extrabold text-balance text-cream`}
            >
              {renderInline(block.text, key)}
            </h2>
          )
        }
        if (block.kind === 'list') {
          const Tag = block.ordered ? 'ol' : 'ul'
          return (
            <Tag
              key={key}
              className={`${textSizeClass} ${block.ordered ? 'list-decimal' : 'list-disc'} mx-auto w-fit list-outside marker:text-amber pl-[1.2em] text-left font-display font-bold leading-snug text-cream`}
            >
              {block.items.map((item, j) => (
                <li key={`${key}-${j}`}>{renderInline(item, `${key}-${j}`)}</li>
              ))}
            </Tag>
          )
        }
        return (
          <p key={key} className={`${textSizeClass} max-w-full font-display font-extrabold leading-snug text-balance text-cream`}>
            {renderInline(block.text, key)}
          </p>
        )
      })}
    </div>
  )
}
