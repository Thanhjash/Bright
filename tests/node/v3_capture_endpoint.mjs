/**
 * Product voice unit in a real browser runtime.
 *
 * The endpoint detector deliberately is not called a VAD: it observes energy,
 * requires a sustained onset, and closes a take after sustained silence.  The
 * answer-station Ready action supplies identity/turn intent; this detector only
 * decides whether the take contained speech-like energy and when it ended.
 */
import { config, launch, newPage, result } from './lib.mjs'

const cfg = config()
const out = { ok: false }
const browser = await launch()

try {
  const page = await newPage(browser)
  await page.goto(`${cfg.uiOrigin}/control`, { waitUntil: 'domcontentloaded', timeout: 60000 })

  out.cases = await page.evaluate(async () => {
    const { ConservativeEndpointDetector } = await import('/src/speech/captureEndpoint.ts')
    const create = () => new ConservativeEndpointDetector({
      noiseFloor: 0.01,
      onsetMs: 160,
      minSpeechMs: 300,
      endSilenceMs: 800,
      maxDurationMs: 8_000,
    })

    const run = (levels, stepMs = 40) => {
      const detector = create()
      let now = 0
      let terminal = null
      for (const level of levels) {
        terminal = detector.sample(level, now)
        now += stepMs
        if (terminal) break
      }
      return terminal ?? detector.deadline(now)
    }

    const firstFrame = create()
    const firstFrameResult = firstFrame.sample(0.005, 0)
    const beforeDeadline = create()
    let preDeadlineResult = null
    for (let now = 0; now < 3_000; now += 40)
      preDeadlineResult = preDeadlineResult ?? beforeDeadline.sample(0.005, now)

    return {
      firstFrameResult,
      firstFrameHasSpeech: firstFrame.hasSpeech,
      preDeadlineResult,
      silence: run(Array(150).fill(0.005)),
      isolatedNoise: run([
        ...Array(20).fill(0.005),
        0.18,
        ...Array(120).fill(0.005),
      ]),
      speech: run([
        ...Array(10).fill(0.005),
        ...Array(25).fill(0.12),
        ...Array(25).fill(0.004),
      ]),
      hardCap: run(Array(250).fill(0.12)),
    }
  })

  out.pageErrors = page.__pageErrors
  out.ok = true
} catch (error) {
  out.error = String(error?.stack ?? error)
} finally {
  await browser.close()
}

result(out)
