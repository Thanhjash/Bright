/**
 * I6 — an ACT token must never be spoken aloud. RELEASE GATE.
 *
 * "Never spoken aloud" is taken literally: the UI's speech pipeline ends at
 * `POST /audio/speech`, so the test reads what the synthesiser was actually
 * asked to say. A subtitle assertion would only prove the token was hidden
 * from the projector while the room heard "less than pipe A C T".
 *
 * Three phases, each catching a different way this breaks:
 *
 *   A. the parser itself, fed a token cut in half — the 5-character tail rule
 *      (PROTOCOL §5.4.1), tested against **the module instance the running app
 *      loaded**, resolved from the URLs this page requested. Importing the
 *      same file by a different URL would create a second module instance and
 *      measure something nothing is using.
 *   B. a whole `speech.say` payload carrying a token, end to end through the
 *      real pipeline.
 *   C. the same, but with the token split across two SSE frames on the wire
 *      between the scripted model and core, which is the only way to exercise
 *      the reassembly seam for real.
 *
 * Emotions differ per phase so the store tells us which one landed.
 */
import {
  config,
  coreApi,
  launch,
  newPage,
  resolveModuleUrl,
  result,
  sleep,
  store,
  waitForStore,
} from './lib.mjs'

const cfg = config()
const core = coreApi(cfg.coreHttp)
const out = { ok: false, phaseA: {}, phaseB: {}, phaseC: {} }

const spokenSince = async (n) => {
  const r = await fetch(`${cfg.ttsUrl}/__spoken`)
  const j = await r.json()
  return j.spoken.slice(n).map((s) => s.input ?? '')
}
const spokenCount = async () => (await (await fetch(`${cfg.ttsUrl}/__spoken`)).json()).count

const browser = await launch()
try {
  const page = await newPage(browser)
  await page.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForStore(page, (s) => s.connection.state === 'open' && !s.awaitingSnapshot, {
    label: 'connected',
  })
  // The speech player is built lazily on the first gesture or the first line.
  await page.mouse.click(20, 20)
  await sleep(500)

  // ───────────────────────────── phase A ──────────────────────────────
  const moduleUrl =
    resolveModuleUrl(page, /\/act\/marker-parser\.ts/) ||
    resolveModuleUrl(page, /\/act\/index\.ts/) ||
    resolveModuleUrl(page, /airi-bridge\/src\/index\.ts/)
  out.phaseA.moduleUrl = moduleUrl
  out.phaseA.actRequests = page.__requests.filter((u) => u.includes('/act/'))

  if (!moduleUrl) {
    out.phaseA.error =
      'the running app never requested the ACT parser module; a probe cannot ' +
      'resolve the instance it is using and must not import a second copy'
  } else {
    out.phaseA.cases = await page.evaluate(async ({ url }) => {
      const mod = await import(/* @vite-ignore */ url)
      const create = mod.createMarkerParser
      if (!create) return [{ error: `no createMarkerParser in ${url}` }]

      async function run(chunks) {
        const literals = []
        const specials = []
        const parser = create(async (e) => {
          if (e.type === 'literal') literals.push(e.text)
          else specials.push(e.raw)
        })
        for (const c of chunks) await parser.consume(c)
        await parser.end()
        return { spoken: literals.join(''), specials }
      }

      const token = '<|ACT {"emotion":"happy"}|>'
      const line = `Yes! ${token} Well done.`
      const open = line.indexOf(token)
      return [
        // cut one character into the opener: '…<' + '|ACT …'
        { name: 'split-inside-opener', ...(await run([line.slice(0, open + 1), line.slice(open + 1)])) },
        // cut immediately after the opener
        { name: 'split-after-opener', ...(await run([line.slice(0, open + 2), line.slice(open + 2)])) },
        // cut in the middle of the payload
        { name: 'split-in-payload', ...(await run([line.slice(0, open + 12), line.slice(open + 12)])) },
        // cut one character into the closer: '…|' + '>'
        {
          name: 'split-inside-closer',
          ...(await run([line.slice(0, open + token.length - 1), line.slice(open + token.length - 1)])),
        },
        // one character at a time — the pathological case
        { name: 'one-char-at-a-time', ...(await run(line.split(''))) },
        // an unterminated token at end of stream must be dropped, not spoken
        { name: 'unterminated', ...(await run(['All done. <|ACT {"emo'])) },
      ]
    }, { url: moduleUrl })
  }

  // ───────────────────────────── phase B ──────────────────────────────
  {
    const before = await spokenCount()
    await core.say({
      text: 'Great job! <|ACT {"emotion":"happy"}|> Now look at the board.',
      turnId: 'i6-b',
    })
    await sleep(4000)
    out.phaseB.tts = await spokenSince(before)
    const s = await store(page)
    out.phaseB.emotion = s.avatar.emotion
    out.phaseB.subtitle = s.speechSubtitle
    out.phaseB.transcript = s.transcript.slice(-3)
  }

  // ───────────────────────────── phase C ──────────────────────────────
  // The scripted model has already been told to stream a `classroom_say`
  // whose arguments are cut in half mid-token (set from pytest).
  {
    const before = await spokenCount()
    await core.startLesson(0)
    let turn = null
    try {
      const r = await fetch(`${cfg.coreHttp}/dev/agent/turn`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: '{}',
      })
      turn = await r.json()
    } catch (err) {
      out.phaseC.turnError = String(err)
    }
    out.phaseC.turn = turn
    await sleep(5000)
    out.phaseC.tts = await spokenSince(before)
    const s = await store(page)
    out.phaseC.emotion = s.avatar.emotion
    out.phaseC.subtitle = s.speechSubtitle
    out.phaseC.transcript = s.transcript.slice(-4)
    await core.control('pause')
  }

  out.pageErrors = page.__pageErrors
  out.consoleErrors = page.__consoleErrors
  out.ok = true
} catch (err) {
  out.error = String(err && err.stack ? err.stack : err)
} finally {
  await browser.close()
}

result(out)
