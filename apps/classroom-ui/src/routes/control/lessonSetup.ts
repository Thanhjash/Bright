import type { LessonStartPayload } from '@contracts'

export type Roster = NonNullable<LessonStartPayload['roster']>

export interface LessonSetup {
  lessonId: string
  classId: string
  roster: Roster
  attendanceIds: string[]
}

export interface ParsedRoster {
  roster: Roster
  error?: string
}

/** CSV/TSV: learner-id, pseudonym, optional seat. One pseudonym alone is OK. */
export function parseRoster(raw: string): ParsedRoster {
  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length < 1) return { roster: [], error: 'Add at least one learner.' }
  if (lines.length > 40) return { roster: [], error: 'This release supports at most 40 learners.' }

  const roster: Roster = []
  const ids = new Set<string>()
  for (const [index, line] of lines.entries()) {
    const fields = line.split(line.includes('\t') ? '\t' : ',').map((field) => field.trim())
    const onlyName = fields.length === 1
    const id = cleanId(onlyName ? `learner-${String(index + 1).padStart(2, '0')}` : fields[0])
    const displayName = (onlyName ? fields[0] : fields[1])?.slice(0, 40)
    const seat = (onlyName ? undefined : fields[2])?.slice(0, 20) || undefined
    if (!id || !displayName)
      return { roster: [], error: `Line ${index + 1}: use learner-id, pseudonym, optional seat.` }
    if (ids.has(id)) return { roster: [], error: `Line ${index + 1}: duplicate learner id “${id}”.` }
    ids.add(id)
    roster.push({ id, displayName, ...(seat ? { seat } : {}) })
  }
  return { roster }
}

export function rosterText(roster: Roster): string {
  return roster.map(({ id, displayName, seat }) => [id, displayName, seat].filter(Boolean).join(', ')).join('\n')
}

export function mockRoster(): Roster {
  return Array.from({ length: 20 }, (_, index) => ({
    id: `learner-${String(index + 1).padStart(2, '0')}`,
    displayName: `Learner ${String(index + 1).padStart(2, '0')}`,
    seat: `${String.fromCharCode(65 + Math.floor(index / 5))}${index % 5 + 1}`,
  }))
}

function cleanId(value: string | undefined): string {
  return (value ?? '')
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
}
