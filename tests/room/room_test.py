#!/usr/bin/env python3
"""Room test for the Bright speech service — the ASR gate before the demo.

WHAT THIS MEASURES, EXACTLY
---------------------------
For every utterance it plays at the live service on :8001 it records two very
different things:

  1. the transcript                 -- what Whisper heard
  2. the GRADED OUTCOME             -- what the lesson would actually do about it

(2) is the one that decides anything, and it is not derivable from (1) by eye.
"Get." for "Cat." is a broken transcript; against `correct: ["cat"]` it grades
`wrong`, which is the same outcome the child would get for saying "dog" -- bad,
but survivable. "I don't like cats" is a PERFECT transcript that grades
`correct`. A transcript table would have called the first a failure and the
second a success, and both readings would be wrong.

So the outcome is computed by importing `grade()` from
`services/classroom-core/runner.py` -- the real function the real lesson runs,
with the real `Expect` dataclass from `packages/contracts/python`. This harness
contains no grading logic of its own. If core's rules change, this test changes
with them.

THE PASS CRITERION
------------------
    No wrong answer is SYSTEMATICALLY graded correct.

The release gate is literal: one false accept in one condition is a hard FAIL.
`--systematic-k` remains as a diagnostic grouping only; it never weakens that
gate. Telling a child they were right when they were not is the one failure
worse than latency.

Cases whose ORACLE outcome (what `grade()` returns for a *perfect* transcript)
disagrees with the authored teacher `intent` are reported in a separate section.
Those are lesson-authoring / protocol properties -- both models fail them
identically -- and folding them into the model comparison would blame the ASR
for something no ASR can fix.

AUDIO
-----
Two sources, and the harness always labels which one a number came from:

  synthetic  Piper via the service's own /audio/speech, then ffmpeg degradation.
             Reproducible, free, runs in CI. NOT child speech. Clean synthetic
             audio is exactly what misled this project once already: it cannot
             separate `tiny.en` from `small.en` on its own.
  real       Any .wav dropped in tests/room/wavs/ (see wavs/README). This is the
             source that is allowed to settle the question.

USAGE
-----
    python3 tests/room/room_test.py                       # both models, all synthetic conditions
    python3 tests/room/room_test.py --models tiny.en
    python3 tests/room/room_test.py --conditions real     # only the recorded wavs
    python3 tests/room/room_test.py --repeats 3           # more latency samples

The resident model is swapped through POST /admin/model and RESTORED at the end
(including on Ctrl-C), because other services share this process.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# --- the real grader, not a copy of it -------------------------------------
sys.path.insert(0, str(ROOT / "services" / "classroom-core"))
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "python"))
try:
    from bright_contracts import Expect  # type: ignore
    from runner import grade, normalize_text  # type: ignore
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        f"cannot import core's grader ({exc}).\n"
        "This harness deliberately refuses to run with a local copy of the "
        "grading rules -- the graded outcome is the whole point of the test."
    ) from exc

AUDIO_DIR = HERE / "audio"
WAV_DIR = HERE / "wavs"
RESULTS_DIR = HERE / "results"
DEFAULT_SERVICE = os.environ.get("SPEECH_URL", "http://127.0.0.1:8001")

# ---------------------------------------------------------------- conditions


@dataclass(frozen=True)
class Condition:
    name: str
    pitch: float          # 1.0 = untouched; >1 raises pitch AND formants
    room: bool            # mic band-limit + short reverb + babble/HVAC bed
    snr_db: float         # nominal, relative to the reference utterance level
    label: str


CONDITIONS: dict[str, Condition] = {
    "clean": Condition("clean", 1.0, False, 0.0, "Piper TTS, untouched"),
    "child": Condition(
        "child", 1.20, False, 0.0,
        "Piper pitch+formant shifted +20% -- NOT child speech, see caveat",
    ),
    "room": Condition(
        "room", 1.0, True, 15.0,
        "mic band 120-4000Hz + short reverb + babble/HVAC at ~15dB SNR",
    ),
    "child_room": Condition(
        "child_room", 1.20, True, 12.0,
        "both of the above, ~12dB SNR",
    ),
}
REAL = Condition("real", 1.0, False, 0.0, "recorded wavs from tests/room/wavs/")

# --------------------------------------------------------------- ffmpeg glue


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {' '.join(cmd)}\n{p.stderr[-2000:]}")
    return p.stderr + p.stdout


def _mean_dbfs(path: Path) -> float:
    out = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out)
    if not m:
        raise RuntimeError(f"no mean_volume for {path}")
    return float(m.group(1))


def _duration_s(path: Path) -> float:
    out = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    return float(out.strip().splitlines()[-1])


class NoiseBed:
    """A reusable classroom noise bed: overlapped Piper babble + pink HVAC hiss.

    Babble is built from real speech rather than white noise because what breaks
    ASR in a room full of children is other people's words, not hiss.
    """

    BABBLE_LINES = [
        "Look at the picture on the board and tell me what you see there.",
        "No it is my turn now, you had the red one before, give it back please.",
        "Teacher, teacher, can I go first? I know the answer to this one.",
    ]

    def __init__(self, client: "SpeechClient", cache: Path) -> None:
        self.client = client
        self.cache = cache
        self.path = cache / "noise_bed.wav"

    def ensure(self) -> Path:
        if self.path.exists():
            return self.path
        self.cache.mkdir(parents=True, exist_ok=True)
        parts = []
        for i, line in enumerate(self.BABBLE_LINES):
            p = self.cache / f"_babble{i}.wav"
            if not p.exists():
                p.write_bytes(self.client.tts(line))
            parts.append(p)
        # Overlap the three voices at staggered offsets, loop to 60 s, add pink
        # noise for the projector fan / air conditioning.
        inputs: list[str] = []
        for p in parts:
            inputs += ["-i", str(p)]
        filters = []
        for i, _ in enumerate(parts):
            delay = 900 * i
            filters.append(
                f"[{i}:a]aloop=loop=-1:size=2147483647,atrim=duration=60,"
                f"adelay={delay},volume=0.9[b{i}]"
            )
        mix_in = "".join(f"[b{i}]" for i in range(len(parts)))
        filters.append(f"{mix_in}amix=inputs={len(parts)}:duration=first:normalize=0[babble]")
        filters.append("anoisesrc=color=pink:duration=60:sample_rate=22050,volume=0.06[hvac]")
        filters.append("[babble][hvac]amix=inputs=2:duration=first:normalize=0[bed]")
        _run([
            "ffmpeg", "-hide_banner", "-y", *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[bed]", "-ac", "1", "-ar", "22050", str(self.path),
        ])
        return self.path


def build_clip(
    *,
    speech_wav: Path | None,
    out: Path,
    cond: Condition,
    bed: Path | None,
    noise_gain_db: float,
    seed: int,
) -> None:
    """Render one test clip. `speech_wav=None` means the silence case."""
    out.parent.mkdir(parents=True, exist_ok=True)
    chain: list[str] = []
    inputs: list[str] = []

    if speech_wav is None:
        # 1.6 s of nothing: the child never answered. With vad_filter on, the
        # right answer here is an empty transcript -> `silence` outcome.
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono:d=1.6"]
        chain.append("[0:a]volume=0[s]")
        dur = 1.6
    else:
        inputs += ["-i", str(speech_wav)]
        pre = []
        if cond.pitch != 1.0:
            # asetrate scales pitch AND formants together, which is the crude
            # part of "child-like": a real child is not a sped-up adult.
            rate = int(22050 * cond.pitch)
            pre.append(f"asetrate={rate},aresample=22050,atempo={1.0 / cond.pitch:.4f}")
        if cond.room:
            pre.append("highpass=f=120,lowpass=f=4000")
            pre.append("aecho=0.8:0.6:35|58:0.22|0.13")
        pre.append("adelay=400")            # leading room tone before the answer
        pre.append("apad=pad_dur=0.5")
        chain.append("[0:a]" + ",".join(pre) + "[s]")
        dur = _duration_s(speech_wav) / (1.0 if cond.pitch == 1.0 else 1.0) + 0.9

    if cond.room and bed is not None:
        offset = (seed * 7919) % 40
        inputs += ["-i", str(bed)]
        idx = 1 if speech_wav is not None else 1
        chain.append(
            f"[{idx}:a]atrim=start={offset}:duration={dur + 0.5:.2f},"
            f"asetpts=PTS-STARTPTS,volume={noise_gain_db:.2f}dB[n]"
        )
        chain.append("[s][n]amix=inputs=2:duration=first:normalize=0[out]")
    else:
        chain.append("[s]anull[out]")

    _run([
        "ffmpeg", "-hide_banner", "-y", *inputs,
        "-filter_complex", ";".join(chain),
        "-map", "[out]", "-ac", "1", "-ar", "16000", str(out),
    ])


# ------------------------------------------------------------------- client


class SpeechClient:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _post_json(self, path: str, payload: dict, timeout: float = 120.0) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def health(self) -> dict:
        with urllib.request.urlopen(self.base + "/health", timeout=10) as r:
            return json.loads(r.read())

    def tts(self, text: str) -> bytes:
        req = urllib.request.Request(
            self.base + "/audio/speech",
            data=json.dumps({"input": text, "voice": "en"}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    def set_model(self, name: str) -> dict:
        return self._post_json("/admin/model", {"model": name}, timeout=600)

    def transcribe(self, wav: Path) -> tuple[dict, float]:
        """Returns (server payload, client wall-clock seconds)."""
        boundary = uuid.uuid4().hex
        data = wav.read_bytes()
        ctype = mimetypes.guess_type(wav.name)[0] or "audio/wav"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{wav.name}"\r\n'.encode(),
            f"Content-Type: {ctype}\r\n\r\n".encode(),
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            self.base + "/audio/transcriptions",
            data=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = json.loads(r.read())
        return payload, time.perf_counter() - t0


# --------------------------------------------------------------------- cases


@dataclass
class Case:
    qid: str
    uid: str
    prompt: str
    say: str
    intent: str
    expect: Expect
    note: str = ""
    source: str = "synthetic"
    wav: Path | None = None

    @property
    def key(self) -> str:
        return f"{self.qid}/{self.uid}"

    @property
    def oracle(self) -> str:
        """What grade() returns for a PERFECT transcript of `say`."""
        return grade(self.expect, "speech", {"text": self.say, "confidence": 1.0}) or "silence"


def _expect(raw: dict) -> Expect:
    return Expect(
        kind=raw.get("kind", "speech"),
        correct=raw.get("correct"),
        acceptFuzzy=raw.get("acceptFuzzy"),
    )


def load_cases(path: Path) -> list[Case]:
    doc = json.loads(path.read_text())
    out: list[Case] = []
    for q in doc["questions"]:
        exp = _expect(q["expect"])
        for u in q["utterances"]:
            out.append(Case(
                qid=q["id"], uid=u["id"], prompt=q["prompt"], say=u["say"],
                intent=u["intent"], expect=exp, note=u.get("note", ""),
            ))
    return out


def load_real_cases(by_key: dict[str, Case]) -> list[Case]:
    """Load only consented, provenance-complete manifest recordings.

    Filenames never constitute consent. Unlisted WAVs are reported and skipped,
    even when their names happen to match a synthetic case.
    """
    if not WAV_DIR.is_dir():
        return []
    out: list[Case] = []
    manifest = WAV_DIR / "manifest.json"
    claimed: set[str] = set()
    if not manifest.exists():
        for f in sorted(WAV_DIR.glob("*.wav")):
            print(f"  ! {f.name}: no manifest/consent metadata, skipped", file=sys.stderr)
        return []
    if manifest.exists():
        for e in json.loads(manifest.read_text()).get("recordings", []):
            required_meta = ("speakerAlias", "consent", "device", "environment", "recordedAt")
            missing = [key for key in required_meta if key not in e]
            if missing or e.get("consent") is not True:
                print(
                    f"  ! {e.get('file', '<unknown>')}: missing consent/provenance "
                    f"metadata {missing}, skipped",
                    file=sys.stderr,
                )
                continue
            f = WAV_DIR / e["file"]
            if not f.exists():
                print(f"  ! manifest lists missing file {e['file']}", file=sys.stderr)
                continue
            base = by_key.get(e.get("case", ""))
            expect = _expect(e["expect"]) if "expect" in e else (base.expect if base else None)
            if expect is None:
                print(f"  ! {e['file']}: no case/expect, skipped", file=sys.stderr)
                continue
            out.append(Case(
                qid=(base.qid if base else "real"),
                uid=f.stem,
                prompt=(base.prompt if base else e.get("prompt", "")),
                say=e.get("say", base.say if base else ""),
                intent=e.get("intent", base.intent if base else "correct"),
                expect=expect, source="real", wav=f,
                note=(
                    e.get("note", "")
                    + f" speakerAlias={e['speakerAlias']} device={e['device']} "
                    + f"environment={e['environment']} recordedAt={e['recordedAt']}"
                ),
            ))
            claimed.add(f.name)
    for f in sorted(WAV_DIR.glob("*.wav")):
        if f.name in claimed:
            continue
        print(f"  ! {f.name}: no valid manifest/consent metadata, skipped", file=sys.stderr)
    return out


# ------------------------------------------------------------------- running


@dataclass
class Row:
    model: str
    condition: str
    case: str
    source: str
    say: str
    intent: str
    oracle: str
    heard: str = ""
    outcome: str = ""
    exact: bool = False
    avg_logprob: float | None = None
    confidence: float = 0.0
    no_speech_probability: float = 1.0
    wall_ms: int = 0
    server_ms: int = 0
    decode_ms: int = 0
    infer_ms: int = 0
    queue_ms: int = 0
    audio_s: float = 0.0
    repeat: int = 0
    note: str = ""

    @property
    def false_accept(self) -> bool:
        """A wrong answer that the lesson would celebrate. The thing that must not happen."""
        return self.intent in ("wrong", "silence") and self.outcome == "correct"

    @property
    def false_reject(self) -> bool:
        return self.intent == "correct" and self.outcome in ("wrong", "silence")

    @property
    def model_attributable(self) -> bool:
        """False when the authored expect already disagrees with teacher intent —
        then both models fail identically and it is not an ASR result."""
        return self.oracle == self.intent


def prepare_audio(client: SpeechClient, cases: list[Case], conds: list[Condition]) -> dict:
    """Synthesise + degrade every (case, condition) clip, cached on disk."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = AUDIO_DIR / "raw"
    raw_dir.mkdir(exist_ok=True)
    need_bed = any(c.room for c in conds)
    bed_path = None
    ref_dbfs = None

    for case in cases:
        if not case.say:
            continue
        raw = raw_dir / f"{case.qid}__{case.uid}.wav"
        if not raw.exists():
            raw.write_bytes(client.tts(case.say))

    if need_bed:
        bed = NoiseBed(client, AUDIO_DIR)
        bed_path = bed.ensure()
        # One reference level for the whole run so the noise bed sits at a fixed
        # absolute level, as a real room does, rather than tracking each clip.
        ref = raw_dir / f"{cases[0].qid}__{cases[0].uid}.wav"
        ref = ref if ref.exists() else next(raw_dir.glob("*.wav"))
        ref_dbfs = _mean_dbfs(ref)
        bed_dbfs = _mean_dbfs(bed_path)

    clips: dict[tuple[str, str], Path] = {}
    for cond in conds:
        gain = 0.0
        if cond.room and ref_dbfs is not None:
            gain = ref_dbfs - bed_dbfs - cond.snr_db
        for i, case in enumerate(cases):
            out = AUDIO_DIR / cond.name / f"{case.qid}__{case.uid}.wav"
            if not out.exists():
                build_clip(
                    speech_wav=(raw_dir / f"{case.qid}__{case.uid}.wav") if case.say else None,
                    out=out, cond=cond, bed=bed_path, noise_gain_db=gain, seed=i + 1,
                )
            clips[(cond.name, case.key)] = out
    return clips


