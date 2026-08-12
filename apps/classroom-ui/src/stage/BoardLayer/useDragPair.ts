/**
 * Drag-to-drop for a classroom board — mouse AND finger, one code path.
 *
 * Why not HTML5 drag-and-drop: `dragstart`/`dragover` does not exist on touch
 * at all. Half the classrooms this ships to have a touchscreen, and a child's
 * finger is not a mouse — it is fat, it wobbles, and it arrives with the whole
 * hand. So this is built on Pointer Events, which unify mouse / touch / pen,
 * plus three things that are individually easy to forget and each of which
 * breaks finger-drag completely:
 *
 *  1. `touch-action: none` on every draggable. Without it the browser claims
 *     the gesture as a page scroll before the first `pointermove` and the drag
 *     never starts. This is the single most common cause of "works with a
 *     mouse, does nothing on the board".
 *  2. `setPointerCapture` on the source. Once the finger leaves the source
 *     element — which it does immediately — events would otherwise retarget.
 *  3. Hit-testing with `document.elementFromPoint`, because captured events
 *     always report the *source* as their target. Drop zones are found by a
 *     `data-drop-id` attribute under the pointer, so the ghost must be
 *     `pointer-events: none` (it is, see `ghostStyle`).
 *
 * A slop threshold keeps a tap a tap. And because a drag is genuinely hard for
 * a small child on a wobbly projected touchscreen, a **tap-then-tap** fallback
 * is built in: tap the thing, then tap where it goes. Same `onDrop`.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'

/** Movement (px) before a press becomes a drag rather than a tap. */
const SLOP_PX = 8

export interface DragPairState {
  /** The item under the finger, or the one armed by a first tap. */
  activeId: string | null
  /** True once the pointer moved past the slop threshold. */
  dragging: boolean
  /** True when `activeId` came from a tap rather than a drag. */
  armed: boolean
  /** Viewport position of the pointer, for the ghost. */
  x: number
  y: number
  /** Size of the source element, so the ghost is the same size as the thing. */
  w: number
  h: number
  /** Drop zone currently under the pointer, if any. */
  overId: string | null
}

const IDLE: DragPairState = {
  activeId: null,
  dragging: false,
  armed: false,
  x: 0,
  y: 0,
  w: 0,
  h: 0,
  overId: null,
}

export interface UseDragPairOptions {
  /** Fired once per completed drop. Never fired for a drop outside a zone. */
  onDrop: (fromId: string, toId: string) => void
  /** Ids that can no longer be moved (already solved / already placed). */
  isLocked?: (id: string) => boolean
  /** Reject a pairing before it is reported. Also greys the zone while over it. */
  canDrop?: (fromId: string, toId: string) => boolean
  disabled?: boolean
}

export interface DragPairApi {
  state: DragPairState
  /** Spread onto a draggable element. */
  source: (id: string) => {
    'data-drag-id': string
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void
    style: CSSProperties
  }
  /**
   * Spread onto a drop zone. The `onPointerDown` completes a tap-then-tap
   * when the zone is not itself draggable; where a card is both source and
   * target, spread `target()` first so the source's handler wins.
   */
  target: (id: string) => {
    'data-drop-id': string
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void
  }
  /** Style for the floating ghost that follows the finger. */
  ghostStyle: CSSProperties
  /** Drop the armed selection without completing it (e.g. tapping the board). */
  cancel: () => void
}

interface Gesture {
  id: string
  pointerId: number
  startX: number
  startY: number
  w: number
  h: number
  node: HTMLElement
  moved: boolean
}

