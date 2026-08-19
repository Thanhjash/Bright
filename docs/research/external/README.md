# external/ — commissioned deep research

Answers we asked for from outside. **Evidence, not doctrine** — a finding here
becomes binding only when a `decisions/` file adopts it.

| Document | Adopted in |
|---|---|
| Offline bilingual classroom speech IO | ASR adopted (`faster-whisper small` multilingual, running). TTS **not** adopted — see below |
| Code-switching inside one sentence | corrects the brief above; nothing adopted yet |
| Practice, Assessment, and Evidence for an Autonomous Whole-Class Teacher | [evidence-and-practice](../../decisions/2026-08-18-evidence-and-practice.md) |

## VieNeu-TTS is a candidate, not a solution

The first survey called it "recommended". The follow-up downgraded it to
**"must pass Bright acceptance testing"**, and that is the status to quote.
Its engineering fit is excellent and its licence is unusually clean, but the
exact thing Bright needs — that an intra-sentence VI↔EN switch keeps the same
perceived speaker, accent and prosody — has not been independently
demonstrated. Do not write "adopted" anywhere until it has.


## Lost: *Storage, Memory, and Retrieval for Bright*

Commissioned 2026-08-17, ~57 KB. On 2026-08-18 a newly downloaded research
document was saved over it — both files ended up byte-identical under two names.
It had never been committed, so there is no copy in git and none on disk.

**Its conclusions survive** in
[three-stores](../../decisions/2026-08-18-three-stores.md), which was written
from a full reading and preserves the three-store architecture, the kill-list
with its reopening gates, the privacy findings, and the two places where the
research was out of date against the code. Nothing acted on has been lost — only
the citations and the wording.

If the original conversation still exists, re-export it to this folder under its
own name.

**The rule that follows:** commit a commissioned research document as soon as it
lands. It cost money and it is not reproducible.
