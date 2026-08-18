import type { ImageProps } from '@contracts'
import { Picture } from './parts'

/** Picture sits on the photographed chalkboard, not a navy card. */
export function ImageBoard({ props }: { props: ImageProps }) {
  return (
    <figure
      key={props.asset}
      data-board="picture"
      className="flex h-full w-full flex-col items-center justify-center gap-[1.4vh] px-[3%] py-[4%]"
    >
      <Picture
        asset={props.asset}
        className="min-h-0 w-auto max-h-[78%] max-w-[88%] object-contain drop-shadow-[0_8px_24px_rgba(0,0,0,0.45)]"
      />
      {props.caption ? (
        <figcaption className="max-w-[90%] text-center font-display text-[clamp(1rem,1.8vw,1.7rem)] font-bold leading-snug text-cream/95">
          {props.caption}
        </figcaption>
      ) : null}
    </figure>
  )
}
