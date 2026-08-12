import { selectSubtitle, useClassroom } from '../../store/classroom'

/**
 * What the teacher is saying, in text.
 *
 * `scene.overlay.subtitle` is authoritative; the current `speech.say` fills in
 * when the server sent no overlay subtitle (see README, ambiguities).
 * ACT tokens are already scrubbed by the store — none of `<|ACT …|>` can ever
 * reach this element.
 */
export function SubtitleBar() {
  const subtitle = useClassroom(selectSubtitle)
  const speaking = useClassroom((s) => s.avatar.speaking)

  return (
    <div
      data-stage="subtitle"
      className={
        // width in % not ch: `ch` on this wrapper resolves against the
        // inherited 16px, not the subtitle's own clamped size.
        'w-full max-w-[94%] transition-all duration-300 ease-out ' +
        (subtitle ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-3 opacity-0')
      }
      aria-live="polite"
    >
      {/* Three lines is the ceiling, and it is a layout guarantee rather than a
          style choice: BoardShell reserves exactly this much room at the foot of
          the board, so an unusually long line clips instead of climbing over the
          activity. At 2.15vw a line holds ~70 characters across the board
          column — longer than anything the lesson content produces. */}
      <p
        className={
          'rounded-[1.6rem] bg-ink-950/82 px-[2.2vw] py-[1.8vh] text-center font-display ' +
          'text-[clamp(1.3rem,2.15vw,2.5rem)] leading-snug font-bold text-balance text-cream ' +
          'shadow-[0_1.6vh_5vh_-1.6vh_rgba(0,0,0,0.8)] backdrop-blur-sm ' +
          (speaking ? 'ring-3 ring-amber/45' : 'ring-3 ring-ink-500/40')
        }
      >
        {/* The clamp sits on an inner span, not on the padded box: `overflow:
            hidden` clips at the PADDING edge, so clamping the box itself lets a
            fourth line bleed halfway into the padding and get sliced by the
            border. Clipping the content box cuts cleanly at line three. */}
        <span className="line-clamp-3">{subtitle || ' '}</span>
      </p>
    </div>
  )
}
