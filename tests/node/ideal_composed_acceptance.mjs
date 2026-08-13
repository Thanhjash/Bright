/**
 * Operator-run ideal composition acceptance lane.
 *
 * Unlike integration scenarios, this opens two persistent Chromium contexts
 * and acts only through the visible UI. It never opens a test WebSocket,
 * calls `/dev`, or sends an ACK, answer, or capability. CDP observes the
 * existing Stage page's frames and stores only event order/type and opaque
 * turn slots -- never text, transcripts, credentials, cookies, or payloads.
 */

import { chromium, LAUNCH_ARGS, result } from './lib.mjs'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { tmpdir } from 'node:os'

const DEFAULT_TIMEOUT_MS = 180_000

function parseArgs(argv) {
  // pytest's browser bridge passes a JSON object; the shell uses flags.
  if (argv[0]?.startsWith('{')) return JSON.parse(argv[0])
  const parsed = {}
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (!arg.startsWith('--')) throw new Error(`unexpected argument ${arg}`)
    const key = arg.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())
    if (key === 'requireAgentProposal' || key === 'allowNoAgent') {
      parsed[key] = true
      continue
    }
    const value = argv[++i]
    if (!value || value.startsWith('--')) throw new Error(`${arg} needs a value`)
    parsed[key] = value
  }
  return parsed
}

function normalized(raw) {
  const mode = raw.mode ?? 'manual-physical-mic'
  if (!['manual-physical-mic', 'fake-audio-file'].includes(mode))
    throw new Error(`mode must be manual-physical-mic or fake-audio-file, got ${mode}`)
  const uiOrigin = String(raw.uiOrigin ?? 'http://127.0.0.1:3000').replace(/\/$/, '')
  const timeoutMs = Number(raw.timeoutMs ?? raw.timeout ?? DEFAULT_TIMEOUT_MS)
  if (!Number.isFinite(timeoutMs) || timeoutMs < 20_000)
    throw new Error('timeoutMs must be at least 20000')
  const fakeAudioFile = raw.fakeAudioFile ? resolve(String(raw.fakeAudioFile)) : undefined
  if (mode === 'fake-audio-file' && !fakeAudioFile)
    throw new Error('fake-audio-file mode requires --fake-audio-file /absolute/path.wav')
  return {
    mode,
    uiOrigin,
    timeoutMs,
    fakeAudioFile,
    expectedLessonId: String(raw.expectedLessonId ?? 'ideal-composed-one-turn'),
    artifacts: resolve(String(raw.artifacts ?? process.env.BRIGHT_ARTIFACTS ?? 'tests/.artifacts/ideal-composed')),
    // Audio-only diagnostics must opt out explicitly. Ideal acceptance requires
    // one committed hosted-Hermes proposal by default.
    requireAgentProposal: raw.allowNoAgent ? false : raw.requireAgentProposal !== false,
  }
}

function safeError(error) {
  // Browser/network messages can echo URLs or response bodies. Keep only a
  // stable category in shareable classroom artifacts.
  const message = String(error?.message ?? error)
  if (/timed out/i.test(message)) return 'timeout'
  if (/navigation|net::/i.test(message)) return 'navigation_failed'
  if (/permission|microphone/i.test(message)) return 'microphone_unavailable'
  return 'acceptance_failed'
}

