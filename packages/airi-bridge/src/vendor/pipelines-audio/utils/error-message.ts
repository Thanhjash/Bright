/**
 * Local replacement for `errorMessageFrom` from `@moeru/std`, which AIRI's
 * pipelines-audio depends on. Taking a pre-release dependency for one helper is
 * not worth it; this reproduces the same contract.
 *
 * Returns the message of an Error-like value, or `undefined` when the thrown
 * value carries no usable message. Callers pair it with `?? 'fallback'`.
 */
export function errorMessageFrom(error: unknown): string | undefined {
  if (error instanceof Error)
    return error.message
  if (typeof error === 'string')
    return error
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as { message: unknown }).message
    if (typeof message === 'string')
      return message
  }
  return undefined
}

/**
 * Returns an error message while preserving JavaScript string fallback.
 */
export function errorMessageFromValue(error: unknown): string {
  return errorMessageFrom(error) ?? String(error)
}
