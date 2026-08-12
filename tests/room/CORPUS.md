# Room-safety corpus

The checked-in `audio/` corpus is synthetic: Bright-authored phrases rendered
with the local Piper voice and transformed by the commands in `room_test.py`.
It is CC0-1.0 and contains no child recordings or personal data.

Synthetic results are regression evidence only. They cannot approve a model for
classroom release. Real recordings belong in the ignored `wavs/` directory and
its `manifest.json`; do not commit raw audio.

Each real recording manifest entry must document:

- `file` and matching `case` (or an explicit `expect`)
- `speakerAlias` (non-identifying), `consent`: true
- `device`, `environment`, and `recordedAt`
- optional non-identifying notes such as distance and background-noise class

The release gate is zero false accepts across every case, condition, and repeat.
Any wrong or silent answer graded `correct` fails the run, including failures
caused by lesson authoring rather than the ASR model.