function createLedger() {
  const rows = []
  const turns = new Map()
  let nextTurn = 0
  const slot = (id) => {
    if (!id) return 'unknown-turn'
    if (!turns.has(id)) turns.set(id, `turn-${++nextTurn}`)
    return turns.get(id)
  }
  return {
    note(client, direction, frame) {
      if (!frame || typeof frame.type !== 'string') return
      const payload = frame.payload && typeof frame.payload === 'object' ? frame.payload : {}
      const row = { order: rows.length + 1, client, direction, type: frame.type }
      if (typeof frame.stateVersion === 'number') row.stateVersion = frame.stateVersion
      if (frame.type === 'speech.turn.started') {
        row.turn = slot(payload.speechTurnId)
        row.source = payload.source === 'agent' ? 'agent' : 'non-agent'
      }
      else if (frame.type === 'speech.playback.started' || frame.type === 'speech.playback.finished') {
        row.turn = slot(payload.speechTurnId)
        if (typeof payload.status === 'string') row.status = payload.status
        if (frame.type === 'speech.playback.started' && payload.metrics) {
          row.causalAudioStart = Number.isFinite(payload.metrics.audioContextTime)
            && Number.isFinite(payload.metrics.firstAudioMs)
        }
      }
      else if (frame.type === 'class.turn.assigned') {
        row.assignment = slot(payload.assignmentId)
        row.target = slot(payload.targetId)
      }
      else if (frame.type === 'student.response.accepted') {
        row.outcome = typeof payload.outcome === 'string' ? payload.outcome : 'unknown'
      }
      else if (frame.type === 'response.capture.ready') {
        row.status = payload.status === 'ready' ? 'ready' : 'failed'
        if (typeof payload.reason === 'string') row.reason = payload.reason.slice(0, 64)
      }
      else if (frame.type === 'lesson.position') {
        row.lessonId = typeof payload.lessonId === 'string' ? payload.lessonId : 'unknown'
        row.stage = typeof payload.stage === 'string' ? payload.stage : 'unknown'
      }
      else if (frame.type === 'scene.snapshot') {
        row.lessonId = typeof payload.lesson?.lessonId === 'string'
          ? payload.lesson.lessonId
          : 'unknown'
        row.stage = typeof payload.lesson?.stage === 'string' ? payload.lesson.stage : 'unknown'
      }
      else if (frame.type === 'class.session.updated') {
        row.status = typeof payload.status === 'string' ? payload.status : 'unknown'
      }
      else if (frame.type === 'classroom.status') {
        row.status = typeof payload.status === 'string' ? payload.status : 'unknown'
        if (typeof payload.reason === 'string') row.reason = payload.reason.slice(0, 64)
      }
      else if (frame.type === 'error') {
        row.code = typeof payload.code === 'string' ? payload.code.slice(0, 64) : 'unknown'
      }
      rows.push(row)
    },
    http(client, kind, status) {
      rows.push({ order: rows.length + 1, client, direction: 'http', type: kind, status })
    },
    rows,
  }
}

async function observeFrames(page, ledger, client) {
  const session = await page.context().newCDPSession(page)
  await session.send('Network.enable')
  const capture = (direction) => ({ response }) => {
    try { ledger.note(client, direction, JSON.parse(response.payloadData)) } catch {}
  }
  session.on('Network.webSocketFrameReceived', capture('received'))
  session.on('Network.webSocketFrameSent', capture('sent'))
  session.on('Network.responseReceived', ({ response }) => {
    try {
      const url = new URL(response.url)
      if (url.pathname === '/audio/speech') ledger.http(client, 'http.audio.speech', response.status)
      if (url.pathname === '/audio/transcriptions') ledger.http(client, 'http.audio.transcriptions', response.status)
    }
    catch {}
  })
  return session
}

async function waitFor(page, predicate, timeoutMs, arg) {
  await page.waitForFunction(predicate, arg, { timeout: timeoutMs })
}

async function waitUntil(predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const value = predicate()
    if (value) return value
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error('timed out waiting for the composed terminal sequence')
}

async function minimalState(page) {
  return page.evaluate(() => {
    return {
      path: window.location.pathname,
      title: document.title,
      voicePhase: document.querySelector('[data-testid="answer-station-ready"]')?.getAttribute('data-voice-phase') ?? null,
      notice: document.querySelector('[role="status"]')?.textContent?.slice(0, 120) ?? null,
    }
  })
}

