/**
 * Narrowing helpers over the contract types.
 *
 * `SceneProps` in @contracts is a bare union — the discriminant (`kind`) lives
 * on `Scene`, not inside `props`, and `IdleProps = {}` is structurally
 * assignable from everything. So TypeScript cannot narrow `scene.props` on its
 * own. This module maps kind → prop type once, in one place, so every board
 * component receives a precisely typed `props` and nothing else casts.
 *
 * This composes the contract types. It does not redefine them.
 */
import type {
  ChoiceProps,
  ExploreProps,
  IdleProps,
  ImageProps,
  MatchingProps,
  PronunciationProps,
  RoleplayProps,
  Scene,
  SceneKind,
  SentenceBuilderProps,
  TextProps,
  VideoProps,
  VocabularyProps,
} from '@contracts'

export interface ScenePropsByKind {
  idle: IdleProps
  text: TextProps
  image: ImageProps
  video: VideoProps
  vocabulary: VocabularyProps
  choice: ChoiceProps
  matching: MatchingProps
  sentence_builder: SentenceBuilderProps
  pronunciation: PronunciationProps
  roleplay: RoleplayProps
  explore: ExploreProps
}

/** Every kind the protocol defines. Exhaustiveness is enforced by the
 *  `satisfies` clause: adding a kind to the contract breaks the build here
 *  rather than silently rendering an error card in front of a class. */
export const SCENE_KINDS = [
  'idle',
  'text',
  'image',
  'video',
  'vocabulary',
  'choice',
  'matching',
  'sentence_builder',
  'pronunciation',
  'roleplay',
  'explore',
] as const satisfies readonly SceneKind[]

const KNOWN = new Set<string>(SCENE_KINDS)

export function isSceneKind(kind: string): kind is SceneKind {
  return KNOWN.has(kind)
}

/**
 * Read `scene.props` at the type implied by `kind`. The caller has already
 * switched on `scene.kind`, so this is the one sanctioned cast in the app.
 */
export function propsFor<K extends keyof ScenePropsByKind>(
  scene: Scene,
  _kind: K,
): ScenePropsByKind[K] {
  return scene.props as ScenePropsByKind[K]
}

/** Human label for a kind — used by /control and the "coming soon" boards. */
export const SCENE_LABEL: Record<SceneKind, string> = {
  idle: 'Idle',
  text: 'Text',
  image: 'Image',
  video: 'Video',
  vocabulary: 'Vocabulary',
  choice: 'Choice',
  matching: 'Matching',
  sentence_builder: 'Sentence builder',
  pronunciation: 'Pronunciation',
  roleplay: 'Roleplay',
  explore: 'Explore',
}
