/**
 * Shared browser plumbing for the integration scenarios.
 *
 * Every scenario prints exactly one `@@RESULT@@ {json}` line; `harness/browser.py`
 * parses that and pytest asserts on it. Anything else printed is diagnosis and
 * lands in tests/.artifacts/.
 *
 * Two rules learned the hard way and encoded here:
 *
 * 1. State is read from `window.__bright` (the app's own Zustand store), never
 *    from pixels. A screenshot cannot tell you the emotion is off by one.
 * 2. When a probe has to touch a module's internals, it must resolve **the
 *    exact URL the app requested**. An earlier diagnostic imported
 *    `pixi-live2d-display_cubism4.js` without the `?v=` query the app used;
 *    that is a different module instance in the browser, so the probe measured
 *    an object nothing was using and reported a working patch as broken.
 *    `resolveModuleUrl()` below exists so that cannot happen again.
 */
// playwright-core is installed in the shared `.tools/` sandbox, not under
// tests/. `NODE_PATH` does not apply to ESM resolution, so the package is
// imported by absolute file URL instead of adding a node_modules tree here.
const { chromium } = await import(process.env.PLAYWRIGHT_CORE)

export const LAUNCH_ARGS = [
  '--no-sandbox',
  '--use-gl=swiftshader',
  '--enable-unsafe-swiftshader',
  '--autoplay-policy=no-user-gesture-required',
]

export function config() {
  return JSON.parse(process.argv[2] || '{}')
}

export function result(obj) {
  console.log(`@@RESULT@@ ${JSON.stringify(obj)}`)
}

export async function launch() {
  return chromium.launch({
    executablePath: process.env.CHROME_PATH,
    args: LAUNCH_ARGS,
  })
}

/** A page that records every request URL, page error and console error. */
export async function newPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
  const requests = []
  const pageErrors = []
  const consoleErrors = []
  page.on('request', (r) => requests.push(r.url()))
  page.on('pageerror', (e) => pageErrors.push(String(e.message || e)))
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })
  page.__requests = requests
  page.__pageErrors = pageErrors
  page.__consoleErrors = consoleErrors
  return page
}

/** The app's live store, as plain JSON. */
export async function store(page) {
  return page.evaluate(() => {
    const hook = window.__bright
    if (!hook) return null
    const s = hook.getState()
    return {
      connection: s.connection,
      stateVersion: s.stateVersion,
      scene: s.scene,
      lesson: s.lesson,
      mode: s.mode,
      overlaySubtitle: s.overlaySubtitle,
      speechSubtitle: s.speechSubtitle,
      avatar: s.avatar,
      awaitingSnapshot: s.awaitingSnapshot,
      transcript: s.transcript.map((t) => `${t.kind}: ${t.text}`),
    }
  })
}

export async function waitForStore(page, predicate, { timeout = 30000, label = 'store' } = {}) {
  const deadline = Date.now() + timeout
  let last = null
  while (Date.now() < deadline) {
    last = await store(page)
    if (last && predicate(last)) return last
    await page.waitForTimeout(100)
  }
  throw new Error(`timed out waiting for ${label}; store=${JSON.stringify(last)?.slice(0, 800)}`)
}

/**
 * The URL the running app actually loaded a module from.
 *
 * Matches against the requests this page made, so the probe gets the same
 * module instance the app is using — query string, `/@fs/` prefix and all.
 */
export function resolveModuleUrl(page, pattern) {
  const re = pattern instanceof RegExp ? pattern : new RegExp(pattern)
  const hits = page.__requests.filter((u) => re.test(u))
  if (hits.length === 0) return null
  // Prefer the longest (most specific) match; they only differ by query.
  return hits.sort((a, b) => b.length - a.length)[0]
}

// ------------------------------------------------------------ core dev API

export function coreApi(base) {
  const get = async (p) => {
    const r = await fetch(`${base}${p}`)
    if (!r.ok) throw new Error(`GET ${p} -> ${r.status}`)
    return r.json()
  }
  const post = async (p, body) => {
    const r = await fetch(`${base}${p}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    if (!r.ok) throw new Error(`POST ${p} -> ${r.status} ${await r.text()}`)
    return r.json()
  }
  return {
    state: () => get('/dev/state'),
    startLesson: (index = 0, extra = {}) => post('/dev/lesson/start', { index, ...extra }),
    control: (cmd, arg) => post('/dev/lesson/control', { cmd, arg: arg ?? null }),
    say: (body) => post('/dev/say', body),
    scene: (body) => post('/dev/scene', body),
    interaction: (type, payload) => post('/dev/interaction', { type, payload }),
    async waitForScene(kind, timeout = 60000) {
      const deadline = Date.now() + timeout
      while (Date.now() < deadline) {
        const s = await get('/dev/state')
        if (s.snapshot.scene.kind === kind) return s
        await new Promise((r) => setTimeout(r, 250))
      }
      throw new Error(`core never reached scene kind=${kind}`)
    },
  }
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}