function assertCommitAfterPlayback(rows) {
  const agentTurns = [...new Map(
    rows
      .filter((row) => row.type === 'speech.turn.started' && row.source === 'agent')
      .map((row) => [row.turn, row]),
  ).values()]
  if (agentTurns.length !== 1)
    throw new Error(`expected exactly one agent speech turn, observed ${agentTurns.length}`)
  const turn = agentTurns[0].turn
  const terminal = rows.find((row) => row.direction === 'sent'
    && row.client === 'stage'
    && row.type === 'speech.playback.finished'
    && row.turn === turn
    && row.status === 'completed')
  if (!terminal) throw new Error('agent speech did not receive a Stage-originated completed playback acknowledgement')
  const started = rows.find((row) => row.direction === 'sent'
    && row.client === 'stage'
    && row.type === 'speech.playback.started'
    && row.turn === turn
    && row.causalAudioStart === true)
  if (!started) throw new Error('agent speech has no causal WebAudio start evidence')
  if (started.order >= terminal.order) throw new Error('agent playback terminal preceded its causal WebAudio start')
  const committed = rows.find((row) => row.order > terminal.order
    && row.direction === 'received'
    && ['scene.update', 'lesson.position', 'class.session.updated'].includes(row.type))
  if (!committed) throw new Error('Core did not publish a post-playback committed state transition')
  return { agentTurn: turn, playbackFinishedOrder: terminal.order, commitOrder: committed.order }
}

function assertRealVoicePath(rows) {
  const tts = rows.some((row) => row.client === 'stage'
    && row.type === 'http.audio.speech' && row.status === 200)
  const asr = rows.some((row) => row.client === 'control'
    && row.type === 'http.audio.transcriptions' && row.status === 200)
  const correct = rows.some((row) => row.direction === 'received'
    && row.type === 'student.response.accepted' && row.outcome === 'correct')
  if (!tts) throw new Error('Stage never completed a real Piper request')
  if (!asr) throw new Error('Control never completed a real ASR request')
  if (!correct) throw new Error('Core did not accept the real ASR result as correct')
  return { piperHttp200: true, asrHttp200: true, correctOutcome: true }
}

