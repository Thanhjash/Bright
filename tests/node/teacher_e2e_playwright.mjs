/** Chromium e2e: Stage hears Hermes; /learn is a mouth, not a speaker. */
import { mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { launch, newPage, result } from './lib.mjs'

const ui = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const core = process.env.CORE_HTTP || 'http://127.0.0.1:8004'
const artifacts = process.env.LEARN_ARTIFACTS || join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  '.artifacts',
)
await mkdir(artifacts, { recursive: true })

const out = {
  ok: false,
  lease: false,
  speechUp: false,
  opening: null,
  reply: null,
  picture: null,
  holdToTalk: false,
  stageTts: [],
  stageWav: [],
  learnTts: [],
  wsSpeech: [],
  mouthPeak: 0,
  spoke: false,
  live2d: false,
  shots: [],
  error: null,
}

const browser = await launch()
const stage = await newPage(browser)
const learn = await newPage(browser)
stage.setDefaultTimeout(120000)
learn.setDefaultTimeout(120000)

function track(page, bucket) {
  page.on('request', (req) => {
    const url = req.url()
    if (url.includes('/audio/speech')) bucket.tts.push(url)
    if (url.includes('.wav')) bucket.wav.push(url)
  })
}

const stageMedia = { tts: out.stageTts, wav: out.stageWav }
const learnMedia = { tts: out.learnTts, wav: [] }
track(stage, stageMedia)
track(learn, learnMedia)

stage.on('websocket', (ws) => {
  ws.on('framereceived', (frame) => {
    try {
      const msg = JSON.parse(String(frame.payload))
      if (String(msg.type || '').startsWith('speech.'))
        out.wsSpeech.push(msg.type)
    } catch { /* ignore */ }
  })
})

try {
  await stage.goto(`${ui}/classroom`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await stage.mouse.click(80, 80)
  const leased = await stage.waitForFunction(async () => {
    try {
      const body = await fetch('http://127.0.0.1:8004/teacher/status').then((r) => r.json())
      return Boolean(body.stageAudioOwner && body.speechUp)
    } catch {
      return false
    }
  }, null, { timeout: 20000 }).then(() => true).catch(() => false)
  const status = await fetch(`${core}/teacher/status`).then((r) => r.json())
  out.lease = Boolean(status.stageAudioOwner)
  out.speechUp = Boolean(status.speechUp)
  if (!leased) throw new Error(`Stage did not own audio: ${JSON.stringify(status)}`)
  out.live2d = await stage.evaluate(() => Boolean(window.__brightStage))
  const wall = stage.locator('[data-stage="wall"]')
  await wall.waitFor({ timeout: 8000 })
  const wallSrc = await wall.getAttribute('src')
  if (!wallSrc || !/classroom-wall/.test(wallSrc))
    throw new Error(`wall photo missing: ${wallSrc}`)
  if (await stage.locator('text=Ready').count())
    throw new Error('CSS Ready-sun is still on Stage')
  await stage.screenshot({ path: join(artifacts, 'e2e-01-stage.png'), fullPage: true })
  out.shots.push('e2e-01-stage.png')

  await learn.goto(`${ui}/learn`, { waitUntil: 'domcontentloaded', timeout: 30000 })
  const teacher = learn.locator('[data-role="teacher"]')
  await teacher.first().waitFor({ timeout: 120000 })
  out.opening = (await teacher.first().innerText()).trim()
  const img = learn.locator('[data-board="picture"]')
  if (await img.count())
    out.picture = await img.getAttribute('src')
  out.holdToTalk = (await learn.getByRole('button', { name: /Hold to talk/i }).count()) > 0
  await learn.screenshot({ path: join(artifacts, 'e2e-02-learn-open.png'), fullPage: true })
  out.shots.push('e2e-02-learn-open.png')
  if (!out.opening) throw new Error('no teacher opening on /learn')

  await stage.waitForTimeout(2500)
  const mouthSamples = []
  for (let i = 0; i < 12; i++) {
    mouthSamples.push(await stage.evaluate(() => {
      const s = window.__bright?.getState?.()
      return {
        speaking: Boolean(s?.avatar?.speaking),
        mouth: Number(s?.avatar?.mouthOpen || 0),
      }
    }))
    await stage.waitForTimeout(200)
  }
  out.mouthPeak = Math.max(0, ...mouthSamples.map((s) => s.mouth))
  out.spoke = mouthSamples.some((s) => s.speaking) || out.wsSpeech.includes('speech.turn.started')

  const heard = out.stageTts.length + out.stageWav.length
  if (!out.wsSpeech.includes('speech.turn.started'))
    throw new Error(`Stage missed speech.turn (${out.wsSpeech.join(',') || 'none'})`)
  if (!heard)
    throw new Error('Stage got speech.turn but fetched no Piper/wav')
  if (out.learnTts.length)
    throw new Error(`/learn must not call Piper (got ${out.learnTts.length})`)
  if (!out.holdToTalk)
    throw new Error('Hold to talk missing on /learn')

  const before = await teacher.count()
  await learn.getByPlaceholder('Type to your teacher').fill('hello')
  await learn.getByRole('button', { name: 'Send' }).click()
  await learn.locator('[data-role="learner"]').filter({ hasText: 'hello' }).waitFor({ timeout: 8000 })
  await learn.waitForFunction((n) => {
    const nodes = [...document.querySelectorAll('[data-role="teacher"]')]
    const last = nodes[nodes.length - 1]?.textContent?.trim() || ''
    return nodes.length > n && last.length > 0
  }, before, { timeout: 120000 })
  out.reply = (await teacher.last().innerText()).trim()
  await learn.screenshot({ path: join(artifacts, 'e2e-03-learn-reply.png'), fullPage: true })
  out.shots.push('e2e-03-learn-reply.png')
  if (!out.reply) throw new Error('teacher did not answer typed hello')

  await stage.waitForTimeout(1500)
  if (out.stageTts.length + out.stageWav.length <= heard)
    throw new Error('second teacher turn did not play on Stage')

  await stage.screenshot({ path: join(artifacts, 'e2e-04-stage-after.png'), fullPage: true })
  out.shots.push('e2e-04-stage-after.png')
  out.ok = true
} catch (err) {
  out.error = String(err?.message || err)
  await Promise.all([
    stage.screenshot({ path: join(artifacts, 'e2e-stage-fail.png'), fullPage: true }).catch(() => {}),
    learn.screenshot({ path: join(artifacts, 'e2e-learn-fail.png'), fullPage: true }).catch(() => {}),
  ])
} finally {
  await browser.close().catch(() => {})
  result(out)
  if (!out.ok) process.exit(1)
}
