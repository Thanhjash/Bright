/**
 * scene.kind → component.
 *
 * Three guarantees, all of them because this is projected in front of
 * thirty children:
 *   · an unknown `kind` renders a visible error card, never a blank screen
 *   · an unknown `v` is rejected loudly rather than guessed at
 *   · a component that throws is caught here, not by a white page
 */
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { PROTOCOL_VERSION } from '@contracts'
import type { Scene } from '@contracts'
import { propsFor } from '../lib/scene'
import { ChoiceBoard } from './BoardLayer/ChoiceBoard'
import { ErrorCard } from './BoardLayer/ErrorCard'
import { ExploreBoard } from './BoardLayer/ExploreBoard'
import { IdleBoard } from './BoardLayer/IdleBoard'
import { ImageBoard } from './BoardLayer/ImageBoard'
import { MatchingBoard } from './BoardLayer/MatchingBoard'
import { PronunciationBoard } from './BoardLayer/PronunciationBoard'
import { RoleplayBoard } from './BoardLayer/RoleplayBoard'
import { SentenceBuilderBoard } from './BoardLayer/SentenceBuilderBoard'
import { TextBoard } from './BoardLayer/TextBoard'
import { VocabularyBoard } from './BoardLayer/VocabularyBoard'
import { VideoBoard } from './BoardLayer/stubs'

export function SceneRouter({ scene }: { scene: Scene | null }) {
  if (!scene) return <IdleBoard />

  if (scene.v !== PROTOCOL_VERSION) {
    return (
      <ErrorCard
        title="Scene version not understood"
        detail={`This board speaks protocol v${PROTOCOL_VERSION}; classroom-core sent v${String(scene.v)}. Nothing is rendered rather than something wrong.`}
        raw={scene}
      />
    )
  }

  return (
    <BoardErrorBoundary resetKey={`${scene.kind}:${scene.stateVersion}`} scene={scene}>
      <div key={scene.kind} className="animate-scene-in h-full w-full">
        {renderScene(scene)}
      </div>
    </BoardErrorBoundary>
  )
}

function renderScene(scene: Scene): ReactNode {
  switch (scene.kind) {
    case 'idle':
      return <IdleBoard />
    case 'text':
      return <TextBoard props={propsFor(scene, 'text')} />
    case 'image':
      return <ImageBoard props={propsFor(scene, 'image')} />
    case 'vocabulary':
      return <VocabularyBoard props={propsFor(scene, 'vocabulary')} />
    case 'choice':
      return <ChoiceBoard props={propsFor(scene, 'choice')} />
    case 'matching':
      return <MatchingBoard props={propsFor(scene, 'matching')} />
    case 'sentence_builder':
      return <SentenceBuilderBoard props={propsFor(scene, 'sentence_builder')} />
    case 'pronunciation':
      return <PronunciationBoard props={propsFor(scene, 'pronunciation')} />
    case 'roleplay':
      return <RoleplayBoard props={propsFor(scene, 'roleplay')} />
    case 'explore':
      return <ExploreBoard props={propsFor(scene, 'explore')} />

    // Still a readable placeholder — see BoardLayer/stubs.tsx
    case 'video':
      return <VideoBoard props={propsFor(scene, 'video')} />

    default:
      return (
        <ErrorCard
          title="Unknown scene"
          detail={`classroom-core asked for "${String((scene as Scene).kind)}", which this board does not know how to draw.`}
          raw={scene}
        />
      )
  }
}

interface BoundaryProps {
  resetKey: string
  scene: Scene
  children: ReactNode
}

class BoardErrorBoundary extends Component<BoundaryProps, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidUpdate(prev: BoundaryProps) {
    // A new scene is a fresh chance to render something.
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[stage] board render failed', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorCard
          title="This activity could not be shown"
          detail={`The "${this.props.scene.kind}" board failed while rendering. The lesson can continue — skip or repeat from the console.`}
          raw={{ error: this.state.error.message, scene: this.props.scene }}
        />
      )
    }
    return this.props.children
  }
}