def run_model(
    client: SpeechClient, model: str, work: list[tuple[Condition, Case, Path]], repeats: int
) -> list[Row]:
    print(f"\n=== {model} ===", flush=True)
    swap = client.set_model(model)
    print(f"  model resident (load {swap['loadMs']} ms)", flush=True)
    # Warm-up: the first call after a load is inflated and would poison the
    # latency numbers if it were counted.
    if work:
        client.transcribe(work[0][2])

    rows: list[Row] = []
    for rep in range(repeats):
        for cond, case, wav in work:
            payload, wall = client.transcribe(wav)
            if payload.get("model") != model:
                raise RuntimeError(
                    f"service answered as {payload.get('model')!r} while testing {model!r} "
                    "-- another process swapped the model mid-run; results discarded"
                )
            heard = payload.get("text", "")
            confidence = float(payload.get("confidence") or 0.0)
            outcome = grade(
                case.expect, "speech", {"text": heard, "confidence": confidence}
            ) or "silence"
            rows.append(Row(
                model=model, condition=cond.name, case=case.key, source=case.source,
                say=case.say, intent=case.intent, oracle=case.oracle,
                heard=heard, outcome=outcome,
                exact=normalize_text(heard) == normalize_text(case.say),
                avg_logprob=payload.get("avgLogprob"),
                confidence=confidence,
                no_speech_probability=float(payload.get("noSpeechProbability") or 0.0),
                wall_ms=round(wall * 1000), server_ms=payload.get("ms", 0),
                decode_ms=payload.get("decodeMs", 0), infer_ms=payload.get("inferMs", 0),
                queue_ms=payload.get("queueMs", 0),
                audio_s=payload.get("audioS", 0.0), repeat=rep, note=case.note,
            ))
            flag = "  <-- FALSE ACCEPT" if rows[-1].false_accept else ""
            print(f"  [{cond.name:<10}] {case.key:<24} say={case.say!r:<24} "
                  f"heard={heard!r:<28} -> {outcome:<8} {rows[-1].wall_ms:>5}ms{flag}", flush=True)
    return rows


