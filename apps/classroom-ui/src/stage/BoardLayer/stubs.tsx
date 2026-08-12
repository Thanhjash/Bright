/**
 * Scene kinds the Stage does not render fully yet.
 *
 * Only `video` is left here. It still shows its props legibly — a facilitator
 * glancing at the board must be able to tell what the lesson asked for, and a
 * developer must be able to see that the wire payload arrived intact. It is
 * not a grey box.
 */
import type { VideoProps } from '@contracts'
import { assetId } from '../../lib/assets'
import { PropRow, StubBoard } from './parts'

export function VideoBoard({ props }: { props: VideoProps }) {
  return (
    <StubBoard
      title="Video"
      summary="Playback, buffering and the scrub-free classroom controls are not built yet."
    >
      <div className="flex flex-col">
        <PropRow label="clip">{assetId(props.asset)}</PropRow>
        {props.caption ? <PropRow label="caption">{props.caption}</PropRow> : null}
        <PropRow label="autoplay">{props.autoplay ? 'yes' : 'no'}</PropRow>
      </div>
    </StubBoard>
  )
}
