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
  hasSpeechTurn,
  startSpeech,
  stop as stopSpeaking,
  unlockAudioOnFirstGesture,
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

  const heardPlayback = new Set<string>()

  // NOTE. There used to be a `PendingSpeech` hold-and-replay queue here, with a
  // `flushPending()` called from `enableAudio`. It could never hold anything:
  // `pending` was initialised to null and nothing ever assigned to it. So the
  // file read as though the "speech arrived before the lease" race was handled,
  // and it was not -- which is exactly how the teacher's opening greeting came
  // to be dropped on 2026-08-21 with no error anywhere.
  //
  // Deleted rather than completed. The race is now closed at the three points
  // where it actually occurs -- `speech.say`, `speech.turn.started` and
  // `speech.text.delta` each take the lease if this Stage does not hold it,
  // because there is only ever one projector. A dead safety net is worse than
  // no safety net: it stops the next person looking.

  const enableAudio = (expiresAt: number) => {
    if (!audioOwner) {
      audioOwner = true
      releaseSpeechOutput = configureSpeechOutput({
        onPlaybackStarted: (speechTurnId, metrics) => {
          heardPlayback.add(speechTurnId)
          publishOutputActivity('playback-started', speechTurnId)
          store().startSpeech(speechTurnId)
          store().updateSpeechText(speechTurnId, textByTurn.get(speechTurnId) ?? '')
          bus.send('speech.playback.started', {
            speechTurnId,
            ...(metrics ? { metrics } : {}),
          })
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
      unlockAudioOnFirstGesture()
    }),
    bus.on('lesson.position', (lesson) => store().applyLesson(lesson)),
    bus.on('lesson.started', ({ lessonId, index }) => {
      store().log('system', `lesson started: ${lessonId} at activity ${index + 1}`)
    }),
    bus.on('mode.changed', (payload) => store().applyMode(payload)),
    bus.on('avatar.act', (act) => store().applyAct(act)),

    bus.on('speech.say', (payload) => {
      store().applySpeech(payload)
      // One projector Stage: play the teacher even if the audio lease has not
      // been granted to this client YET.
      //
      // The same rescue already guarded `speech.turn.started` below, and its
      // absence here cost the room its opening line. Measured 2026-08-21: she
      // opened the class correctly -- read the unit map, read open-a-period,
      // put the picture up, called `say`, census ok=True -- and the speech log
      // shows NOT ONE synthesis request in the five minutes that followed. The
      // greeting reached `applySpeech`, so the subtitle and the board appeared;
      // `ownsAudio()` was still false because the lease grant had not landed,
      // so the line was dropped on the floor without a word anywhere. The room
      // looked like it had started a lesson and then refused to speak, and the
      // owner only heard her after HE spoke first and the lease caught up.
      //
      // A Stage that is not the audio owner is either a race like this one or a
      // second Stage, and there is only ever one projector.
      if (bus.role === 'stage' && !audioOwner)
        enableAudio(Date.now() + 60_000)
      // Full text, tokens intact: the speech pipeline's ACT parser needs them
      // to fire emotions in step with the audio, and strips them before TTS.
      if (ownsAudio()) speak(payload.text, payload.turnId)
    }),

    bus.on('speech.turn.started', (payload) => {
      textByTurn.set(payload.speechTurnId, '')
      // Which child sentence this answers. Recorded here rather than inside
      // `startSpeech`, because on the projector the store is driven by the
      // player's playback callbacks, which never see this payload -- so the one
      // screen that matters would have been the one screen that missed it.
      store().noteAnswering(payload.conversationTurnId ?? null)
      // One projector Stage: play the teacher even if the 15s lease timer
      // dropped client-side while Hermes was still thinking.
      if (bus.role === 'stage' && !audioOwner)
        enableAudio(Date.now() + 60_000)
      if (ownsAudio()) publishOutputActivity('started', payload.speechTurnId)
      else observeOutputActivity('started', payload.speechTurnId)
      if (!ownsAudio())
        store().startSpeech(payload.speechTurnId)
      if (bus.role === 'stage') {
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
      // The third door onto the same silent failure. `speech.say` and
      // `speech.turn.started` both take the lease when this Stage does not hold
      // it; the delta path did not, so a streamed line typed itself across the
      // subtitle while nothing was ever synthesised -- harder to spot than a
      // dropped greeting, because the text is animating.
      if (bus.role === 'stage' && !audioOwner)
        enableAudio(Date.now() + 60_000)
      if (bus.role === 'stage')
        void pushSpeech(speechTurnId, delta)
    }),

    bus.on('speech.turn.ended', ({ speechTurnId, status, reason }) => {
      const text = textByTurn.get(speechTurnId) ?? ''
      store().finishSpeechText(speechTurnId, text)
      if (bus.role !== 'stage') {
        textByTurn.delete(speechTurnId)
        return
      }
      if (status === 'completed') {
        if (!hasSpeechTurn(speechTurnId) && text)
          speak(text, speechTurnId)
        else
          void endSpeech(speechTurnId)
      }
      else if (status === 'error')
        failSpeech(speechTurnId, reason ?? status)
      else
        cancelSpeech(speechTurnId, reason ?? status)
    }),

    bus.on('speech.playback.observed', ({ speechTurnId }) => {
      // Core relays this only after accepting the active Stage lease owner's
      // terminal ACK. BroadcastChannel cannot cross browser profiles/devices,
      // so Control needs this authoritative observation to end half-duplex
      // suppression. Stage already owns the local physical callback.
      if (!ownsAudio()) observeOutputActivity('finished', speechTurnId)
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
