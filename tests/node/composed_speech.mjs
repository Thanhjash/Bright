/**
 * Real-browser speech composition probe.
 *
 * This intentionally does not import Bright internals or fabricate speech
 * lifecycle ACKs. Chromium opens a fake *browser* microphone, records a real
 * MediaRecorder blob, uploads it to the configured local ASR endpoint, then
 * fetches Piper WAV and asks the browser audio pipeline to play it. It proves
 * endpoint and browser boundary composition, not room recognition quality or
 * physical speaker/microphone acoustics.
 */
import { config, launchPersistent, instrumentPage, result } from './lib.mjs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const cfg = config()
const out = { ok: false, coverage: 'browser_fake_mic_to_real_asr_and_real_tts_to_browser_audio' }
const profile = await mkdtemp(join(tmpdir(), 'bright-composed-smoke-'))
const context = await launchPersistent(profile, { viewport: { width: 1024, height: 768 } })

try {
  const page = instrumentPage(await context.newPage())
  await page.goto(`${cfg.uiOrigin}/control`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  out.browser = await page.evaluate(async (speechUrl) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    try {
      const tracks = stream.getAudioTracks()
      if (tracks.length !== 1 || tracks[0].readyState !== 'live')
        throw new Error('browser did not provide a live audio track')

      const recorder = new MediaRecorder(stream)
      const chunks = []
      recorder.addEventListener('dataavailable', (event) => {
        if (event.data.size) chunks.push(event.data)
      })
      const stopped = new Promise((resolve) => recorder.addEventListener('stop', resolve, { once: true }))
      recorder.start()
      await new Promise((resolve) => setTimeout(resolve, 900))
      recorder.stop()
      await stopped
      const clip = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      if (clip.size < 100)
        throw new Error(`browser microphone recording was unexpectedly small (${clip.size} bytes)`)

      const form = new FormData()
      form.append('file', clip, 'composed-smoke.webm')
      const asr = await fetch(`${speechUrl}/audio/transcriptions`, { method: 'POST', body: form })
      const asrBody = await asr.json().catch(() => null)
      if (!asr.ok)
        throw new Error(`ASR returned ${asr.status}: ${JSON.stringify(asrBody)?.slice(0, 300)}`)
      if (!asrBody || typeof asrBody.text !== 'string' || typeof asrBody.totalMs !== 'number')
        throw new Error('ASR response does not match Bright speech contract')

      const tts = await fetch(`${speechUrl}/audio/speech`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ input: 'Bright speech composition check.', voice: 'en' }),
      })
      const audioBytes = await tts.arrayBuffer()
      if (!tts.ok || audioBytes.byteLength <= 44)
        throw new Error(`TTS returned ${tts.status} with ${audioBytes.byteLength} bytes`)
      const audio = new Audio(URL.createObjectURL(new Blob([audioBytes], { type: 'audio/wav' })))
      audio.volume = 0.01
      await audio.play()
      await new Promise((resolve) => setTimeout(resolve, 150))
      const playing = !audio.paused
      audio.pause()
      URL.revokeObjectURL(audio.src)
      if (!playing) throw new Error('browser audio pipeline did not enter playing state')

      return {
        micTrackLabel: tracks[0].label,
        recordedBytes: clip.size,
        recorderMime: recorder.mimeType,
        asr: {
          model: asrBody.model,
          totalMs: asrBody.totalMs,
          textLength: asrBody.text.trim().length,
          // The fake browser microphone is not a child utterance. Do not
          // report its transcript, and never interpret it as accuracy proof.
        },
        tts: { bytes: audioBytes.byteLength, voice: tts.headers.get('X-Voice') },
      }
    } finally {
      stream.getTracks().forEach((track) => track.stop())
    }
  }, cfg.speechUrl)
  out.pageErrors = page.__pageErrors
  out.ok = true
} catch (error) {
  out.error = String(error?.stack ?? error)
} finally {
  await context.close()
  await rm(profile, { recursive: true, force: true })
}

result(out)
