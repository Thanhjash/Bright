/**
 * The one place where bus events become store state.
 *
 * Keeping this in a single file is what makes "the store is a pure reflection
 * of server events" checkable: if a mutator is called anywhere else, that is
 * the bug.
 */
import {
  cancelSpeech,
  configureSpeechOutput,
  endSpeech,
  failSpeech,
  pushSpeech,
  speak,
  startSpeech,
  stop as stopSpeaking,
} from '../speech/speakingDriver'
import {
  observeOutputActivity,
  publishOutputActivity,
  resetOutputActivity,
} from '../speech/outputActivity'
import { useClassroom } from '../store/classroom'
import type { Bus, Unsubscribe } from './types'

export function connectBusToStore(bus: Bus): Unsubscribe {
  const store = useClassroom.getState
  const textByTurn = new Map<string, string>()
  let audioOwner = false
  let releaseSpeechOutput: () => void = () => {}
  let leaseTimer = 0

  const ownsAudio = () => bus.role === 'stage' && audioOwner

  const disableAudio = (reason: string, reportToCore: boolean) => {
    if (!audioOwner) return
    window.clearTimeout(leaseTimer)
    leaseTimer = 0
    stopSpeaking(reason, reportToCore)
    releaseSpeechOutput()
    releaseSpeechOutput = () => {}
    audioOwner = false
  }

  const enableAudio = (expiresAt: number) => {
    if (!audioOwner) {
      audioOwner = true
      releaseSpeechOutput = configureSpeechOutput({
        onPlaybackStarted: (speechTurnId, metrics) => {
          publishOutputActivity('playback-started', speechTurnId)
          store().startSpeech(speechTurnId)
          store().updateSpeechText(speechTurnId, textByTurn.get(speechTurnId) ?? '')
          bus.send('speech.playback.started', { speechTurnId })
          void metrics
        },
        onPlaybackFinished: (speechTurnId, status, reason, reportToCore = true, metrics) => {
          publishOutputActivity('finished', speechTurnId, status)
          if (reportToCore) {
            bus.send('speech.playback.finished', {
              speechTurnId,
              status,
              ...(reason ? { reason } : {}),
              ...(metrics ? { metrics } : {}),
            })
          }
          store().cancelSpeech(speechTurnId)
          textByTurn.delete(speechTurnId)
        },
      })
    }
    window.clearTimeout(leaseTimer)
    leaseTimer = window.setTimeout(
      () => disableAudio('stage-audio-lease-expired', true),
      Math.max(0, expiresAt - Date.now()),
    )
  }

  const offs: Unsubscribe[] = [
    bus.onStatus((status) => store().setConnection(status)),

    bus.onReset((reason) => {
      resetOutputActivity()
      if (ownsAudio()) {
        // A reconnect reset fires before WsBus sends client.hello. Never let
        // cancellation callbacks put an ACK ahead of that mandatory first frame.
        disableAudio('transport-reset', false)
      }
      store().discardLocalState(reason)
    }),

    bus.onAny((event) => store().noteEvent(event)),

    bus.on('scene.snapshot', (payload) => {
      store().applySnapshot(payload)
      if (bus.role === 'control' && payload.speech?.status !== 'terminal' && payload.speech?.speechTurnId)
        observeOutputActivity('started', payload.speech.speechTurnId)
    }),
    bus.on('scene.update', (scene) => store().applyScene(scene)),
    bus.on('class.session.updated', (session) => store().applySession(session)),
    bus.on('class.turn.assigned', (assignment) => store().applyAssignment(assignment)),
    bus.on('class.turn.closed', (closed) => store().closeTurn(closed)),
    bus.on('response.capture.requested', (capture) => store().applyCapture(capture)),
    bus.on('classroom.status', (status) => store().applyStatus(status)),
    bus.on('stage.lease.granted', (lease) => {
      store().applyStageLease(lease)
      if (bus.role !== 'stage') return
      if (lease.clientInstanceId !== bus.clientInstanceId) {
        disableAudio('stage-audio-lease-moved', true)
        return
      }
      enableAudio(lease.expiresAt)
    }),
    bus.on('lesson.position', (lesson) => store().applyLesson(lesson)),
    bus.on('lesson.started', ({ lessonId, index }) => {
      store().log('system', `lesson started: ${lessonId} at activity ${index + 1}`)
    }),
    bus.on('mode.changed', (payload) => store().applyMode(payload)),
    bus.on('avatar.act', (act) => store().applyAct(act)),

    bus.on('speech.say', (payload) => {
      store().applySpeech(payload)
      // Full text, tokens intact: the speech pipeline's ACT parser needs them
      // to fire emotions in step with the audio, and strips them before TTS.
      if (ownsAudio()) speak(payload.text, payload.turnId)
    }),

    bus.on('speech.turn.started', (payload) => {
      textByTurn.set(payload.speechTurnId, '')
      // Control tracks the intent immediately, while only Stage owns physical
      // playback. The matching `finished` signal still comes from Stage.
      if (ownsAudio()) publishOutputActivity('started', payload.speechTurnId)
      else observeOutputActivity('started', payload.speechTurnId)
      if (!ownsAudio())
        store().startSpeech(payload.speechTurnId)
      if (ownsAudio()) {
        startSpeech({
          speechTurnId: payload.speechTurnId,
          conversationTurnId: payload.conversationTurnId,
          behavior: payload.behavior,
          audioAsset: payload.audioAsset,
        })
      }
    }),

    bus.on('speech.text.delta', ({ speechTurnId, delta }) => {
      const text = `${textByTurn.get(speechTurnId) ?? ''}${delta}`
      textByTurn.set(speechTurnId, text)
      if (store().currentTurnId === speechTurnId)
        store().updateSpeechText(speechTurnId, text)
      if (ownsAudio())
        void pushSpeech(speechTurnId, delta)
    }),

    bus.on('speech.turn.ended', ({ speechTurnId, status, reason }) => {
      const text = textByTurn.get(speechTurnId) ?? ''
      store().finishSpeechText(speechTurnId, text)
      if (!ownsAudio()) {
        textByTurn.delete(speechTurnId)
        return
      }
      if (status === 'completed')
        void endSpeech(speechTurnId)
      else if (status === 'error')
        failSpeech(speechTurnId, reason ?? status)
      else
        cancelSpeech(speechTurnId, reason ?? status)
    }),

    bus.on('speech.cancel', ({ speechTurnId, reason }) => {
      if (ownsAudio()) cancelSpeech(speechTurnId, reason ?? 'server-cancel')
      else textByTurn.delete(speechTurnId)
      store().cancelSpeech(speechTurnId)
    }),

    bus.on('error', ({ code, message }) => {
      console.error(`[core] ${code}: ${message}`)
      store().log('system', `core error — ${code}: ${message}`)
    }),
  ]

  return () => {
    for (const off of offs) off()
    window.clearTimeout(leaseTimer)
    disableAudio('speech-output-unmounted', false)
  }
}
