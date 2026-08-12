/**
 * Vendored from Project AIRI — https://github.com/moeru-ai/airi
 * Source: packages/pipelines-audio/src/priority.ts
 * Version: 0.11.3 (commit b230e16)
 * Copyright (c) 2024-present Moeru AI Project AIRI Team. Licensed under the MIT License.
 *
 * Copied VERBATIM. Do not edit — re-vendor from upstream instead.
 */

import type { PriorityLevel, PriorityResolver } from './types'

const DEFAULT_LEVELS: Record<PriorityLevel, number> = {
  critical: 300,
  high: 200,
  normal: 100,
  low: 0,
}

export function createPriorityResolver(levels?: Partial<Record<PriorityLevel, number>>): PriorityResolver {
  const resolved = { ...DEFAULT_LEVELS, ...levels }

  return {
    resolve(priority?: PriorityLevel | number) {
      if (priority == null)
        return resolved.normal
      if (typeof priority === 'number')
        return priority
      return resolved[priority] ?? resolved.normal
    },
  }
}

export function comparePriority(a: number, b: number) {
  if (a === b)
    return 0
  return a > b ? 1 : -1
}
