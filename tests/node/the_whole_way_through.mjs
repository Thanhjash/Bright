/**
 * The whole way through, the way a child does it.
 *
 * Every other script here tests one organ. This walks the product: the front
 * door, the camera at it, the enrolment offer, the press that opens a period,
 * the room itself, and the way back out. It screenshots each step so a person
 * can look, and it asserts on structure -- roles, states, geometry -- rather
 * than pixels, so it fails on a regression and not on a shade of blue.
 *
 *   PLAYWRIGHT_CORE=... CHROME_PATH=... node tests/node/the_whole_way_through.mjs
 *
 * It never presses the period card by default: opening a class spends a model
 * turn and takes a minute. Pass ENTER=1 when you want the full walk.
 */
import { chromium, LAUNCH_ARGS } from './lib.mjs'

const UI = process.env.LEARN_UI || 'http://127.0.0.1:3000'
const ENTER = process.env.ENTER === '1'
const SHOTS = process.env.SHOT_DIR || 'tests/.artifacts/walk'

const checks = {}
const notes = []
const shots = []
let step = 0

function check(name, ok, detail) {
  checks[name] = ok
  if (!ok && detail !== undefined) notes.push(`${name}: ${JSON.stringify(detail)}`)
}

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: [...LAUNCH_ARGS, '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
})
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  permissions: ['camera', 'microphone'],
})
const page = await ctx.newPage()
const pageErrors = []
page.on('pageerror', e => pageErrors.push(String(e).slice(0, 200)))
page.on('console', m => { if (m.type() === 'error') pageErrors.push(m.text().slice(0, 160)) })

async function shot(label) {
  const path = `${SHOTS}/${String(++step).padStart(2, '0')}-${label}.png`
  await page.screenshot({ path })
  shots.push(path)
}

// ---------------------------------------------------------------- 1. the door
await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('[data-lobby="period"]', { timeout: 20000 }).catch(() => {})
await page.waitForTimeout(1500)
await shot('front-door')

const cards = await page.$$eval('[data-lobby="period"]', els => els.map(e => ({
  n: Number(e.getAttribute('data-period')),
  state: e.getAttribute('data-state'),
  disabled: e.disabled,
})))
check('the door lists the unit\'s real periods', cards.length === 3, cards)
check('exactly one period is pressable', cards.filter(c => !c.disabled).length === 1, cards)
check('the pressable one is the next unheld period',
  cards.find(c => !c.disabled)?.state === 'next', cards)
check('locked periods cannot be pressed',
  cards.filter(c => c.state === 'locked').every(c => c.disabled), cards)

// The front door must never claim the audio lease -- that socket is what makes
// Core open a class, and a class opened here would greet an empty page.
const stageOwnerAtDoor = await fetch(`${process.env.CORE_HTTP || 'http://127.0.0.1:8004'}/teacher/status`)
  .then(r => r.json()).then(b => b.stageAudioOwner).catch(() => null)
check('the door holds no audio lease', !stageOwnerAtDoor, stageOwnerAtDoor)

// ------------------------------------------------------- 2. readiness is honest
const readiness = await page.$eval('[data-lobby="readiness-text"]', e => e.innerText).catch(() => null)
check('the room says what it is doing', typeof readiness === 'string' && readiness.length > 0, readiness)
notes.push(`readiness: ${readiness}`)

// -------------------------------------------------------------- 3. the camera
const camPhase = await page.getAttribute('[data-lobby="camera"]', 'data-phase').catch(() => null)
check('the camera reaches a real state',
  ['looking', 'stranger', 'known', 'no-camera'].includes(camPhase), camPhase)

if (camPhase === 'stranger') {
  await page.click('[data-lobby="im-new"]')
  await page.waitForTimeout(500)
  await shot('enrolment-offered')
  const goDisabled = await page.isDisabled('[data-lobby="enrol-go"]')
  check('enrolment is refused without a name and consent', goDisabled)
  await page.fill('[data-lobby="camera"] input[type="text"], [data-lobby="camera"] input:not([type])', 'Minh')
  await page.waitForTimeout(200)
  const stillDisabled = await page.isDisabled('[data-lobby="enrol-go"]')
  check('a name alone is not consent', stillDisabled)
  await page.check('[data-lobby="camera"] input[type="checkbox"]')
  await page.waitForTimeout(200)
  check('name plus consent unlocks enrolment', await page.isEnabled('[data-lobby="enrol-go"]'))
  await shot('enrolment-consented')
}

// ---------------------------------------------------------------- 4. the room
if (ENTER) {
  await page.click('[data-lobby="period"]:not([disabled])')
  await page.waitForURL('**/classroom', { timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(6000)
  await shot('the-room')
  check('pressing a period opens the room', page.url().endsWith('/classroom'))

  const geom = await page.evaluate(() => {
    const box = (sel) => {
      const e = document.querySelector(sel)
      if (!e) return null
      const r = e.getBoundingClientRect()
      return { x: r.x, y: r.y, w: r.width, h: r.height }
    }
    return {
      board: box('[data-stage="board"]'),
      avatar: box('[data-stage="avatar"]'),
      camera: box('[data-stage="camera-slot"]'),
      leave: box('[data-stage="leave"]'),
      vw: window.innerWidth,
      vh: window.innerHeight,
    }
  })
  check('the board is on the wall', Boolean(geom.board), geom.board)
  check('the teacher is on the right',
    Boolean(geom.avatar) && geom.avatar.x > geom.vw * 0.5, geom.avatar)
  check('the child\'s camera is on the left',
    Boolean(geom.camera) && geom.camera.x < geom.vw * 0.3, geom.camera)
  // Her head must reach a little above the board's midline: high enough to read
  // as standing in front of it, not so high she covers the chalk.
  const headTop = geom.avatar ? geom.avatar.y / geom.vh : 1
  check('the teacher\'s head sits just above the board\'s midline',
    headTop > 0.18 && headTop < 0.40, { headTop })
  check('there is a way out', Boolean(geom.leave), geom.leave)

  // --------------------------------------------------------- 5. and back out
  await page.click('[data-stage="leave"]')
  await page.waitForTimeout(2500)
  await shot('back-at-the-door')
  check('the door takes you back', new URL(page.url()).pathname === '/')

  const after = await fetch(`${process.env.CORE_HTTP || 'http://127.0.0.1:8004'}/teacher/status`)
    .then(r => r.json()).catch(() => ({}))
  // Leaving is not closing. A child who steps out returns to the same period.
  check('leaving does not end the period', after.sessionOpen === true, after.sessionOpen)
}

check('no page errors anywhere', pageErrors.length === 0, pageErrors)

const pass = Object.values(checks).every(Boolean)
console.log(`@@RESULT@@ ${JSON.stringify({ pass, checks, notes, shots, pageErrors })}`)
await browser.close()
process.exit(pass ? 0 : 1)
