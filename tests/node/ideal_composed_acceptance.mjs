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
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
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
  const attempts = Number(raw.attempts ?? 1)
  if (!Number.isInteger(attempts) || attempts < 1 || attempts > 3)
    throw new Error('attempts must be an integer from 1 to 3')
  const fakeAudioFile = raw.fakeAudioFile ? resolve(String(raw.fakeAudioFile)) : undefined
  if (mode === 'fake-audio-file' && !fakeAudioFile)
    throw new Error('fake-audio-file mode requires --fake-audio-file /absolute/path.wav')
  return {
    mode,
    uiOrigin,
    timeoutMs,
    attempts,
    fakeAudioFile,
    expectedLessonId: String(raw.expectedLessonId ?? (
      attempts === 3 ? 'ideal-composed-three-turn' : 'ideal-composed-one-turn'
    )),
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
  // Raw runtime identifiers never leave this closure. The durable artifact
  // receives only per-run opaque slots, while assertions can still follow the
  // exact capability and utterance relationships Core validates.
  const rows = []
  const slots = new Map()
  const counters = new Map()
  const slot = (kind, id) => {
    if (!id) return `unknown-${kind}`
    const key = `${kind}:${id}`
    if (!slots.has(key)) {
      const next = (counters.get(kind) ?? 0) + 1
      counters.set(kind, next)
      slots.set(key, `${kind}-${next}`)
    }
    return slots.get(key)
  }
  const safeStatus = (value, allowed, fallback = 'unknown') => (
    typeof value === 'string' && allowed.includes(value) ? value : fallback
  )
  const safeSource = (value) => {
    if (value === 'agent') return 'agent'
    if (value === 'core') return 'callout'
    return 'other'
  }
  const safeTypes = new Set([
    'stage.lease.granted',
    'class.turn.assigned',
    'class.turn.closed',
    'response.capture.requested',
    'response.capture.ready',
    'response.capture.started',
    'student.speech.final',
    'student.response.accepted',
    'speech.turn.started',
    'speech.playback.started',
    'speech.playback.finished',
    'scene.update',
    'lesson.position',
    'class.session.updated',
    'classroom.status',
    'error',
  ])
  return {
    note(client, direction, frame) {
      if (!frame || typeof frame.type !== 'string' || !safeTypes.has(frame.type)) return
      const payload = frame.payload && typeof frame.payload === 'object' ? frame.payload : {}
      const row = { order: rows.length + 1, client, direction, type: frame.type }
      if (typeof frame.stateVersion === 'number') row.stateVersion = frame.stateVersion
      if (frame.type === 'speech.turn.started') {
        row.speech = slot('speech', payload.speechTurnId)
        row.source = safeSource(payload.source)
      }
      else if (frame.type === 'speech.playback.started' || frame.type === 'speech.playback.finished') {
        row.speech = slot('speech', payload.speechTurnId)
        if (frame.type === 'speech.playback.finished')
          row.status = safeStatus(payload.status, ['completed', 'cancelled', 'failed'])
        if (frame.type === 'speech.playback.started' && payload.metrics) {
          row.causalAudioStart = Number.isFinite(payload.metrics.audioContextTime)
            && Number.isFinite(payload.metrics.firstAudioMs)
        }
      }
      else if (frame.type === 'class.turn.assigned') {
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
        if (payload.targetId) row.learner = slot('learner', payload.targetId)
      }
      else if (frame.type === 'response.capture.requested') {
        row.capture = slot('capture', payload.captureId)
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
      }
      else if (frame.type === 'response.capture.ready') {
        row.capture = slot('capture', payload.captureId)
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
        row.status = safeStatus(payload.status, ['ready', 'failed'])
      }
      else if (frame.type === 'response.capture.started') {
        row.capture = slot('capture', payload.captureId)
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
      }
      else if (frame.type === 'student.speech.final') {
        row.utterance = slot('utterance', payload.utteranceId)
        row.capture = slot('capture', payload.captureId)
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
      }
      else if (frame.type === 'student.response.accepted') {
        row.utterance = slot('utterance', payload.utteranceId)
        row.outcome = safeStatus(payload.outcome, ['correct', 'near', 'wrong', 'silence', 'timeout', 'rejected'])
      }
      else if (frame.type === 'class.turn.closed') {
        row.assignment = slot('assignment', payload.assignmentId)
        row.response = slot('response', payload.responseTurnId)
        row.outcome = safeStatus(payload.outcome, ['correct', 'near', 'wrong', 'uncertain', 'unhandled', 'silence', 'timeout', 'rejected'])
      }
      else if (frame.type === 'lesson.position') {
        if (typeof payload.lessonId === 'string') slot('lesson', payload.lessonId)
        row.stage = safeStatus(payload.stage, ['WARMUP', 'MODELING', 'GUIDED_PRACTICE', 'SAMPLED_RETRIEVAL', 'INDEPENDENT', 'CLOSURE'])
      }
      else if (frame.type === 'class.session.updated') {
        row.status = safeStatus(payload.status, ['PREPARING', 'RUNNING', 'PAUSED', 'RECOVERING', 'CLOSING', 'COMPLETED', 'ABORTED'])
      }
      else if (frame.type === 'classroom.status') {
        row.status = safeStatus(payload.readiness, ['ready', 'degraded', 'not_ready'])
      }
      rows.push(row)
    },
    http(client, kind, status) {
      rows.push({
        order: rows.length + 1,
        client,
        direction: 'http',
        type: kind,
        status: status >= 200 && status < 300 ? 'ok' : 'not_ok',
      })
    },
    hasLesson(lessonId) {
      return slots.has(`lesson:${lessonId}`)
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

function received(rows, client, type) {
  return rows.filter((row) => row.direction === 'received' && row.client === client && row.type === type)
}

function agentSpeechTurns(rows) {
  // Stage is the unique owner of audio. Looking only at its received events
  // prevents the Control broadcast copy from counting a proposal twice.
  return received(rows, 'stage', 'speech.turn.started').filter((row) => row.source === 'agent')
}

function lastBefore(rows, predicate, before) {
  return rows.filter((row) => row.order < before && predicate(row)).at(-1)
}

function firstBetween(rows, predicate, after, before = Infinity) {
  return rows.find((row) => row.order > after && row.order < before && predicate(row))
}

function correlatedCorrectCycles(rows) {
  return received(rows, 'control', 'student.response.accepted')
    .filter((row) => row.outcome === 'correct')
    .map((accepted) => {
      const final = lastBefore(rows, (row) => row.direction === 'sent'
        && row.client === 'control'
        && row.type === 'student.speech.final'
        && row.utterance === accepted.utterance, accepted.order)
      if (!final)
        throw new Error('correct Core acceptance has no matching Control utterance slot')
      return { accepted, final }
    })
}

function assertAttempt(rows, cycle, index, nextFinalOrder = Infinity) {
  const { accepted, final } = cycle
  const attempt = index + 1
  const sameCapture = (row) => row.capture === final.capture
    && row.assignment === final.assignment && row.response === final.response
  const captureStarted = lastBefore(rows, (row) => row.direction === 'sent'
    && row.client === 'control' && row.type === 'response.capture.started'
    && sameCapture(row), final.order)
  if (!captureStarted) throw new Error(`attempt ${attempt} has no correlated capture.started`)
  const captureReady = lastBefore(rows, (row) => row.direction === 'sent'
    && row.client === 'control' && row.type === 'response.capture.ready'
    && row.status === 'ready' && sameCapture(row), captureStarted.order)
  if (!captureReady) throw new Error(`attempt ${attempt} has no correlated ready capture`)
  const captureRequested = lastBefore(rows, (row) => row.direction === 'received'
    && row.client === 'control' && row.type === 'response.capture.requested'
    && sameCapture(row), captureReady.order)
  if (!captureRequested) throw new Error(`attempt ${attempt} has no correlated Core capture request`)
  const assignmentRefresh = lastBefore(rows, (row) => row.direction === 'received'
    && row.client === 'control' && row.type === 'class.turn.assigned'
    && row.assignment === final.assignment && row.response === final.response, captureRequested.order)
  if (!assignmentRefresh) throw new Error(`attempt ${attempt} has no Core assignment refresh after callout`)

  // Core deliberately re-emits the same assignment immediately after accepting
  // the exact callout ACK. The callout has no assignment field on the wire, so
  // bind it to that refresh and require the original same-slot assignment too.
  const calloutFinished = lastBefore(rows, (row) => row.direction === 'sent'
    && row.client === 'stage' && row.type === 'speech.playback.finished'
    && row.status === 'completed'
    && rows.some((started) => started.direction === 'received'
      && started.client === 'stage' && started.type === 'speech.turn.started'
      && started.source === 'callout' && started.speech === row.speech
      && started.order < row.order), assignmentRefresh.order)
  if (!calloutFinished) throw new Error(`attempt ${attempt} has no completed Stage callout`)
  const initialAssignment = lastBefore(rows, (row) => row.direction === 'received'
    && row.client === 'control' && row.type === 'class.turn.assigned'
    && row.assignment === final.assignment && row.response === final.response, calloutFinished.order)
  if (!initialAssignment) throw new Error(`attempt ${attempt} callout has no matching Core assignment`)

  const asr = firstBetween(rows, (row) => row.client === 'control'
    && row.direction === 'http' && row.type === 'http.audio.transcriptions'
    && row.status === 'ok', captureStarted.order, final.order)
  if (!asr) throw new Error(`attempt ${attempt} has no real ASR response after capture started`)
  if (accepted.order <= final.order)
    throw new Error(`attempt ${attempt} Core accepted before its correlated utterance`)

  const agent = firstBetween(rows, (row) => row.direction === 'received'
    && row.client === 'stage' && row.type === 'speech.turn.started'
    && row.source === 'agent', accepted.order, nextFinalOrder)
  if (!agent) throw new Error(`attempt ${attempt} has no hosted agent speech after correct acceptance`)
  const playbackStarted = firstBetween(rows, (row) => row.direction === 'sent'
    && row.client === 'stage' && row.type === 'speech.playback.started'
    && row.speech === agent.speech && row.causalAudioStart === true, agent.order, nextFinalOrder)
  if (!playbackStarted) throw new Error(`attempt ${attempt} agent speech has no causal WebAudio start evidence`)
  const piper = firstBetween(rows, (row) => row.client === 'stage'
    && row.direction === 'http' && row.type === 'http.audio.speech'
    && row.status === 'ok', agent.order, playbackStarted.order)
  if (!piper) throw new Error(`attempt ${attempt} has no real Piper response before causal audio start`)
  const playbackFinished = firstBetween(rows, (row) => row.direction === 'sent'
    && row.client === 'stage' && row.type === 'speech.playback.finished'
    && row.speech === agent.speech && row.status === 'completed', playbackStarted.order, nextFinalOrder)
  if (!playbackFinished) throw new Error(`attempt ${attempt} agent speech has no completed Stage playback acknowledgement`)
  if (typeof agent.stateVersion !== 'number')
    throw new Error(`attempt ${attempt} agent speech has no Core state version`)
  const committed = firstBetween(rows, (row) => row.direction === 'received'
    && ['scene.update', 'lesson.position', 'class.session.updated'].includes(row.type)
    && typeof row.stateVersion === 'number' && row.stateVersion > agent.stateVersion,
  playbackFinished.order, nextFinalOrder)
  if (!committed) throw new Error(`attempt ${attempt} Core did not publish a post-playback committed state transition`)
  return {
    attempt: `attempt-${attempt}`,
    assignment: final.assignment,
    response: final.response,
    capture: final.capture,
    utterance: final.utterance,
    calloutSpeech: calloutFinished.speech,
    agentSpeech: agent.speech,
    calloutCompletedOrder: calloutFinished.order,
    captureRequestedOrder: captureRequested.order,
    captureReadyOrder: captureReady.order,
    captureStartedOrder: captureStarted.order,
    asrOrder: asr.order,
    responseAcceptedOrder: accepted.order,
    piperOrder: piper.order,
    playbackStartedOrder: playbackStarted.order,
    playbackFinishedOrder: playbackFinished.order,
    commitOrder: committed.order,
  }
}

function assertExpectedAgentTurns(rows, attempts) {
  const cycles = correlatedCorrectCycles(rows)
  if (cycles.length !== attempts)
    throw new Error(`expected exactly ${attempts} correlated correct response cycles, observed ${cycles.length}`)
  const proofs = cycles.map((cycle, index) => assertAttempt(
    rows, cycle, index, cycles[index + 1]?.final.order ?? Infinity,
  ))
  const matchedAgentSpeech = new Set(proofs.map((proof) => proof.agentSpeech))
  const actualAgentSpeech = new Set(agentSpeechTurns(rows).map((row) => row.speech))
  if (actualAgentSpeech.size !== attempts || actualAgentSpeech.size !== matchedAgentSpeech.size
    || [...actualAgentSpeech].some((speech) => !matchedAgentSpeech.has(speech)))
    throw new Error(`expected exactly ${attempts} correlated agent speech turns`)
  return proofs
}

function assertRealVoicePath(rows) {
  const tts = rows.some((row) => row.client === 'stage'
    && row.type === 'http.audio.speech' && row.status === 'ok')
  const asr = rows.some((row) => row.client === 'control'
    && row.type === 'http.audio.transcriptions' && row.status === 'ok')
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
    artifactVersion: 2,
    ok: false,
    mode: cfg.mode,
    expectedAttempts: cfg.attempts,
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
      () => ledger.hasLesson(cfg.expectedLessonId),
      cfg.timeoutMs,
    )
    progress('lesson-identity')

    for (let attempt = 0; attempt < cfg.attempts; attempt += 1) {
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
      progress(`turn-${attempt + 1}-assigned`)
      // The same visible button a learner presses. Afterwards the browser's
      // real selected input (or only its configured file device) supplies the
      // audio. The harness neither makes nor injects a learner answer.
      await control.getByTestId('answer-station-ready').click()
      await waitFor(
        control,
        () => document.querySelector('[data-testid="answer-station-ready"]')?.getAttribute('data-voice-phase') === 'listening',
        cfg.timeoutMs,
      )
      progress(`turn-${attempt + 1}-capture-listening`)
      if (cfg.mode === 'manual-physical-mic')
        process.stderr.write(`Bright acceptance: speak expected answer ${attempt + 1} of ${cfg.attempts} into the physical microphone now.\n`)

      await waitFor(
        control,
        () => document.querySelector('[data-testid="answer-station-ready"]')?.getAttribute('data-voice-phase') === 'idle',
        cfg.timeoutMs,
      )
      await waitUntil(
        () => received(ledger.rows, 'control', 'student.response.accepted')
          .filter((row) => row.outcome === 'correct').length >= attempt + 1,
        cfg.timeoutMs,
      )
      if (cfg.requireAgentProposal) {
        await waitUntil(() => {
          try {
            const cycle = correlatedCorrectCycles(ledger.rows)[attempt]
            return cycle ? assertAttempt(ledger.rows, cycle, attempt) : null
          }
          catch { return null }
        }, cfg.timeoutMs)
      }
      progress(`turn-${attempt + 1}-committed`)
    }
    out.voicePath = assertRealVoicePath(ledger.rows)
    if (cfg.requireAgentProposal) {
      out.attempts = assertExpectedAgentTurns(ledger.rows, cfg.attempts)
      // Preserve the one-turn result contract used by existing operators.
      if (cfg.attempts === 1) out.commit = out.attempts[0]
    }

    out.events = ledger.rows
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
