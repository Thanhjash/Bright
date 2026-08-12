import { defineConfig } from 'tsdown'

export default defineConfig({
  entry: [
    'src/index.ts',
    'src/act/index.ts',
    'src/live2d/index.ts',
    'src/react/index.ts',
    'src/vendor/index.ts',
    // Browser-only: `wlipsync` subclasses AudioWorkletNode at module scope, so this
    // must stay out of every other entry point's import graph.
    'src/vendor/model-driver-lipsync/live2d/index.ts',
    // Side-effectful: patches pixi-live2d-display's static ZipLoader/FileLoader on
    // import. Its own entry so callers opt in explicitly.
    'src/live2d/live2d-zip-loader.ts',
  ],
  outDir: 'dist',
  format: ['esm'],
  dts: true,
  clean: true,
  platform: 'browser',
  // The contracts package is types + a handful of frozen constants. It is
  // reached by relative path (there is no npm workspace in this repo), so it
  // must be bundled in rather than emitted as a dangling `../../contracts/src`
  // import that would not resolve from `dist/`.
  external: [
    'react',
    'react/jsx-runtime',
    'react-dom',
    /^@pixi\//,
    'pixi-live2d-display',
    /^pixi-live2d-display\//,
    'wlipsync',
    'clustr',
    'jszip',
    '@moeru/eventa',
  ],
})
