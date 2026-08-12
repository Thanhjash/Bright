import type { TextProps } from '@contracts'
import { BoardShell } from './parts'

const SIZE_CLASS: Record<NonNullable<TextProps['size']>, string> = {
  sm: 't-board-sm',
  md: 't-board-md',
  lg: 't-board-lg',
  xl: 't-board-xl',
}

/** `text` — one sentence, as large as it can be. Nothing else on screen. */
export function TextBoard({ props }: { props: TextProps }) {
  const size = SIZE_CLASS[props.size ?? 'lg']
  return (
    <BoardShell>
      <p
        key={props.text}
        className={`${size} animate-scene-in max-w-[16ch] text-center font-display font-extrabold text-balance tracking-tight text-cream`}
      >
        {props.text}
      </p>
    </BoardShell>
  )
}
