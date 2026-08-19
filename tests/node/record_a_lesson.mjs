/**
 * Sit in the back of the room with a camera on.
 *
 * Opens the classroom exactly as the projector does, records the whole period,
 * and logs every line the class HEARS and every scene the board SHOWS. It
 * teaches nothing and drives nothing -- it is an observer, so what it records
 * is what a child would actually have seen and heard.
 *
 * State is read from the app's own store, never from pixels: a screenshot
 * cannot tell you the board changed to something that looks the same.
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.UI_HTTP || 'http://127.0.0.1:3000'
const OUT = process.env.RECORD_DIR || '.runtime/lesson-recording'
const MINUTES = Number(process.env.RECORD_MINUTES || 14)

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, args: LAUNCH_ARGS })
const ctx = await browser.newContext({
  viewport: { width: 1024, height: 768 },        // a cheap classroom projector
  recordVideo: { dir: OUT, size: { width: 1024, height: 768 } },
})
const page = await ctx.newPage()

const spoken = []
const scenes = []
const started = Date.now()
const stamp = () => ((Date.now() - started) / 1000).toFixed(1)

page.on('console', m => {
  const t = m.text()
  if (t.startsWith('@@SAY@@')) { spoken.push({ t: stamp(), text: t.slice(7).trim() }); console.log(`[${stamp()}s] SAY  ${t.slice(7).trim()}`) }
  else if (t.startsWith('@@SCENE@@')) { scenes.push({ t: stamp(), scene: t.slice(9).trim() }); console.log(`[${stamp()}s] BOARD ${t.slice(9).trim().slice(0, 120)}`) }
})

await page.goto(`${UI}/classroom`, { waitUntil: 'networkidle' })
await page.evaluate(() => {
  const store = window.__bright
  if (!store?.subscribe) { console.log('@@SCENE@@ (no store)'); return }
  let lastScene = '', lastSay = ''
  store.subscribe(st => {
    const scene = JSON.stringify({ kind: st.scene?.kind, props: st.scene?.props })
    if (scene !== lastScene) { lastScene = scene; console.log('@@SCENE@@ ' + scene) }
    const say = st.speech?.text || st.lastSpeech?.text || ''
    if (say && say !== lastSay) { lastSay = say; console.log('@@SAY@@ ' + say) }
  })
})

console.log(`recording ${MINUTES} min -> ${OUT}`)
await page.waitForTimeout(MINUTES * 60 * 1000)
await ctx.close()      // the video file is written here
await browser.close()
console.log(`@@RESULT@@ ${JSON.stringify({ spoken, sceneChanges: scenes.length })}`)
