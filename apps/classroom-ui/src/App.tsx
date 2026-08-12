import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { ClassroomRoute } from './routes/classroom/ClassroomRoute'
import { ControlRoute } from './routes/control/ControlRoute'
import { NotFound } from './routes/NotFound'

/**
 * Two routes, one app (docs/3-design/runtime-topology.md §1).
 *
 * In the classroom these are two windows on an extended display: the projector
 * shows `/classroom`, the laptop shows `/control`. Each window opens its own
 * WebSocket to classroom-core with its own role.
 */
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/classroom" replace />} />
        <Route path="/classroom" element={<ClassroomRoute />} />
        <Route path="/control" element={<ControlRoute />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}