async function run(raw) {
  const cfg = normalized(raw)
  const out = {
    ok: false,
    mode: cfg.mode,
    uiOrigin: cfg.uiOrigin,
    coverage: [
      'two persistent Chromium contexts: Stage and Control',
      'visible UI lesson start and answer-station capture',
      'Stage-originated playback acknowledgements only',
      'optional committed hosted Hermes proposal evidence',
    ],
    exclusions: [
      'acoustic-pressure measurement at the speaker cone',
      'room ASR accuracy, child speech, or grading-quality claims',
    ],
  }
  if (cfg.fakeAudioFile) {
    const fixture = await readFile(cfg.fakeAudioFile)
    out.inputFixture = {
      sha256: createHash('sha256').update(fixture).digest('hex'),
      bytes: fixture.byteLength,
    }
  }
  const stageProfile = await mkdtemp(resolve(tmpdir(), 'bright-stage-acceptance-'))
  const controlProfile = await mkdtemp(resolve(tmpdir(), 'bright-control-acceptance-'))
  let stageContext
  let controlContext
  let stageSession
  let controlSession
  let ledger
  try {
    const progress = (gate) => process.stderr.write(`Bright acceptance gate: ${gate}\n`)
    stageContext = await chromium.launchPersistentContext(stageProfile, {
      executablePath: process.env.CHROME_PATH,
      args: LAUNCH_ARGS,
      viewport: { width: 1600, height: 900 },
    })
    const controlArgs = [...LAUNCH_ARGS]
    if (cfg.mode === 'fake-audio-file') {
      controlArgs.push('--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream')
      controlArgs.push(`--use-file-for-fake-audio-capture=${cfg.fakeAudioFile}`)
    }
    controlContext = await chromium.launchPersistentContext(controlProfile, {
      executablePath: process.env.CHROME_PATH,
      args: controlArgs,
      viewport: { width: 1366, height: 768 },
    })
    // This permits the selected host microphone; it never replaces it. In
    // manual mode that remains the physical answer-station input device.
    await controlContext.grantPermissions(['microphone'], { origin: cfg.uiOrigin })

    const stage = await stageContext.newPage()
    const control = await controlContext.newPage()
    ledger = createLedger()
    stageSession = await observeFrames(stage, ledger, 'stage')
    controlSession = await observeFrames(control, ledger, 'control')
    await stage.goto(`${cfg.uiOrigin}/classroom`, { waitUntil: 'domcontentloaded', timeout: cfg.timeoutMs })
    await control.goto(`${cfg.uiOrigin}/control`, { waitUntil: 'domcontentloaded', timeout: cfg.timeoutMs })
    progress('routes-open')

    await waitUntil(
      () => ledger.rows.some((row) => row.client === 'stage'
        && row.direction === 'received' && row.type === 'stage.lease.granted'),
      cfg.timeoutMs,
    )
    progress('stage-lease')
    await control.locator('#roster-input').fill('acceptance-learner, Acceptance Learner, A1')
    await control.getByRole('button', { name: 'Check microphone' }).click()
    await control.getByRole('button', { name: 'Microphone ready' }).waitFor({ timeout: cfg.timeoutMs })
    progress('microphone-ready')
    await control.getByTestId('start-lesson').waitFor({ state: 'visible', timeout: cfg.timeoutMs })
    await waitFor(
      control,
      () => !document.querySelector('[data-testid="start-lesson"]')?.hasAttribute('disabled'),
      cfg.timeoutMs,
    )
    await control.getByTestId('start-lesson').click()
    progress('lesson-start-requested')
    await waitUntil(
      () => ledger.rows.some((row) => row.direction === 'received'
        && row.type === 'lesson.position'
        && row.lessonId === cfg.expectedLessonId),
      cfg.timeoutMs,
    )
    progress('lesson-identity')

    await waitFor(
      control,
      () => {
        const ready = document.querySelector('[data-testid="answer-station-ready"]')
        return ready?.getAttribute('data-voice-phase') === 'assigned'
          && ready?.getAttribute('data-output-quiet') === 'true'
          && !ready?.hasAttribute('disabled')
      },
      cfg.timeoutMs,
    )
    progress('turn-assigned')
    // The same visible button a learner presses. Afterwards the browser's real
    // selected input (or only its configured file device) supplies the audio.
    await control.getByTestId('answer-station-ready').click()
    await waitFor(
      control,
      () => document.querySelector('[data-testid="answer-station-ready"]')?.getAttribute('data-voice-phase') === 'listening',
      cfg.timeoutMs,
    )
    progress('capture-listening')
    if (cfg.mode === 'manual-physical-mic')
      process.stderr.write('Bright acceptance: speak the expected answer into the physical microphone now.\n')

    await waitFor(
      control,
      () => document.querySelector('[data-testid="answer-station-ready"]')?.getAttribute('data-voice-phase') === 'idle',
      cfg.timeoutMs,
    )
    out.voicePath = assertRealVoicePath(ledger.rows)
    if (cfg.requireAgentProposal)
      out.commit = await waitUntil(() => {
        try { return assertCommitAfterPlayback(ledger.rows) } catch { return null }
      }, cfg.timeoutMs)

    out.events = ledger.rows
    out.stage = await minimalState(stage)
    out.control = await minimalState(control)
    out.ok = true
  }
  catch (error) {
    out.error = safeError(error)
  }
  finally {
    try { await stageSession?.detach() } catch {}
    try { await controlSession?.detach() } catch {}
    try { await controlContext?.close() } catch {}
    try { await stageContext?.close() } catch {}
    await rm(controlProfile, { recursive: true, force: true })
    await rm(stageProfile, { recursive: true, force: true })
    if (ledger) out.events = ledger.rows
    await mkdir(cfg.artifacts, { recursive: true })
    // The result is the sole durable artifact: no profile, cookies, transcript,
    // frame body, bearer secret, or answer text survives this process.
    await writeFile(resolve(cfg.artifacts, 'result.json'), `${JSON.stringify(out, null, 2)}\n`, 'utf8')
  }
  return out
}

const out = await run(parseArgs(process.argv.slice(2)))
result(out)
process.exitCode = out.ok ? 0 : 1