# ------------------------------------------------------------------ reporting


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.0f}%" if d else "n/a"


def summarise(rows: list[Row], models: list[str], systematic_k: int) -> tuple[str, bool, dict]:
    lines: list[str] = []
    attributable = [r for r in rows if r.model_attributable]
    authoring = [r for r in rows if not r.model_attributable]
    conds = sorted({r.condition for r in rows})

    lines.append("## Grading outcomes (the number that decides)\n")
    lines.append("Only cases where a perfect transcript agrees with teacher intent; "
                 "the rest are in the authoring section below.\n")
    lines.append("| model | condition | n | transcript exact | graded as intended | "
                 "FALSE ACCEPT (wrong→correct) | false reject (correct→wrong/silence) |")
    lines.append("|---|---|--:|--:|--:|--:|--:|")
    stats: dict = {}
    for m in models:
        for c in conds:
            sub = [r for r in attributable if r.model == m and r.condition == c]
            if not sub:
                continue
            fa = [r for r in sub if r.false_accept]
            fr = [r for r in sub if r.false_reject]
            ok = [r for r in sub if r.outcome == r.intent]
            ex = [r for r in sub if r.exact]
            lines.append(
                f"| `{m}` | {c} | {len(sub)} | {_pct(len(ex), len(sub))} | "
                f"{_pct(len(ok), len(sub))} | **{len(fa)}** | {len(fr)} |"
            )
            stats[f"{m}/{c}"] = {
                "n": len(sub), "exact": len(ex), "asIntended": len(ok),
                "falseAccept": len(fa), "falseReject": len(fr),
            }

    # --- the gate
    lines.append("\n## Pass criterion — zero wrong answers graded correct\n")
    failed = False
    for m in models:
        # Safety is independent of attribution: an authored rule that accepts
        # a wrong answer is still an unsafe release and must fail this gate.
        fa = [r for r in rows if r.model == m and r.false_accept]
        by_case: dict[str, set[str]] = {}
        for r in fa:
            by_case.setdefault(r.case, set()).add(r.condition)
        systematic = {k: v for k, v in by_case.items() if len(v) >= systematic_k}
        if by_case:
            failed = True
            qualifier = (
                f"; {len(systematic)} systematic across >= {systematic_k} conditions"
                if systematic else ""
            )
            lines.append(f"- **`{m}`: FAIL.** {len(by_case)} false-accept case(s){qualifier}:")
            for k, v in sorted(by_case.items()):
                ex = next(r for r in fa if r.case == k)
                lines.append(f"  - `{k}` said {ex.say!r} heard {ex.heard!r} in {sorted(v)}")
        else:
            lines.append(f"- **`{m}`: PASS.** No wrong answer was graded correct in any condition.")

    # --- latency
    lines.append("\n## Latency (client wall clock, per call)\n")
    lines.append("| model | n | median | p90 | max | median inference | median decode | "
                 "median HTTP+queue |")
    lines.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for m in models:
        sub = [r for r in rows if r.model == m]
        if not sub:
            continue
        w = sorted(r.wall_ms for r in sub)
        lines.append(
            f"| `{m}` | {len(sub)} | {statistics.median(w):.0f} ms | "
            f"{w[int(0.9 * (len(w) - 1))]:.0f} ms | {w[-1]:.0f} ms | "
            f"{statistics.median([r.infer_ms for r in sub]):.0f} ms | "
            f"{statistics.median([r.decode_ms for r in sub]):.0f} ms | "
            f"{statistics.median([r.wall_ms - r.server_ms for r in sub]):.0f} ms |"
        )

    # --- disagreements worth a human eye
    lines.append("\n## Every grading disagreement\n")
    lines.append("| model | condition | case | said | heard | graded | should be |")
    lines.append("|---|---|---|---|---|---|---|")
    bad = [r for r in attributable if r.outcome != r.intent]
    for r in bad:
        lines.append(f"| `{r.model}` | {r.condition} | `{r.case}` | {r.say!r} | "
                     f"{r.heard!r} | **{r.outcome}** | {r.intent} |")
    if not bad:
        lines.append("| — | — | — | — | — | — | none |")

    if authoring:
        lines.append("\n## Not the model's fault — authoring / protocol\n")
        lines.append("A perfect transcript already grades against teacher intent here, "
                     "so every model behaves the same way.\n")
        lines.append("| case | said | perfect transcript grades | teacher means | why |")
        lines.append("|---|---|---|---|---|")
        seen = set()
        for r in authoring:
            if r.case in seen:
                continue
            seen.add(r.case)
            lines.append(f"| `{r.case}` | {r.say!r} | **{r.oracle}** | {r.intent} | {r.note} |")

    return "\n".join(lines), not failed, stats


