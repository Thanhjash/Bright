import type { ImageProps } from '@contracts'
import { BoardShell, Picture } from './parts'

/** `image` — one picture, as big as the board allows, caption underneath. */
export function ImageBoard({ props }: { props: ImageProps }) {
  return (
    <BoardShell>
      <figure
        key={props.asset}
        className="animate-scene-in flex h-full w-full flex-col items-center justify-center gap-[2.4vh]"
      >
        <Picture
          asset={props.asset}
          className="min-h-0 w-full flex-1 rounded-[2rem] shadow-[0_2.4vh_6vh_-2vh_rgba(0,0,0,0.65)]"
        />
        {props.caption ? (
          <figcaption className="t-board-sm text-center font-display font-extrabold text-balance text-cream">
            {props.caption}
          </figcaption>
        ) : null}
      </figure>
    </BoardShell>
  )
}