export function useDragPair({
  onDrop,
  isLocked,
  canDrop,
  disabled = false,
}: UseDragPairOptions): DragPairApi {
  const [state, setState] = useState<DragPairState>(IDLE)
  const gesture = useRef<Gesture | null>(null)
  // Latest callbacks, so the window listeners installed once never go stale.
  const cbs = useRef({ onDrop, isLocked, canDrop, disabled })
  cbs.current = { onDrop, isLocked, canDrop, disabled }
  // A mirror of `state` for the event handlers. `onDrop` must never be called
  // from inside a setState updater: updaters have to be pure, and StrictMode
  // runs them twice — which would emit the interaction twice.
  const live = useRef<DragPairState>(IDLE)
  live.current = state

  const zoneUnder = useCallback((x: number, y: number): string | null => {
    const el = document.elementFromPoint(x, y)
    const zone = el?.closest<HTMLElement>('[data-drop-id]')
    return zone?.dataset.dropId ?? null
  }, [])

  const finish = useCallback(
    (fromId: string, toId: string | null) => {
      if (toId && (!cbs.current.canDrop || cbs.current.canDrop(fromId, toId))) {
        cbs.current.onDrop(fromId, toId)
      }
    },
    [],
  )

  useEffect(() => {
    function move(e: PointerEvent) {
      const g = gesture.current
      if (!g || e.pointerId !== g.pointerId) return
      const far =
        Math.abs(e.clientX - g.startX) > SLOP_PX || Math.abs(e.clientY - g.startY) > SLOP_PX
      if (!g.moved && !far) return
      g.moved = true
      const over = zoneUnder(e.clientX, e.clientY)
      setState({
        activeId: g.id,
        dragging: true,
        armed: false,
        x: e.clientX,
        y: e.clientY,
        w: g.w,
        h: g.h,
        overId: over,
      })
    }

    function up(e: PointerEvent) {
      const g = gesture.current
      if (!g || e.pointerId !== g.pointerId) return
      gesture.current = null
      try {
        g.node.releasePointerCapture(g.pointerId)
      } catch {
        /* capture already gone — nothing to release */
      }

      if (g.moved) {
        const zone = zoneUnder(e.clientX, e.clientY)
        live.current = IDLE
        setState(IDLE)
        finish(g.id, zone)
        return
      }

      // A tap. It either arms this item, un-arms it, or completes a pair that
      // a previous tap armed.
      const prev = live.current
      if (prev.armed && prev.activeId && prev.activeId !== g.id) {
        const zone = zoneUnder(e.clientX, e.clientY)
        live.current = IDLE
        setState(IDLE)
        finish(prev.activeId, zone ?? g.id)
        return
      }
      const next: DragPairState =
        prev.armed && prev.activeId === g.id
          ? IDLE // tap the same thing again = put it down
          : { ...IDLE, activeId: g.id, armed: true }
      live.current = next
      setState(next)
    }

    function cancel(e: PointerEvent) {
      const g = gesture.current
      if (!g || e.pointerId !== g.pointerId) return
      gesture.current = null
      setState(IDLE)
    }

    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [finish, zoneUnder])

  const source = useCallback(
    (id: string) => ({
      'data-drag-id': id,
      // `touch-action: none` is load-bearing: see the file header.
      style: { touchAction: 'none' as const },
      onPointerDown: (event: ReactPointerEvent<HTMLElement>) => {
        if (cbs.current.disabled || cbs.current.isLocked?.(id)) return
        const node = event.currentTarget
        const r = node.getBoundingClientRect()
        try {
          node.setPointerCapture(event.pointerId)
        } catch {
          /* a synthetic or already-captured pointer; the window listeners still work */
        }
        gesture.current = {
          id,
          pointerId: event.pointerId,
          startX: event.clientX,
          startY: event.clientY,
          w: r.width,
          h: r.height,
          node,
          moved: false,
        }
      },
    }),
    [],
  )

  const target = useCallback(
    (id: string) => ({
      'data-drop-id': id,
      onPointerDown: () => {
        if (cbs.current.disabled) return
        const prev = live.current
        if (!prev.armed || !prev.activeId) return
        live.current = IDLE
        setState(IDLE)
        finish(prev.activeId, id)
      },
    }),
    [finish],
  )

  const cancel = useCallback(() => setState(IDLE), [])

  const ghostStyle: CSSProperties = {
    position: 'fixed',
    left: state.x,
    top: state.y,
    width: state.w || undefined,
    height: state.h || undefined,
    transform: 'translate(-50%, -50%) scale(1.06) rotate(-2deg)',
    pointerEvents: 'none',
    zIndex: 50,
  }

  return { state, source, target, ghostStyle, cancel }
}
