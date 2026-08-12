import { Link } from 'react-router'

export function NotFound() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-8 bg-ink-900 p-8 text-center">
      <h1 className="font-display text-4xl font-extrabold text-cream">There are two screens</h1>
      <div className="flex flex-wrap justify-center gap-4">
        <Link
          to="/classroom"
          className="rounded-2xl bg-amber px-8 py-5 font-display text-xl font-extrabold text-ink-900"
        >
          Classroom stage
        </Link>
        <Link
          to="/control"
          className="rounded-2xl bg-ink-700 px-8 py-5 font-display text-xl font-extrabold text-cream ring-2 ring-ink-500"
        >
          Facilitator console
        </Link>
      </div>
    </div>
  )
}
