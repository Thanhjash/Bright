import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { unlockAudioOnFirstGesture } from './speech/speakingDriver'
import { useClassroom } from './store/classroom'
import './index.css'

// Browsers block an AudioContext until the page has been interacted with, so
// the first spoken line would be silent. One click or key anywhere unlocks it.
// The kiosk has no gesture to wait for and passes
// --autoplay-policy=no-user-gesture-required instead.
unlockAudioOnFirstGesture()

// Dev-only inspection handle. The projector has no devtools and a kiosk has no
// console, so being able to read live state from an automated browser (or from
// a support session) is worth the four lines.
if (import.meta.env.DEV)
  (window as unknown as Record<string, unknown>).__bright = useClassroom

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing from index.html')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
