/**
 * Mock lesson — the fixture sequence behind `VITE_MOCK=1`.
 *
 * Purpose: let the whole UI be developed and demoed with no backend at all,
 * and exercise every scene kind the Stage can render, including the stubs.
 * It is throwaway content (docs/archive/phase-1-plan.md §10, P3) — the shape is what matters.
 *
 * These are `Scene`s exactly as classroom-core would send them, so anything
 * that renders here renders identically against the real bus.
 */
import type { LessonPosition, Scene, SceneKind, SceneProps } from '@contracts'
import { PROTOCOL_VERSION } from '@contracts'

export interface MockStep {
  id: string
  /** lesson stage label — HOOK / INPUT / PRACTICE / … */
  stage: string
  kind: SceneKind
  props: SceneProps
  overlay?: Scene['overlay']
  /** what the teacher says when this step opens; may carry inline ACT tokens */
  say?: string
  /** auto-advance after this long. Omit ⇒ waits for an interaction. */
  holdMs?: number
  /** id the mock grades interactions against, when this step waits for one */
  correct?: string
}

export const MOCK_LESSON: Omit<
  LessonPosition,
  'activityIndex' | 'activityCount' | 'stage' | 'activityId' | 'activityGeneration'
> = {
  lessonId: 'demo-market-01',
  classId: '7A',
  decisionRevision: 0,
  currentStudentId: 'minh',
}

export const MOCK_STUDENT_NAME = 'Minh'

