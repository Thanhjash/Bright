/** Runtime configuration. Every value has a working default so the app boots
 *  with no .env at all. */

export const IS_MOCK = import.meta.env.VITE_MOCK === '1'

/** classroom-core WebSocket bus. */
export const BUS_URL = import.meta.env.VITE_BUS_URL ?? 'ws://127.0.0.1:8004/ws'

/** classroom-core HTTP origin — serves `GET /assets/<id>`. Absolute, because
 *  the UI is served from :3000 and core lives on :8004 in every environment,
 *  dev and kiosk alike. */
export const CORE_HTTP = import.meta.env.VITE_CORE_HTTP ?? 'http://127.0.0.1:8004'

/** speech service — `POST /audio/speech` (Piper TTS) and
 *  `POST /audio/transcriptions` (Whisper STT). Note that it CORS-allows exactly
 *  `127.0.0.1:3000` / `localhost:3000`, so a UI served from any other port gets
 *  a "Failed to fetch" it cannot distinguish from the service being down. */
export const SPEECH_URL = import.meta.env.VITE_SPEECH_URL ?? 'http://127.0.0.1:8001'
