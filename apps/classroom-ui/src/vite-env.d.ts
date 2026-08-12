/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `1` → run from local fixtures with no backend. */
  readonly VITE_MOCK?: string
  /** classroom-core WebSocket endpoint. Default `ws://127.0.0.1:8004/ws`. */
  readonly VITE_BUS_URL?: string
  /** classroom-core HTTP origin for `/assets/<id>`. Default `http://127.0.0.1:8004`. */
  readonly VITE_CORE_HTTP?: string
  /** Dev-only Core-owned transcript fixture. Must be unset in a product build. */
  readonly VITE_SYNTHETIC_FIXTURE_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
