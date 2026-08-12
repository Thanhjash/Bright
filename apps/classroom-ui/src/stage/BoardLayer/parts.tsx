/**
 * Shared board primitives.
 *
 * Everything here is sized for a projector: no element smaller than a
 * fingertip, no text below ~1.5rem at 1080p, no hairline borders (a 1px rule
 * disappears at 6 metres), no low-contrast greys.
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { AssetRef, MediaItem } from '@contracts'
import { resolveAsset } from '../../lib/assets'

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/** Every board sits in this frame: full bleed, centred, animated on entry. */
export function BoardShell({
  children,
  className,
  align = 'center',
  justify = 'center',
}: {
  children: ReactNode
  className?: string
  align?: 'center' | 'stretch'
  /** kept as a prop rather than a className so it can never fight
   *  `justify-center` in Tailwind's output order */
  justify?: 'center' | 'between'
}) {
  return (
    <div
      className={cx(
        // Top and bottom padding are the overlay's reserved lanes — student
        // name / listening / mode badge above, subtitle below. The board must
        // never sit underneath either of them.
        //
        // 22vh at the foot is measured, not guessed: three lines of subtitle at
        // clamp(…,2.15vw,…) with leading-snug is 19.3vh of box plus the lane's
        // own 2.5vh bottom margin. `line-clamp-3` in SubtitleBar is the other
        // half of that guarantee — change one and you must change both.
        'flex h-full w-full flex-col gap-[2vh] p-[9vh_3vw_22vh]',
        align === 'center' ? 'items-center' : 'items-stretch',
        justify === 'center' ? 'justify-center' : 'justify-between',
        className,
      )}
    >
      {children}
    </div>
  )
}

/** The instruction line above a task — the thing a child reads first. */
export function Prompt({ children }: { children: ReactNode }) {
  return (
    <h2 className="t-board-md animate-rise max-w-[92%] text-center font-display font-extrabold text-balance text-cream">
      {children}
    </h2>
  )
}

/**
 * A board picture.
 *
 * `alt` is deliberately **empty** whenever the word is already printed beside
 * the picture. Two reasons, and the second is the one that showed up on a
 * projector:
 *
 *  1. A visible label makes the image decorative; repeating it in `alt` is a
 *     screen-reader duplicate.
 *  2. When an asset 404s — which happens the first time a lesson ships with a
 *     media manifest that was not fully rendered — the browser paints the alt
 *     text *inside the tile*, in tiny grey system type next to a broken-image
 *     glyph. The class then sees the word twice: once as rubble at the top of
 *     the card, once as the real label below it.
 *
 * So a failed load is caught and replaced with a calm frame instead. A missing
 * picture should look like a missing picture, never like a second caption.
 */
export function Picture({
  asset,
  alt = '',
  className,
  fit = 'contain',
}: {
  asset: AssetRef | undefined
  alt?: string
  className?: string
  fit?: 'contain' | 'cover'
}) {
  const src = resolveAsset(asset)
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])

  if (!src || failed) {
    return (
      <span
        className={cx(
          'flex items-center justify-center rounded-[1.1rem] bg-ink-600/50',
          className,
        )}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="h-[38%] max-h-[6vh] min-h-[18px] text-muted/60">
          <path
            d="M3.5 5.5h17v13h-17zM3.5 15l4.5-4 3.5 3 4-5 5 6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          <circle cx="9" cy="9.5" r="1.6" fill="currentColor" />
        </svg>
      </span>
    )
  }

  return (
    <img
      src={src}
      alt={alt}
      draggable={false}
      onError={() => setFailed(true)}
      className={cx(fit === 'cover' ? 'object-cover' : 'object-contain', className)}
    />
  )
}

/** Picture + word, the unit both vocabulary and choice are built from. */
export function MediaTile({
  item,
  label,
  className,
}: {
  item: MediaItem
  label?: string
  className?: string
}) {
  const text = label ?? item.text
  return (
    <div
      className={cx(
        'flex h-full min-h-0 w-full flex-1 flex-col items-center justify-center gap-[1.2vh]',
        className,
      )}
    >
      {item.asset ? (
        // Labelled: the word below is the accessible name. Unlabelled (the
        // picture column of a `matching`): the item id is all we have and it
        // is not language a child or a screen reader wants read out, so the
        // picture stays decorative either way.
        <Picture asset={item.asset} className="min-h-0 w-full flex-1 rounded-[1.1rem]" />
      ) : null}
      {text ? (
        <span className="text-center font-display text-[clamp(1.2rem,2.2vw,2.4rem)] leading-none font-extrabold tracking-tight text-cream">
          {text}
        </span>
      ) : null}
    </div>
  )
}

/**
 * Placeholder for scene kinds the Stage does not render fully yet.
 * It must still show the props: a facilitator needs to know what the lesson
 * asked for even when the board cannot draw it.
 */
export function StubBoard({
  title,
  summary,
  children,
}: {
  title: string
  summary?: string
  children?: ReactNode
}) {
  return (
    <BoardShell>
      <div className="animate-scene-in card-surface flex max-h-full w-full max-w-[80%] flex-col items-center gap-[2vh] overflow-hidden p-[4vh_4vw] text-center">
        <span className="rounded-full bg-violet/25 px-6 py-2 text-[clamp(0.9rem,1.3vw,1.3rem)] font-extrabold tracking-[0.18em] text-violet uppercase">
          Coming soon
        </span>
        <h2 className="t-board-md font-display font-extrabold text-cream">{title}</h2>
        {summary ? <p className="t-caption max-w-[46ch] text-muted">{summary}</p> : null}
        {children ? <div className="w-full">{children}</div> : null}
      </div>
    </BoardShell>
  )
}

/** Readable key/value dump used by the stubs. */
export function PropRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-center gap-x-4 gap-y-2 border-t-3 border-ink-500/60 py-[1.4vh] first:border-t-0">
      <span className="text-[clamp(0.85rem,1.15vw,1.15rem)] font-extrabold tracking-[0.16em] text-muted uppercase">
        {label}
      </span>
      <span className="t-caption font-semibold text-cream">{children}</span>
    </div>
  )
}

export function Chips({ items }: { items: string[] }) {
  return (
    <span className="flex flex-wrap justify-center gap-2">
      {items.map((t) => (
        <span
          key={t}
          className="rounded-full bg-ink-600 px-4 py-1.5 text-[clamp(0.9rem,1.3vw,1.35rem)] font-bold text-cream"
        >
          {t}
        </span>
      ))}
    </span>
  )
}
