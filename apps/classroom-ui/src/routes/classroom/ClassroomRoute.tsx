/**
 * `/classroom` — the projector view.
 *
 * Full screen, no chrome, no controls, nothing a child can get lost in.
 * The facilitator drives it from `/control` on the laptop screen (extended
 * display, never mirrored — docs/3-design/runtime-topology.md §1).
 */
import { BusProvider } from '../../bus'
import { Stage } from '../../stage/Stage'

export function ClassroomRoute() {
  return (
    <BusProvider role="stage">
      <Stage />
    </BusProvider>
  )
}
