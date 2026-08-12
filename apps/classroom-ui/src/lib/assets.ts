/**
 * Asset resolution — PROTOCOL.md §8.
 *
 *   asset://apple.webp  →  GET {CORE_HTTP}/assets/apple.webp
 *
 * The UI never sees a filesystem path. In mock mode there is no core to serve
 * anything, so refs resolve to a generated inline SVG instead of 404ing —
 * a demo with broken image icons is worse than no demo.
 */
import type { AssetRef } from '@contracts'
import { CORE_HTTP, IS_MOCK } from './env'

const SCHEME = 'asset://'

export function assetId(ref: AssetRef): string {
  return ref.startsWith(SCHEME) ? ref.slice(SCHEME.length) : ref
}

export function resolveAsset(ref: AssetRef | undefined): string | undefined {
  if (!ref) return undefined
  // Already a browser-usable URL (fixtures, embedded media).
  if (/^(https?:|data:|blob:)/.test(ref)) return ref
  const id = assetId(ref)
  if (!id) return undefined
  if (IS_MOCK) return placeholderFor(id)
  return `${CORE_HTTP}/assets/${id}`
}

/** Stable hue from an asset id, so `apple.webp` is the same colour every time. */
function hueOf(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360
  return h
}

function prettyName(id: string): string {
  return id
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/^.*\//, '')
    .replace(/[-_]+/g, ' ')
}

const cache = new Map<string, string>()

/**
 * A friendly stand-in illustration: a soft duotone blob card, deterministic
 * per asset id so `apple.webp` is always the same picture.
 *
 * It carries **no text**. It used to print the asset's name across the bottom,
 * which meant every labelled card — the whole of `vocabulary` and `choice` —
 * showed the word twice: once burnt into the "picture", once as the real label
 * underneath. A stand-in picture must look like a picture; the word is the
 * board's job, not the placeholder's.
 */
export function placeholderFor(id: string): string {
  const hit = cache.get(id)
  if (hit) return hit

  const h = hueOf(id)
  const h2 = (h + 42) % 360
  // Deterministic per id, so the blob shapes differ between assets.
  const n = prettyName(id).length
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="hsl(${h} 78% 68%)"/>
      <stop offset="1" stop-color="hsl(${h2} 82% 54%)"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" rx="36" fill="url(#g)"/>
  <circle cx="${140 + (n % 5) * 24}" cy="150" r="104" fill="hsl(${h2} 90% 88%)" opacity="0.55"/>
  <circle cx="470" cy="${300 + (n % 4) * 18}" r="150" fill="hsl(${h} 92% 34%)" opacity="0.32"/>
  <path d="M0 392 Q160 320 320 380 T640 348 L640 480 L0 480 Z" fill="hsl(${h2} 88% 30%)" opacity="0.38"/>
</svg>`
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  cache.set(id, url)
  return url
}
