/**
 * Resolving an expression reference to the index pixi-live2d-display wants.
 *
 * THE TRAP THIS SOLVES. In `haru_greeter_t03.model3.json` the expression entries are:
 *
 *   { "Name": "f00", "File": "expressions/F01.exp3.json" }
 *   { "Name": "f01", "File": "expressions/F02.exp3.json" }
 *   ...
 *
 * The `Name` and the file basename are DIFFERENT, and off by one. A human authoring
 * `bright-model.json` reads the file listing and writes `"F05"`; the model's own name
 * for that entry is `f04`. Matching on `Name` alone silently maps every emotion to
 * the neighbouring expression — a bug that looks like "the emotions are a bit wrong"
 * rather than like a failure.
 *
 * Worse, on this model the two key spaces OVERLAP: `"F05"` lowercased is `"f05"`,
 * which is the `Name` of a DIFFERENT entry (the one whose file is `F06`). So a
 * case-insensitive `Name`-first lookup silently returns the neighbour — every
 * emotion one off, and still "working". A real integration test against this model
 * caught it (see `real-model.test.ts`).
 *
 * The precedence that resolves it, in order:
 *   1. exact, case-sensitive `Name`
 *   2. exact, case-sensitive `File` basename
 *   3. case-insensitive `File` basename
 *   4. case-insensitive `Name`
 *   5. a numeric index (handled first, since a number is unambiguous)
 *
 * Exact matches come first because they cannot be accidents. Among fuzzy matches the
 * file basename wins, because that is what a human authoring `bright-model.json`
 * reads — they list the directory, not the model3.json `Name` fields.
 *
 * If you write a genuinely ambiguous reference (e.g. `"f05"`, which is both a `Name`
 * and, case-insensitively, a file basename) the exact `Name` match wins. Use the
 * numeric index if you need to be certain.
 */

export interface ExpressionEntry {
  /** Position in the model3.json `Expressions` array. What the runtime indexes by. */
  index: number
  /** The `Name` field, as written. */
  name: string
  /** File basename with the `.exp3.json` suffix removed, as written. */
  file: string
}

export type ExpressionIndex = ExpressionEntry[]

/** Reference to an expression: its `Name`, its file basename, or its index. */
export type ExpressionRef = string | number

function basename(path: string): string {
  const last = path.split(/[\\/]/).pop() ?? path
  return last.replace(/\.exp3\.json$/i, '')
}

/**
 * Builds the lookup table from a model3.json `FileReferences.Expressions` array.
 *
 * Accepts the loose shape the runtime hands back — entries missing `Name` or `File`
 * are kept with an empty string rather than dropped, so indices stay aligned with
 * the model's own array.
 */
export function buildExpressionIndex(
  definitions: ReadonlyArray<{ Name?: unknown, File?: unknown }> | undefined | null,
): ExpressionIndex {
  if (!Array.isArray(definitions))
    return []

  return definitions.map((definition, index) => ({
    index,
    name: typeof definition?.Name === 'string' ? definition.Name : '',
    file: typeof definition?.File === 'string' ? basename(definition.File) : '',
  }))
}

/**
 * Resolves a reference to a concrete entry, or `undefined` if the model has no such
 * expression.
 *
 * @example
 * const index = buildExpressionIndex([{ Name: 'f00', File: 'expressions/F01.exp3.json' }])
 * resolveExpressionRef(index, 'F01')  // => { index: 0, name: 'f00', file: 'F01', id: 'F01' } — exact file match
 * resolveExpressionRef(index, 'f00')  // => same entry, matched on Name
 * resolveExpressionRef(index, 0)      // => same entry, matched on index
 * resolveExpressionRef(index, 'F09')  // => undefined
 */
export function resolveExpressionRef(
  index: ExpressionIndex,
  ref: ExpressionRef,
): { index: number, name: string, file: string, id: string } | undefined {
  if (typeof ref === 'number') {
    const entry = index[ref]
    return entry ? { ...entry, id: entry.name || entry.file || String(ref) } : undefined
  }

  const exact = ref.trim()
  if (!exact)
    return undefined
  const needle = exact.toLowerCase()

  const match
    = index.find(entry => entry.name === exact)
      ?? index.find(entry => entry.file === exact)
      ?? index.find(entry => entry.file.toLowerCase() === needle)
      ?? index.find(entry => entry.name.toLowerCase() === needle)

  return match ? { ...match, id: exact } : undefined
}