# ----------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", default=DEFAULT_SERVICE)
    ap.add_argument("--models", default="tiny.en,small.en")
    ap.add_argument("--conditions", default="clean,child,room,child_room",
                    help="comma list of " + ",".join(CONDITIONS) + ",real")
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--systematic-k", type=int, default=2,
                    help="group false accepts seen in >= K conditions (diagnostic only; one always fails)")
    ap.add_argument("--out", default=str(RESULTS_DIR))
    ap.add_argument("--keep-model", action="store_true",
                    help="leave the last tested model resident instead of restoring")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to build the synthetic clips")

    client = SpeechClient(args.service)
    try:
        health = client.health()
    except Exception as exc:
        raise SystemExit(f"speech service not reachable at {args.service}: {exc}")
    if not health.get("stt"):
        raise SystemExit(f"service has no STT loaded: {health}")
    original = health.get("sttModel")
    print(f"service {args.service}  resident={original}  available={health.get('sttModelsAvailable')}")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in models if m not in (health.get("sttModelsAvailable") or [])]
    if unknown:
        raise SystemExit(f"models not available on the service: {unknown}")

    cases = load_cases(Path(args.cases))
    by_key = {c.key: c for c in cases}
    wanted = [c.strip() for c in args.conditions.split(",") if c.strip()]
    synth_conds = [CONDITIONS[c] for c in wanted if c in CONDITIONS]
    want_real = "real" in wanted

    work: list[tuple[Condition, Case, Path]] = []
    if synth_conds:
        print(f"building synthetic clips ({len(cases)} utterances x {len(synth_conds)} conditions)...")
        clips = prepare_audio(client, cases, synth_conds)
        for cond in synth_conds:
            for case in cases:
                work.append((cond, case, clips[(cond.name, case.key)]))
    if want_real:
        real = load_real_cases(by_key)
        if not real:
            print(f"  ! no usable recordings in {WAV_DIR} — the synthetic set alone "
                  "cannot settle tiny vs small", file=sys.stderr)
        for case in real:
            work.append((REAL, case, case.wav))  # type: ignore[arg-type]
    if not work:
        raise SystemExit("nothing to run")

    print(f"{len(work)} clips x {len(models)} models x {args.repeats} repeat(s) = "
          f"{len(work) * len(models) * args.repeats} transcriptions")

    rows: list[Row] = []
    t0 = time.time()
    try:
        for m in models:
            rows += run_model(client, m, work, args.repeats)
    finally:
        if original and not args.keep_model:
            try:
                client.set_model(original)
                print(f"\nrestored resident model: {original}")
            except Exception as exc:
                print(f"!! COULD NOT RESTORE MODEL {original}: {exc}", file=sys.stderr)

    report, passed, stats = summarise(rows, models, args.systematic_k)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{stamp}-rows.json").write_text(json.dumps(
        {
            "generatedAt": stamp,
            "service": args.service,
            "models": models,
            "conditions": [c.name for c in synth_conds] + (["real"] if want_real else []),
            "conditionLabels": {c.name: c.label for c in synth_conds} | ({"real": REAL.label} if want_real else {}),
            "systematicK": args.systematic_k,
            "releaseGate": "zero false accepts across every case/condition/repeat",
            "corpus": json.loads(Path(args.cases).read_text()).get("corpus", {}),
            "elapsedS": round(time.time() - t0, 1),
            "stats": stats,
            "rows": [r.__dict__ | {"falseAccept": r.false_accept,
                                   "modelAttributable": r.model_attributable} for r in rows],
        }, indent=2))
    head = (f"# Room test — {stamp}\n\n"
            f"Service `{args.service}`, {len(rows)} transcriptions, "
            f"{round(time.time() - t0)} s.\n\n"
            f"Audio: " + "; ".join(f"**{c.name}** = {c.label}" for c in synth_conds)
            + ("; **real** = " + REAL.label if want_real else "") + "\n\n")
    (outdir / f"{stamp}-summary.md").write_text(head + report + "\n")
    print("\n" + report)
    print(f"\nwrote {outdir / (stamp + '-summary.md')}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
