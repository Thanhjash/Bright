import { BrowserRouter, Route, Routes } from 'react-router'
import { ClassroomRoute } from './routes/classroom/ClassroomRoute'
import { ControlRoute } from './routes/control/ControlRoute'
import { LobbyRoute } from './routes/lobby/LobbyRoute'
import { NotFound } from './routes/NotFound'

/**
 * Three routes, one app (docs/design/runtime-topology.md §1).
 *
 * In the classroom `/classroom` and `/control` are two windows on an extended
 * display: the projector shows the room, the laptop shows the console. Each
 * opens its own WebSocket to classroom-core with its own role.
 *
 * `/` is the front door, and it opens no socket at all. It was a bare redirect
 * to `/classroom` until 2026-08-21, which is why the room had no beginning.
 * Deleting this one line restores exactly that behaviour, which is the rollback
 * if the door ever misbehaves.
 */
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LobbyRoute />} />
        <Route path="/classroom" element={<ClassroomRoute />} />
        <Route path="/control" element={<ControlRoute />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}
