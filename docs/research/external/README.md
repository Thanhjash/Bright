# external/ — commissioned deep research

Answers we asked for from outside. **Evidence, not doctrine** — a finding here
becomes binding only when a `decisions/` file adopts it.

| Document | Adopted in |
|---|---|
| Offline bilingual classroom speech IO | ASR adopted, **but `base` not `small`** — see below. TTS **not** adopted |
| Code-switching inside one sentence | corrects the brief above. Its §11 span fallback is now shipped; typed spans are not |
| Storage, Memory, and Retrieval for Bright | [three-stores](../../decisions/2026-08-18-three-stores.md) |
| Practice, Assessment, and Evidence for an Autonomous Whole-Class Teacher | [evidence-and-practice](../../decisions/2026-08-18-evidence-and-practice.md) |

## The shipped ASR model is `base`, not `small`

This file said `small` for two days and the running appliance said something
else again. Measured on the live service 2026-08-20, Piper `vi` clips, three
repeats each: `small` returns an **empty** transcript for *"Con không biết"*
3 times out of 3 at 3× the latency, while `base` returns *"Bà không biết"*
every time. An empty transcript is not a worse answer, it is silence — the room
cannot tell it from a child who never spoke. Full table in
`services/speech/app.py`; all three declarations now agree on `base`.

The research's advice still stands and is unchanged by this: **do not replace
the ASR family before the 72-child locked evaluation.** `base` vs `small` is a
size choice inside the adopted family, not a new adoption.

## Gemma 4 audio does not replace ASR — and the doctrine already says so

Gemma 4 E4B really does accept audio: model-card capability *text/image/audio*,
30-second cap, text out — both verified in
[fact-check-gpt-brief](../../decisions/fact-check-gpt-brief.md) rows 9 and 10.
That is where the good news stops.

- **OpenVINO — the runtime that IS the Intel showcase — documents text and
  image only. Audio is unconfirmed.** The same fact-check calls the
  "Gemma verifies ambiguous utterances" idea *"may be dead on the Intel box.
  Do not design anything that depends on it."* Spike SP-1 was meant to settle
  it and has never run, because the hardware SKU is still undecided.
- **It is the wrong shape for the hot path.** A turn already costs ~16 s, of
  which ~95% is model time. Replacing a 2.5 s Whisper call with another pass
  through the same busy LLM is a latency regression bought with a dependency.
- **It is the worst possible transcriber for this room, on our own doctrine.**
  NS-5 forbids exactly this failure: a decoder that knows the curriculum
  *"hears a child fumble and writes down the word the lesson expected — and
  then evidence of mastery exists for something the child never said."* An LLM
  holding the lesson plan is maximally exposed to it. Keep the raw transcript
  raw; interpretation is a separate, separately-named step.

[option-b-classroom-runtime](../../decisions/option-b-classroom-runtime.md)
already writes the conclusion: *"Gemma native audio may later implement the ASR
provider interface, but dedicated ASR remains canonical until that independent
benchmark passes. Model support for audio alone is not proof that the serving
and Hermes transports support the required path."*

## TTS: the architecture matters more than the model

The follow-up's §10 is the finding to act on, and it is not a model swap:

1. **Pre-render authored curriculum speech at build time** → an accepted audio
   asset, played by `play_clip`. Zero synthesis latency in the lesson, no
   language-detection failure, human-auditable pronunciation, and one bad line
   can be rejected without rejecting a model. Not yet done.
2. **Carry typed VI/EN spans instead of re-detecting them.** The teacher knows
   which span is which; making G2P rediscover it is where both Piper and
   SEA-G2P fail. Not yet done — it needs a home that does not violate the
   `say` accretion tripwire.

**Shipped 2026-08-20:** the §11 fallback, one voice per *sentence* rather than
one per line. It was not a nicety. Measured on lines she really said, a single
Vietnamese letter anywhere put the whole line through the Vietnamese voice, so
*"Say with me: Fine, thank you."* transcribed back as
`'Kosoco Sado, Sao Yume, Fai, Vakiu'`. After the split it comes back as
`"say with me. Fine, thank you."` The English a child is asked to copy is now
intelligible; before, it was noise.

## VieNeu-TTS is a candidate, not a solution

The first survey called it "recommended". The follow-up downgraded it to
**"must pass Bright acceptance testing"**, and that is the status to quote.
Its engineering fit is excellent and its licence is unusually clean, but the
exact thing Bright needs — that an intra-sentence VI↔EN switch keeps the same
perceived speaker, accent and prosody — has not been independently
demonstrated. Do not write "adopted" anywhere until it has.


## ~~Lost~~ Recovered: *Storage, Memory, and Retrieval for Bright*

Reported lost on 2026-08-18 — a newly downloaded document was believed to have
been saved over it, leaving two byte-identical files under different names.

**It is on disk and it is intact.** Checked 2026-08-20: every file in this
folder has a distinct checksum, and `Storage, Memory, and Retrieval for
Bright.md` opens with its own executive verdict. Either the overwrite never
happened or it was undone; the file is committed now, so it cannot recur.

Its conclusions were already carried into
[three-stores](../../decisions/2026-08-18-three-stores.md) — the three-store
architecture, the kill-list with its reopening gates, the privacy findings, and
the two places the research was out of date against the code. The citations and
wording are back too.

**The rule still stands, and is the reason this ended well:** commit a
commissioned research document the moment it lands. It cost money and it is not
reproducible.
