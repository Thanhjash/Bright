import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * `@contracts` points straight at the TypeScript source of packages/contracts.
 * That package has no build step and no package.json, so we resolve the file
 * directly and let esbuild transpile it. `server.fs.allow` must include the
 * repo root or the dev server refuses to serve a file outside its root.
 */
const contractsEntry = fileURLToPath(
  new URL('../../packages/contracts/src/index.ts', import.meta.url),
)
const repoRoot = fileURLToPath(new URL('../..', import.meta.url))

/**
 * `@bright/airi-bridge` is consumed as SOURCE, not as its built `dist` —
 * exactly like `@contracts` above.
 *
 * Going through `dist` gave us two live copies of pixi-live2d-display: the
 * dist resolved the library through airi-bridge's own node_modules while Vite
 * pre-bundled the app's copy into `.vite/deps`. airi-bridge patches
 * pixi-live2d-display's *static* `ZipLoader` in place to support `.zip` models,
 * so the patch landed on one instance and the renderer used the other. The only
 * symptom was `Live2DFactory` throwing "Unknown settings format" — nothing
 * pointing at duplication. Confirmed by probing the running page:
 * `ZipLoader.createSettings` was upstream's, not ours.
 *
 * Fighting that with `dedupe` / `optimizeDeps` traded it for CommonJS interop
 * failures, because these pixi packages must be pre-bundled to work in dev.
 * Aliasing to source removes the second graph entirely instead of trying to
 * reconcile two, and it gives HMR into the bridge for free.
 */
const bridgeSrc = (p: string) =>
  fileURLToPath(new URL(`../../packages/airi-bridge/src/${p}`, import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: '@contracts', replacement: contractsEntry },
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
      // Longest-prefix first: '@bright/airi-bridge' would otherwise swallow
      // its own subpaths.
      {
        find: '@bright/airi-bridge/wlipsync-profile.json',
        replacement: bridgeSrc('vendor/model-driver-lipsync/shared/wlipsync/profile.json'),
      },
      { find: '@bright/airi-bridge/react', replacement: bridgeSrc('react/index.ts') },
      { find: '@bright/airi-bridge/act', replacement: bridgeSrc('act/index.ts') },
      { find: '@bright/airi-bridge/live2d/zip-loader', replacement: bridgeSrc('live2d/live2d-zip-loader.ts') },
      { find: '@bright/airi-bridge/live2d', replacement: bridgeSrc('live2d/index.ts') },
      { find: '@bright/airi-bridge', replacement: bridgeSrc('index.ts') },
    ],
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    fs: { allow: [repoRoot] },
    // Running from WSL against a repo on a Windows drive (/mnt/d/...) gives no
    // inotify events, so HMR silently stops working. `VITE_POLL=1 pnpm dev`
    // trades a little CPU for a working reload loop.
    watch: process.env.VITE_POLL === '1' ? { usePolling: true, interval: 300 } : undefined,
  },
  preview: { host: '127.0.0.1', port: 3000, strictPort: true },
  build: { target: 'es2022', sourcemap: true },
})
