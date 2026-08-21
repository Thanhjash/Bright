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
      {/* Fill the board, do not sit at natural size.
          `w-auto` meant a 300px textbook card rendered as a 300px card on a
          1267px chalkboard -- a stamp on a wall, unreadable from the back of a
          room. `object-contain` keeps the aspect ratio, so a wide comic panel
          and a square portrait both fill what they can without distortion. */}
      <Picture
        asset={props.asset}
        className="min-h-0 h-[78%] w-[88%] object-contain drop-shadow-[0_8px_24px_rgba(0,0,0,0.45)]"
      />
      {props.caption ? (
        <figcaption className="max-w-[90%] text-center font-display text-[clamp(1rem,1.8vw,1.7rem)] font-bold leading-snug text-cream/95">
          {props.caption}
        </figcaption>
      ) : null}
    </figure>
  )
}
