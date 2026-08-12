/**
 * The `Ref` shim.
 *
 * AIRI's Live2D composables are framework-free at runtime but type-only coupled to
 * Vue: they take `Ref<T>` purely as "a box whose `.value` I read every frame". This
 * file is that box, so the ported code keeps its exact shape without pulling Vue in.
 *
 * There is no reactivity here and none is needed — every consumer reads `.value`
 * inside the render loop, 60 times a second. React state is bridged by writing to
 * `.value` in an effect (see `src/react/`), never by re-rendering the canvas.
 */

/** A mutable box. Structurally identical to Vue's `Ref<T>` for read/write use. */
export interface Ref<T> {
  value: T
}

/** A box that is only read. Accepts a `Ref<T>` anywhere it is required. */
export interface ReadonlyRef<T> {
  readonly value: T
}

/** Creates a box. Named `ref` so ported AIRI code and tests read unchanged. */
export function ref<T>(value: T): Ref<T> {
  return { value }
}

/** Wraps a getter as a read-only box, for values owned elsewhere. */
export function computedRef<T>(get: () => T): ReadonlyRef<T> {
  return {
    get value() {
      return get()
    },
  }
}

/** `T`, a box holding `T`, or a getter returning `T`. */
export type MaybeRefOrGetter<T> = T | ReadonlyRef<T> | (() => T)

/** Reads any of the three forms above. Mirrors Vue's `toValue`. */
export function toValue<T>(source: MaybeRefOrGetter<T>): T {
  if (typeof source === 'function')
    return (source as () => T)()
  if (source !== null && typeof source === 'object' && 'value' in source)
    return (source as ReadonlyRef<T>).value
  return source as T
}