export const MOCK_STEPS: MockStep[] = [
  {
    id: 'ready',
    stage: 'READY',
    kind: 'idle',
    props: {},
    holdMs: 2600,
  },
  {
    id: 'greet',
    stage: 'HOOK',
    kind: 'text',
    props: { text: 'Good morning!', size: 'xl' },
    say: '<|ACT {"emotion":"happy","motion":"nod"}|> Good morning, everyone! I am so happy to see you today.',
    holdMs: 4200,
  },
  {
    id: 'market-photo',
    stage: 'HOOK',
    kind: 'image',
    props: { asset: 'asset://market-stall.webp', caption: 'The morning market' },
    say: 'This is a market. Today we are going shopping!',
    holdMs: 4600,
  },
  {
    id: 'vocab-show',
    stage: 'INPUT',
    kind: 'vocabulary',
    props: {
      items: [
        { id: 'apple', text: 'apple', asset: 'asset://apple.webp' },
        { id: 'banana', text: 'banana', asset: 'asset://banana.webp' },
        { id: 'mango', text: 'mango', asset: 'asset://mango.webp' },
        { id: 'bread', text: 'bread', asset: 'asset://bread.webp' },
      ],
      interaction: 'none',
    },
    say: 'Here are four things you can buy. Apple. Banana. Mango. Bread.',
    holdMs: 5200,
  },
  {
    id: 'vocab-point',
    stage: 'PRACTICE',
    kind: 'vocabulary',
    props: {
      items: [
        { id: 'apple', text: 'apple', asset: 'asset://apple.webp' },
        { id: 'banana', text: 'banana', asset: 'asset://banana.webp' },
        { id: 'mango', text: 'mango', asset: 'asset://mango.webp' },
        { id: 'bread', text: 'bread', asset: 'asset://bread.webp' },
      ],
      interaction: 'point',
    },
    overlay: { studentName: MOCK_STUDENT_NAME, listening: true },
    say: '<|ACT {"emotion":"question"}|> Minh, can you point to the apple?',
    correct: 'apple',
    // no holdMs — waits for interaction.point
  },
  {
    id: 'choice-banana',
    stage: 'PRACTICE',
    kind: 'choice',
    props: {
      prompt: 'Which one is a banana?',
      options: [
        { id: 'o-mango', text: 'mango', asset: 'asset://mango.webp' },
        { id: 'o-banana', text: 'banana', asset: 'asset://banana.webp' },
        { id: 'o-bread', text: 'bread', asset: 'asset://bread.webp' },
      ],
    },
    overlay: { studentName: MOCK_STUDENT_NAME },
    say: 'Now — which one is a banana?',
    correct: 'o-banana',
    // no holdMs — waits for interaction.choice
  },
  {
    id: 'target-sentence',
    stage: 'PRACTICE',
    kind: 'text',
    props: { text: 'I would like an apple, please.', size: 'lg' },
    say: 'Say it with me. I would like an apple, please.',
    holdMs: 4800,
  },
  {
    id: 'builder',
    stage: 'PRACTICE',
    kind: 'sentence_builder',
    props: {
      tokens: [
        { id: 't1', text: 'I' },
        { id: 't2', text: 'would' },
        { id: 't3', text: 'like' },
        { id: 't4', text: 'an' },
        { id: 't5', text: 'apple' },
      ],
      placed: ['t1', 't2'],
      target: 'I would like an apple',
    },
    say: 'Put the words in order.',
    holdMs: 4200,
  },
  {
    id: 'matching',
    stage: 'PRACTICE',
    kind: 'matching',
    props: {
      left: [
        { id: 'l-apple', text: 'apple' },
        { id: 'l-banana', text: 'banana' },
        { id: 'l-bread', text: 'bread' },
      ],
      right: [
        { id: 'r-banana', asset: 'asset://banana.webp' },
        { id: 'r-bread', asset: 'asset://bread.webp' },
        { id: 'r-apple', asset: 'asset://apple.webp' },
      ],
      solved: [['l-apple', 'r-apple']],
    },
    say: 'Match the word to the picture.',
    holdMs: 4200,
  },
  {
    id: 'pronunciation',
    stage: 'PRACTICE',
    kind: 'pronunciation',
    props: {
      word: 'banana',
      phonemes: [
        { symbol: 'b', status: 'good' },
        { symbol: 'ə', status: 'good' },
        { symbol: 'n', status: 'retry' },
        { symbol: 'ɑː', status: 'pending' },
        { symbol: 'n', status: 'pending' },
        { symbol: 'ə', status: 'pending' },
      ],
    },
    overlay: { listening: true },
    say: 'Try the word again. Ba-na-na.',
    holdMs: 4600,
  },
  {
    id: 'roleplay',
    stage: 'PRODUCTION',
    kind: 'roleplay',
    props: {
      environment: 'market',
      aiRole: 'shopkeeper',
      studentRole: 'customer',
      targetPhrases: ['I would like...', 'How much is this?', 'Thank you!'],
    },
    overlay: { studentName: MOCK_STUDENT_NAME, listening: true },
    say: '<|ACT {"emotion":"curious"}|> I am the shopkeeper. Hello! What would you like?',
    holdMs: 5200,
  },
  {
    id: 'video',
    stage: 'INPUT',
    kind: 'video',
    props: { asset: 'asset://market-clip.mp4', caption: 'At the market', autoplay: true },
    say: 'Watch this short clip.',
    holdMs: 4200,
  },
  {
    id: 'explore',
    stage: 'EXPLORE',
    kind: 'explore',
    props: {
      topic: 'Food around the world',
      nodes: [
        { id: 'n-fruit', label: 'Fruit', asset: 'asset://fruit.webp' },
        { id: 'n-bread', label: 'Bread', asset: 'asset://bread.webp' },
        { id: 'n-rice', label: 'Rice', asset: 'asset://rice.webp' },
        { id: 'n-market', label: 'Markets', asset: 'asset://market-stall.webp' },
      ],
      focusId: 'n-fruit',
    },
    say: 'What else would you like to know about?',
    holdMs: 4600,
  },
  {
    id: 'goodbye',
    stage: 'CLOSE',
    kind: 'text',
    props: { text: 'See you next time!', size: 'xl' },
    say: '<|ACT {"emotion":"happy"}|> Great work today. See you next time!',
    holdMs: 5000,
  },
]

export function sceneFrom(step: MockStep, stateVersion: number, overlay?: Scene['overlay']): Scene {
  const merged = { ...step.overlay, ...overlay }
  return {
    v: PROTOCOL_VERSION,
    stateVersion,
    kind: step.kind,
    props: step.props,
    ...(Object.keys(merged).length ? { overlay: merged } : {}),
  }
}
