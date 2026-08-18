# Offline bilingual classroom speech I/O for Bright

## Decision

As of **August 18, 2026**, my recommendation is:

**TTS: VieNeu-TTS v3 Turbo, ONNX INT8, CPU, fixed preset voice, frame-streamed through `services/speech`.**

**ASR: faster-whisper `small` multilingual, CTranslate2 INT8 on CPU. Replace `small.en`, do not add a separate language detector.**

VieNeu-TTS is the first candidate in this survey that cleanly matches the whole TTS problem rather than only pieces of it. Its current v3 Turbo path explicitly targets **Vietnamese-English bilingual code-switching**, uses a single speaker embedding across the generated line, has a torch-free ONNX CPU implementation, defaults to an INT8 backbone, and exposes frame-level streaming. The maintainer reports first audio around **300 ms** and roughly **2 to 3 times real-time generation on a laptop CPU**, which puts the requested 800 ms first-audio target within reach. Those latency numbers are maintainer measurements, not an independent cheap-Intel benchmark, so they must be treated as a hypothesis to validate on Bright's actual box. citeturn25search4turn25search6 The current GitHub `main` is v3.2.5 at commit `54f42abf4460e68aac79c985b9446557c2180f2f`, dated August 13, 2026. fileciteturn33file0L2-L2

The licensing story is unusually good for this use case. The VieNeu repository is Apache-2.0, its `sea-g2p` dependency is Apache-2.0, and the MOSS components used by v3 Turbo are Apache-2.0. Apache-2.0 permits redistribution, modification and commercial use, subject to its notice and attribution requirements. fileciteturn9file0L2-L2 fileciteturn16file0L2-L2 citeturn24search2turn24search4 I found no separate restrictive "sample/demo only" licence attached to the 14 built-in v3 Turbo preset voice embeddings and reference codes, which are bundled as repository assets. That is materially better than a Live2D-like situation where sample assets have a different licence from the runtime. Still, for a distribution measured in tens of millions of children, Bright should archive the exact LICENSE files and voice asset provenance with every release rather than infer rights from a GitHub badge. fileciteturn14file0L2-L2

For recognition, there is no reason to rebuild the stack. The multilingual Whisper `small` checkpoint is a **244M-parameter multilingual model**, while `small.en` is the English-only variant Bright currently uses. fileciteturn26file0L2-L2 faster-whisper's official CPU benchmark transcribes 13 minutes of audio in **1m42s using INT8 and 1,477 MB RAM on an i7-12700K with eight threads**, an RTF of about 0.131. Linearized to three seconds of audio, that is about **0.39 seconds of model processing**, although a real 3-second request has fixed startup and decoding overhead and therefore will not scale perfectly from the long-file benchmark. fileciteturn22file0L2-L2 This is a far safer route to the `<2 s` requirement than moving immediately to Whisper `medium`, NeMo, or another runtime.

The resulting architecture is deliberately boring:

```text
Core
  │
  ├── POST /audio/speech
  │       services/speech
  │         └── VieNeu-TTS v3 Turbo, ONNX INT8, resident
  │                └── streamed PCM/WAV
  │                       └── Stage, only loudspeaker
  │
  └── child turn
          microphone
             └── POST /audio/transcriptions
                    services/speech
                      └── faster-whisper small multilingual, INT8, resident
                             └── transcript
                                   └── Core
```

**Do not put either model on Hermes. Do not use AIRI's streaming TTS server.** ElevenLabs, Google, Azure and OpenAI speech services can remain research-quality reference points, but they should not exist in the production dependency graph because a classroom must continue working with the WAN disconnected.

The one serious caveat is that **VieNeu v3 Turbo is still a fast-moving, beta/early-access project**. Its current Python package labels itself Development Status Beta. fileciteturn31file0L2-L2 I would therefore ship a **pinned, vendored snapshot**, never `pip install -U vieneu` at classroom boot, and I would refuse rollout until it passes Bright's mixed-language corpus on the exact low-cost Intel SKU.

## TTS comparison

Here, **"drop-in for Piper" means Bright can replace the engine behind `POST /audio/speech` without changing Core or Stage**, not that the candidate can literally be loaded by Piper as a Piper checkpoint.

| Name | Repo URL | Weights URL | Licence | Bilingual / code-switch? | ONNX / OpenVINO? | RAM | CPU RTF | Vietnamese quality | English quality | Both in ONE utterance? | Drop-in for Piper? | Shippable? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **VieNeu-TTS v3 Turbo** ★ | [GitHub](https://github.com/pnnbao97/VieNeu-TTS) | [HF model](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo), plus [MOSS codec](https://huggingface.co/OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX) | **Apache-2.0** repo/model stack. `sea-g2p` also Apache-2.0. fileciteturn9file0L2-L2 fileciteturn16file0L2-L2 | **Explicit EN-VI bilingual code-switching.** The project describes seamless English-Vietnamese switching and uses a bilingual G2P pipeline. citeturn25search4 fileciteturn19file0L2-L2 | **Native ONNX. INT8 default on CPU.** No official OpenVINO IR needed. Current engine runs ORT `CPUExecutionProvider`. fileciteturn11file0L2-L2 | Runtime RSS not officially published. `onnx_int8` backbone assets are about **165 MB**, plus codec and runtime. citeturn24search15 | Maintainer reports ~2-3× realtime on laptop CPU, so roughly **RTF 0.33-0.5**; first audio ~300 ms. Must benchmark Intel target. citeturn25search6 | **High-potential**, purpose-built for Vietnamese, but no independent classroom benchmark found. | **High-potential**, trained bilingual rather than bolted-on English. No independent Bright-like benchmark found. | **YES, strongest candidate.** One preset speaker embedding is resolved for the mixed text before generation. fileciteturn30file0L2-L2 | **Yes at Bright API layer**, small adapter, not Piper model format. | **YES**, preferred licence. |
| **Supertonic 3** | [GitHub](https://github.com/supertone-inc/supertonic) | [HF](https://huggingface.co/Supertone/supertonic-3) | MIT code, OpenRAIL-family model licence, redistributable with restrictions rather than simple Apache/MIT terms. fileciteturn5file0L2-L2 | 31 languages including EN and VI, plus `lang="na"` language-agnostic mode. fileciteturn5file0L2-L2 | **Native ONNX**, 99M parameters. fileciteturn4file0L2-L2 | Compact, 99M parameter class; official material says low-memory edge deployment but does not give a universal desktop RSS. fileciteturn4file0L2-L2 | Project reports around RTF 0.3 on constrained hardware in its performance material. | Reading benchmark WER 4.49 for VI. fileciteturn4file0L2-L2 | Reading benchmark WER 2.06 for EN. fileciteturn4file0L2-L2 | **Maybe, not sufficiently proven.** Current preprocessing wraps the whole call in one language tag, rather than explicit per-span EN/VI tags. `na` is plausible for mixed input, but this is weaker evidence than VieNeu's explicit code-switch support. fileciteturn2file0L2-L2 | Yes, adapter. It even offers an OpenAI-compatible local HTTP endpoint. fileciteturn5file0L2-L2 | Conditional yes, but **not my choice**. Repo announced July 23, 2026 that it will be archived with no further official open-source development/support. fileciteturn5file0L2-L2 |
| **NVIDIA MagpieTTS Multilingual 357M** | [NeMo](https://github.com/NVIDIA/NeMo) / [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) | [HF](https://huggingface.co/nvidia/magpie_tts_multilingual_357m) | NVIDIA Open Model License, redistribution/commercial use permitted subject to its terms and notices. citeturn19search0 | **Yes.** Current multilingual release includes English and Vietnamese and explicitly supports multilingual/code-switch scenarios with shared speaker identity. citeturn3search0turn4search1 | NeMo plus local `NeMo-Speech.cpp`; current TTS converter path exposes f16/f32 rather than q8 for Magpie/NanoCodec. citeturn5search0turn5search2 | Larger than the VieNeu/Supertonic class, 357M model plus codec; cheap-Intel RSS not officially established. | **No trustworthy cheap-Intel number published that clears Bright's 800 ms TTFA target.** | Likely excellent, official multilingual model. | Likely excellent. | **YES.** | Adapter required. | Yes under NVIDIA terms, but **hardware/latency risk makes it runner-up, not winner**. |
| **Piper multi-speaker / two-language baseline** | [Archived original](https://github.com/rhasspy/piper) | Existing Bright Piper voice files | Original project MIT; upstream development has moved. citeturn7search0 | Multi-speaker is not multilingual code-switching. Bright's EN and VI checkpoints remain separate models/voices. | Native ONNX. | Excellent, already known on Bright. | Excellent CPU speed. | Good within VI voice. | Good within EN voice. | **NO.** Switching checkpoints or speaker identities mid-line recreates the "two people" defect. | Native. | Yes, but capability fail. |
| **Meta MMS-TTS Vietnamese** | [MMS/fairseq](https://github.com/facebookresearch/fairseq/tree/main/examples/mms) | [HF `facebook/mms-tts-vie`](https://huggingface.co/facebook/mms-tts-vie) | **CC-BY-NC-4.0.** citeturn7search1turn7search5 | Vietnamese checkpoint only. | VITS architecture can be exported, but not a ready bilingual Bright ONNX deployment. | Small/moderate VITS class. No relevant official classroom RSS result. | CPU-feasible, but irrelevant because of capability/licence. | Good specialist VI. | Not supported by VI checkpoint. | **NO.** | No. | **NO. Hard licence fail** under Bright's rule. |
| **Coqui XTTS-v2** | [GitHub](https://github.com/coqui-ai/TTS) | [HF](https://huggingface.co/coqui/XTTS-v2) | **Coqui Public Model License**, non-commercial restrictions. citeturn7search2 | Multilingual, but Vietnamese is not a first-class official XTTS-v2 language and the API is language-conditioned rather than a proven EN-VI mixed-line solution. | Primarily PyTorch; third-party export work exists, not the small clean INT8 path Bright wants. | Large, hundreds-of-millions-class stack; uncomfortable beside Gemma. | CPU path is not attractive for `<800 ms` first audio on a cheap box. | Not a supported strength. | Strong. | **NO for Bright requirement.** | Adapter. | **NO. Licence fail**, irrespective of quality. |
| **Kokoro-82M** | [GitHub](https://github.com/hexgrad/kokoro) | [HF](https://huggingface.co/hexgrad/Kokoro-82M) | **Apache-2.0.** citeturn1view2 | Multilingual variants exist, but the official supported set does **not include Vietnamese**. citeturn1view2 | Small model with ONNX ecosystem/ports; attractive footprint. | Excellent 82M-class footprint. | Potentially excellent CPU deployment. | **Unsupported.** | Strong. | **NO.** | Adapter. | Licence yes, capability no. |
| **StyleTTS2** | [GitHub](https://github.com/yl4579/StyleTTS2) | [Official pretrained-model section](https://github.com/yl4579/StyleTTS2#pre-trained-models) | Permissive code, but each external checkpoint needs separate provenance review. | Architecture can be trained multilingual, but the official ready checkpoints are not a production EN-VI code-switch model. citeturn7search3 | Community ONNX work exists, not an official optimized bilingual deployment. citeturn7search11 | Depends heavily on auxiliary stack; not a compelling 16 GB choice. | No authoritative Bright-like CPU number. | Requires a VI checkpoint/training effort. | Good research quality in supported English setups. | **NO out of box.** | No. | Code potentially yes, usable required checkpoint no. |
| **OpenVoice v2 + Intel OpenVINO sample** | [OpenVoice](https://github.com/myshell-ai/OpenVoice) | [HF OpenVoice](https://huggingface.co/myshell-ai/OpenVoiceV2) | Permissive/open project terms, but base-speaker components must be reviewed as a complete stack. | Cross-lingual **tone-colour transfer** is the point, but that does not magically make the underlying base TTS a Vietnamese-English code-switch synthesizer. | **Intel has an OpenVINO OpenVoice sample**, so acceleration is real. citeturn21search7 | Multi-component stack. | No evidence it beats the purpose-built VieNeu path on cheap Intel for this exact workload. | VI base-generation gap. | Good in supported bases. | **NO turnkey.** | No. | Technically distributable pieces exist, capability fail. |
| **VietTTS** | [GitHub](https://github.com/NTT123/vietTTS) | [Pretrained section](https://github.com/NTT123/vietTTS) | MIT-style licence, including use, modification and redistribution rights. fileciteturn34file0L2-L2 | Vietnamese specialist only. Project is no longer the active general bilingual path. citeturn14search22 | Can be optimized/exported with work, not a current turnkey mixed-language runtime. | Relatively light. | CPU-feasible. | Good specialist option historically. | Not target. | **NO.** | No. | Licence yes, capability no. |

A useful distinction emerges from the whole table. **"Multilingual" is not the same thing as "code-switches naturally inside one sentence."** Supertonic knows both languages, Piper can load both languages, OpenVoice can transfer a voice across languages, and XTTS is multilingual, but the Bright requirement is tighter: the system must keep **one teacher identity** while moving through something like:

> `Chào con! Look, this is the market. Chợ đó.`

VieNeu explicitly advertises that EN-VI use case, and its current implementation resolves a single preset's `speaker_emb` and reference codes before processing the text and feeding the bilingual phonemizer. fileciteturn30file0L2-L2 The project currently includes 14 fixed presets, with `Minh Đức` as the default. fileciteturn14file0L2-L2 That is structurally much closer to Bright's requirement than stitching two VITS/Piper voices together.

Intel's OpenVINO work is worth watching, but I would not make it a selection criterion by itself. Current Intel material includes OpenVoice acceleration and newer experimental speech/TTS integrations such as CosyVoice-family examples, but none gives Bright a better combination of **small CPU deployment + Vietnamese + English + one-speaker mid-sentence switching + known permissive packaging** than VieNeu right now. citeturn21search7turn21search9

## ASR comparison

For the latency column, numbers derived from the faster-whisper official 13-minute benchmark are labelled **throughput-equivalent**, because processing a three-second file has fixed per-request costs that a long benchmark amortizes. The benchmark ran on an Intel Core i7-12700K with eight threads. fileciteturn22file0L2-L2

| Name | Repo URL | Weights URL | Licence | Languages | Child / noisy-room notes | RAM | Latency for 3 s clip | OpenVINO? | Drop-in for faster-whisper? |
|---|---|---|---|---|---|---|---|---|---|
| **faster-whisper `small` multilingual INT8** ★ | [GitHub](https://github.com/SYSTRAN/faster-whisper) | [HF `Systran/faster-whisper-small`](https://huggingface.co/Systran/faster-whisper-small) | faster-whisper **MIT**; underlying Whisper code/weights lineage MIT. fileciteturn23file0L2-L2 fileciteturn24file0L2-L2 | Whisper `small` is multilingual, unlike `small.en`; EN and VI are in one decoder/tokenizer. fileciteturn26file0L2-L2 | Whisper was trained on diverse audio, but there is **no Vietnamese-child-classroom benchmark** I would trust as a substitute for Bright's own recordings. Built-in Silero VAD is available. fileciteturn22file0L2-L2 | **1,477 MB** in official small/CPU/INT8 benchmark. fileciteturn22file0L2-L2 | **~0.39 s throughput-equivalent** from official 102s / 780s result. Real 3s call should be measured. | No, uses CTranslate2. | **YES. Change model from `small.en` to local `small`.** |
| **faster-whisper `medium` multilingual INT8** | Same repo | [HF `Systran/faster-whisper-medium`](https://huggingface.co/Systran/faster-whisper-medium) | MIT stack. | Multilingual; Whisper medium has **769M parameters** versus small's 244M. fileciteturn26file0L2-L2 | More capacity can help difficult speech, but classroom-child improvement is not guaranteed without measuring. | Materially larger; official Whisper lists a much larger memory class than small. fileciteturn26file0L2-L2 | No equivalent official CPU benchmark in the cited faster-whisper table; likely slower than small. | No. | **YES**, same API, but poor first choice for 16 GB shared box. |
| **Whisper `small` via whisper.cpp + OpenVINO** | [whisper.cpp](https://github.com/ggerganov/whisper.cpp) / Intel OpenVINO examples | [OpenAI Whisper small](https://huggingface.co/openai/whisper-small) | MIT Whisper; runtime licences permissive. | Same multilingual Whisper capability as small. | Same model-level robustness; different runtime. | **1,642 MB** in faster-whisper's published comparison. fileciteturn22file0L2-L2 | **~0.40 s throughput-equivalent**, 105s / 780s. fileciteturn22file0L2-L2 | **YES.** Intel also documents Whisper conversion/inference through OpenVINO tooling. citeturn14search3 | **No**, requires replacing runtime adapter. |
| **Distil-Whisper `distil-large-v3.x`** | [GitHub](https://github.com/huggingface/distil-whisper) | [HF Distil-Whisper](https://huggingface.co/distil-whisper) | MIT-family open model distribution. | Current Distil-Whisper family is fundamentally **English-oriented/monolingual**, not a VI+EN replacement. citeturn13search2turn13search4 | Strong English efficiency is irrelevant when Vietnamese is mandatory. | Large distilled model, still far bigger than Whisper small. | Not relevant, capability fail. | Conversion paths exist. | faster-whisper can run Distil-Whisper checkpoints, but **do not use it here**. fileciteturn22file0L2-L2 |
| **PhoWhisper** | [GitHub](https://github.com/VinAIResearch/PhoWhisper) | [HF VinAI PhoWhisper](https://huggingface.co/vinai) | BSD-3-Clause project. citeturn14search5 | Vietnamese-specialized Whisper fine-tunes. | Strongest interesting specialist for Vietnamese accents; trained from substantial diverse Vietnamese speech. citeturn14search0turn14search4 | Depends on base/small/medium variant. | Needs target-box benchmark. | Convertible in principle through standard Whisper/OpenVINO toolchains. | **Convertible to CTranslate2**, but not a zero-change replacement and not the right one-model answer for fully English child replies. |
| **Vietnamese wav2vec2 base 250h** | model/runtime through Transformers | [HF](https://huggingface.co/nguyenvulebinh/wav2vec2-base-vietnamese-250h) | **CC-BY-NC-4.0.** citeturn14search2 | Vietnamese only. | Vietnamese specialist, but no English/mixed capability and no reason to accept the licence compromise. | Base-sized model, relatively light. | Likely fast enough, but irrelevant. | Export possible. | **No.** |
| **NVIDIA Parakeet CTC 0.6B Vietnamese-English CS** | [NeMo](https://github.com/NVIDIA/NeMo) / [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) | [HF](https://huggingface.co/nvidia/parakeet-ctc-0.6b-Vietnamese) | NVIDIA Open Model License, redistribution allowed subject to terms. citeturn19search0 | **Explicit Vietnamese-English code-switch ASR**, FastConformer CTC, about 600M parameters. citeturn18view0 | Very interesting challenger for Vietnamese-dominant classroom code-switch. NVIDIA discussion, however, cautions that its English ability is oriented toward English occurring in Vietnamese/code-switch contexts rather than arbitrary full English audio. citeturn15search2turn16search1 | `.nemo` checkpoint alone is about **2.44 GB**, before runtime. citeturn16search3 | No official cheap-Intel 3s figure that I would use for a product decision. | No official OpenVINO path; NeMo-Speech.cpp provides local CPU/GGML-style deployment paths. citeturn16search4turn16search5 | **No**, new runtime adapter. |

The **OpenVINO result is particularly telling**. On the same published small-model CPU comparison, whisper.cpp with OpenVINO took 1m45s while faster-whisper INT8 took 1m42s. fileciteturn22file0L2-L2 That is not evidence that OpenVINO is bad, it is evidence that **Bright should not rewrite an already-working faster-whisper service merely to acquire an OpenVINO badge**. CTranslate2 INT8 is already delivering Intel CPU performance in the right class.

The change from `small.en` to `small` matters more than the runtime change. OpenAI documents `small.en` and `small` as separate English-only and multilingual variants, both at 244M parameters. fileciteturn26file0L2-L2 Bright therefore gets Vietnamese capability without moving up a model size.

For mixed speech, **do not run a language detector first and then force the entire recording to `"vi"` or `"en"`**. That converts a multilingual decoder into a one-language policy. Instantiate the multilingual model and leave `language=None` for the request. Whisper still produces a dominant-language estimate, but the transcript vocabulary is multilingual. This does not guarantee perfect intra-utterance switching, particularly from young speakers, so the mixed-child acceptance corpus is non-negotiable. Whisper itself is designed as a single multilingual speech-recognition and language-identification model rather than a pipeline of separate language ASRs. fileciteturn26file0L2-L2

**Parakeet is the model I would keep in the lab as challenger B.** It is unusually relevant because NVIDIA specifically trained a Vietnamese-English code-switch checkpoint. citeturn18view0 But NVIDIA's own discussion about incomplete arbitrary-English coverage is enough to disqualify it as Bright's default when a child may answer entirely in English. citeturn15search2turn16search1

## Recommended Bright architecture

### TTS path

Run **exactly one resident VieNeu v3 Turbo ONNX engine** inside `services/speech`. Do not classify the sentence as Vietnamese or English. Hand the original UTF-8 line directly to VieNeu's bilingual normalization/G2P path. The project's own `phonemize_text()` describes its input as a "Vietnamese/bilingual text string", and the public TTS API resolves one speaker embedding/reference-code pair before chunk synthesis. fileciteturn19file0L2-L2 fileciteturn30file0L2-L2

Keep the UI's current `voice: "en"` working. Inside `services/speech`, treat legacy names as aliases:

```text
en      -> bright
vi      -> bright
bright  -> Minh Đức     # or the preset selected after listening tests
```

That removes the existing hardcoded-`en` failure without forcing a Stage/UI migration. The "voice" now means **teacher identity**, not language.

For the latency requirement, use `infer_stream()`, not `infer()`. The current implementation explicitly prefers its engine's native frame-level streaming path and yields sub-waveforms as soon as they become available. fileciteturn30file0L2-L2 `POST /audio/speech` should therefore send a WAV/PCM streaming response, and Stage should begin playback after the header plus the first usable PCM frame rather than waiting for the entire 1-to-2-sentence waveform.

This distinction is critical:

```text
Bad:
say decided
  -> synthesize entire 5 s waveform
  -> HTTP response finishes
  -> Stage begins playback

Good:
say decided
  -> first TTS frames
  -> HTTP chunk reaches Stage
  -> Stage begins playback
  -> remaining frames generated ahead of playback
```

The latter is the architecture capable of meeting `<800 ms`. An RTF below one alone is not enough if the API buffers the whole response.

Use a **fixed preset voice**, not runtime voice cloning. Current v3 Turbo presets already contain their 192-dimensional speaker embeddings and pre-encoded reference codes, so normal TTS does not need to run the speaker encoder or encode a reference WAV. fileciteturn13file0L2-L2 This saves CPU, reduces dependencies and, more importantly, eliminates a whole category of voice-consent and sample-licence problems.

### ASR path

Keep the current faster-whisper process, replace its model path:

```text
before:
faster-whisper / small.en / CPU

after:
faster-whisper / small multilingual / CPU INT8
```

Load it once:

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    "/opt/bright/models/asr/faster-whisper-small",
    device="cpu",
    compute_type="int8",
    cpu_threads=6,   # benchmark 4/6/8 on the actual box
    num_workers=1,
)
```

faster-whisper officially supports CPU INT8 and local model paths; its model-size shortcuts simply auto-download equivalent CTranslate2 models. fileciteturn22file0L2-L2

For a 1-to-4-second classroom request I would start with:

```python
segments, info = model.transcribe(
    wav_path,
    language=None,                  # critical: do not force vi or en
    task="transcribe",
    beam_size=1,                    # latency first
    temperature=0.0,
    vad_filter=True,
    vad_parameters={
        "min_silence_duration_ms": 250,
    },
    condition_on_previous_text=False,
)

text = "".join(segment.text for segment in segments).strip()
```

faster-whisper integrates Silero VAD and allows the silence parameters to be changed per call. fileciteturn22file0L2-L2 `condition_on_previous_text=False` is appropriate for independent child turns, where carrying hypotheses from an earlier turn would create more risk than benefit.

Do **not** make ASR wait for a cloud fallback. An optional research-only cloud comparator can asynchronously score recorded benchmark clips in development, but classroom production must complete with the local transcript.

The speech services are naturally complementary in CPU scheduling. Teacher TTS and child ASR usually alternate rather than contend continuously. Prewarm both models at process startup, cap each runtime's CPU thread count rather than letting either seize every logical core, and benchmark with Chromium and Core running. The likely failure on a cheap box is not raw model size, it is p95 latency caused by thread contention, thermal throttling or memory pressure while the rest of Bright is active.

## Exact model acquisition

### VieNeu-TTS v3 Turbo

The current source snapshot is v3.2.5 at commit `54f42abf4460e68aac79c985b9446557c2180f2f`. fileciteturn33file0L2-L2 Its CPU package is deliberately torch-free and declares `sea-g2p==0.8.4`, ONNX Runtime, NumPy, SoundFile, SoXR and tokenizers among its core dependencies. fileciteturn31file0L2-L2

The internal ONNX engine expects these v3 files: `vieneu_prefill.onnx`, `vieneu_decode_step.onnx`, `vieneu_acoustic_cached.onnx`, `vieneu_backbone_shared.data`, `vieneu_v3_heads.npz`, `config.json`, and `tokenizer.json`. It expects the MOSS codec files listed below as a separate set. fileciteturn11file0L2-L2 No ONNX conversion is needed because the producer now publishes the INT8 graphs directly.

```bash
# Assumption: run from the Bright repository root.
export BRIGHT="$PWD"

mkdir -p \
  "$BRIGHT/third_party" \
  "$BRIGHT/models/tts/vieneu-v3-turbo/onnx_int8" \
  "$BRIGHT/models/tts/vieneu-v3-turbo/codec" \
  "$BRIGHT/models/asr"

python3 -m venv "$BRIGHT/.venv-speech"
source "$BRIGHT/.venv-speech/bin/activate"

python -m pip install --upgrade pip
python -m pip install "huggingface_hub[cli]"

# clone
git clone https://github.com/pnnbao97/VieNeu-TTS.git \
  "$BRIGHT/third_party/VieNeu-TTS"

git -C "$BRIGHT/third_party/VieNeu-TTS" checkout \
  54f42abf4460e68aac79c985b9446557c2180f2f

# Install the exact vendored source.
python -m pip install -e "$BRIGHT/third_party/VieNeu-TTS"
```

Download **only the INT8 backbone**, not the fp32/PyTorch weights:

```bash
# download weights: VieNeu v3 Turbo INT8 ONNX
hf download pnnbao-ump/VieNeu-TTS-v3-Turbo \
  onnx_int8/config.json \
  onnx_int8/tokenizer.json \
  onnx_int8/vieneu_prefill.onnx \
  onnx_int8/vieneu_decode_step.onnx \
  onnx_int8/vieneu_acoustic_cached.onnx \
  onnx_int8/vieneu_backbone_shared.data \
  onnx_int8/vieneu_v3_heads.npz \
  --local-dir "$BRIGHT/models/tts/vieneu-v3-turbo"
```

The published `onnx_int8` directory is about 165 MB in the current model repository. citeturn24search15

Then fetch the exact codec files the current ONNX engine enumerates:

```bash
# download weights: MOSS Audio Tokenizer Nano ONNX
hf download OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX \
  moss_audio_tokenizer_decode_full.onnx \
  moss_audio_tokenizer_decode_shared.data \
  moss_audio_tokenizer_decode_step.onnx \
  codec_browser_onnx_meta.json \
  moss_audio_tokenizer_encode.onnx \
  moss_audio_tokenizer_encode.data \
  --local-dir "$BRIGHT/models/tts/vieneu-v3-turbo/codec"
```

The current engine's `_CODEC_FILES` constant includes all six of those assets, including the encoder even though preset-voice inference principally needs decoding. fileciteturn11file0L2-L2 Shipping exactly what the pinned implementation requests is safer than trying to outsmart its loader.

Also vendor the fixed preset metadata so Bright's release artifact contains the complete teacher-voice definition:

```bash
cp \
  "$BRIGHT/third_party/VieNeu-TTS/src/vieneu/assets/voices_v3_turbo.json" \
  "$BRIGHT/models/tts/vieneu-v3-turbo/voices_v3_turbo.json"

sha256sum \
  "$BRIGHT/models/tts/vieneu-v3-turbo/onnx_int8/"* \
  "$BRIGHT/models/tts/vieneu-v3-turbo/codec/"* \
  "$BRIGHT/models/tts/vieneu-v3-turbo/voices_v3_turbo.json" \
  > "$BRIGHT/models/tts/vieneu-v3-turbo/SHA256SUMS"
```

There is one **important offline gotcha in v3.2.5**. The low-level `OnnxV3LiteEngine` already accepts both `onnx_dir` and `codec_dir`, but the high-level `V3TurboVieNeuTTS` wrapper passes `onnx_dir` while not exposing `codec_dir`. Without intervention, that wrapper can ask `huggingface_hub` for the codec repository on first initialization. fileciteturn11file0L2-L2 fileciteturn13file0L2-L2

For a product that **must boot with no network**, I would carry this tiny patch in Bright's vendored copy instead of depending on a pre-populated Hugging Face cache:

```diff
diff --git a/src/vieneu/v3turbo.py b/src/vieneu/v3turbo.py
--- a/src/vieneu/v3turbo.py
+++ b/src/vieneu/v3turbo.py
@@
         onnx_repo: Optional[str] = None,
         onnx_dir: Optional[str] = None,
+        codec_dir: Optional[str] = None,
         precision: str = "int8",
@@
                 onnx_repo=onnx_repo,
                 onnx_dir=onnx_dir,
+                codec_dir=codec_dir,
                 onnx_subfolder=onnx_subfolder,
                 threads=threads,
```

After applying it, initialization is completely explicit:

```python
from pathlib import Path
from vieneu import Vieneu

ROOT = Path("/opt/bright/models/tts/vieneu-v3-turbo")

tts = Vieneu(
    mode="v3turbo",
    backend="onnx",
    backbone_repo=str(ROOT),
    onnx_dir=str(ROOT / "onnx_int8"),
    codec_dir=str(ROOT / "codec"),
    precision="int8",
    threads=6,
)

# Existing package preset. Pick the final Bright voice after listening tests.
audio = tts.infer(
    "Chào con! Look, this is the market. Chợ đó.",
    voice="Minh Đức",
)
```

This patch is preferable to preserving a fake online-looking HF cache in production. It makes the filesystem itself the source of truth.

The expected TTS layout is:

```text
Bright/
├── models/
│   └── tts/
│       └── vieneu-v3-turbo/
│           ├── SHA256SUMS
│           ├── voices_v3_turbo.json
│           ├── onnx_int8/
│           │   ├── config.json
│           │   ├── tokenizer.json
│           │   ├── vieneu_prefill.onnx
│           │   ├── vieneu_decode_step.onnx
│           │   ├── vieneu_acoustic_cached.onnx
│           │   ├── vieneu_backbone_shared.data
│           │   └── vieneu_v3_heads.npz
│           └── codec/
│               ├── moss_audio_tokenizer_decode_full.onnx
│               ├── moss_audio_tokenizer_decode_shared.data
│               ├── moss_audio_tokenizer_decode_step.onnx
│               ├── codec_browser_onnx_meta.json
│               ├── moss_audio_tokenizer_encode.onnx
│               └── moss_audio_tokenizer_encode.data
└── third_party/
    └── VieNeu-TTS/
```

Finally, prove there is no hidden cloud dependency:

```bash
export HF_HUB_OFFLINE=1

# Start Bright services/speech with the network physically disabled
# or blocked by the classroom image firewall.
# It must initialize TTS and synthesize successfully.
```

### faster-whisper small multilingual

The current faster-whisper `master` resolves to commit `ed9a06cd89a93e47838f564998a6c09b655d7f43` in the checked repository. fileciteturn32file0L2-L2 Its code is MIT. fileciteturn23file0L2-L2

```bash
export BRIGHT="$PWD"
source "$BRIGHT/.venv-speech/bin/activate"

# clone
git clone https://github.com/SYSTRAN/faster-whisper.git \
  "$BRIGHT/third_party/faster-whisper"

git -C "$BRIGHT/third_party/faster-whisper" checkout \
  ed9a06cd89a93e47838f564998a6c09b655d7f43

python -m pip install -e "$BRIGHT/third_party/faster-whisper"

mkdir -p "$BRIGHT/models/asr/faster-whisper-small"
```

Download the pre-converted CTranslate2 checkpoint:

```bash
# download weights
hf download Systran/faster-whisper-small \
  config.json \
  model.bin \
  preprocessor_config.json \
  tokenizer.json \
  vocabulary.json \
  --local-dir "$BRIGHT/models/asr/faster-whisper-small"
```

**No ONNX/OpenVINO conversion is required for the winner.** The whole point of faster-whisper is that it runs the Whisper model through CTranslate2, including INT8 CPU inference. fileciteturn22file0L2-L2

The expected directory is:

```text
Bright/
└── models/
    └── asr/
        └── faster-whisper-small/
            ├── config.json
            ├── model.bin
            ├── preprocessor_config.json
            ├── tokenizer.json
            └── vocabulary.json
```

Prewarm it at `services/speech` startup:

```python
from faster_whisper import WhisperModel

asr = WhisperModel(
    "/opt/bright/models/asr/faster-whisper-small",
    device="cpu",
    compute_type="int8",
    cpu_threads=6,
    num_workers=1,
)
```

The official faster-whisper implementation supports CPU INT8, and its published `small` CPU benchmark is the 1,477 MB / 1m42s result described above. fileciteturn22file0L2-L2

A useful deployment invariant is:

```text
no "small.en"
no language detector ahead of ASR
no forced language="vi"
no forced language="en"
```

The model selection and request configuration should stay multilingual end to end.

## Endpoint proof and rollout gates

Assuming Bright's existing `/audio/speech` route uses its current OpenAI-style `input` / `voice` body, **keep `voice:"en"` valid as a backward-compatible alias for the new bilingual teacher**. That means the currently hardcoded UI does not block deployment.

### TTS smoke tests

English:

```bash
curl --fail-with-body -sS -N \
  -X POST http://127.0.0.1:8000/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Look carefully. This is the market.",
    "voice": "en",
    "response_format": "wav"
  }' \
  --output /tmp/bright-en.wav
```

Vietnamese, through the **same voice value and same model**:

```bash
curl --fail-with-body -sS -N \
  -X POST http://127.0.0.1:8000/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Chào con! Đây là cái chợ.",
    "voice": "en",
    "response_format": "wav"
  }' \
  --output /tmp/bright-vi.wav
```

Mixed, the actual acceptance case:

```bash
curl --fail-with-body -sS -N \
  -X POST http://127.0.0.1:8000/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "Chào con! Look, this is the market. Chợ đó.",
    "voice": "en",
    "response_format": "wav"
  }' \
  --output /tmp/bright-mixed.wav
```

The current VieNeu streaming implementation yields frame-level sub-waveforms rather than requiring the full utterance to finish first. fileciteturn30file0L2-L2 For Bright's metric, instrument **`say_decision_timestamp -> Stage first PCM played`**, not merely the time taken by the Python `infer_stream()` generator.

### ASR smoke tests

Use three real microphone recordings in the repository, ideally from the target classroom microphone. Do not use TTS output as the final ASR benchmark because synthetic speech understates the actual child/noise problem.

```text
tests/audio/
├── child-en.wav
├── child-vi.wav
└── child-mixed.wav
```

English:

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:8000/audio/transcriptions \
  -F 'file=@tests/audio/child-en.wav;type=audio/wav' \
  -F 'model=small'
```

Vietnamese:

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:8000/audio/transcriptions \
  -F 'file=@tests/audio/child-vi.wav;type=audio/wav' \
  -F 'model=small'
```

Mixed:

```bash
curl --fail-with-body -sS \
  -X POST http://127.0.0.1:8000/audio/transcriptions \
  -F 'file=@tests/audio/child-mixed.wav;type=audio/wav' \
  -F 'model=small'
```

The service should **not require a `language` multipart field**. If one is present for backward compatibility, an empty/`auto` value should resolve to `None`, not to Vietnamese or English.

Before a 40-million-child-scale image is frozen, I would make the following release gates hard failures rather than "nice to have":

| Gate | Pass criterion |
|---|---|
| TTS offline boot | Cold machine boots and synthesizes with WAN physically unavailable. |
| TTS first audio | `say` decision to **first PCM actually played by Stage** is `<800 ms` at p95 after model prewarm. |
| TTS sustained generation | RTF remains below 1 for representative 1-to-2-sentence lines, so synthesis does not fall behind playback. |
| TTS mixed identity | Vietnamese and English portions are judged to be the **same teacher**, with no obvious speaker reset at switches. |
| TTS pronunciation | Test at least hundreds of curriculum phrases, especially English words embedded in Vietnamese syntax, Vietnamese names, numbers, market/classroom vocabulary and punctuation boundaries. |
| ASR latency | End of upload to transcript returned to Core is `<2 s` p95 for 1-to-4-second recordings while Chromium and Core are active. |
| ASR corpus | Include real Vietnamese children, full English replies, Vietnamese replies and genuinely mixed replies, plus fan/projector/classroom noise. |
| ASR metrics | Track ordinary WER/CER **and curriculum-keyword recall**. A transcript with acceptable WER can still be pedagogically useless if it misses the target word being assessed. |
| Memory | Keep both speech models resident during the test. Test simultaneously with the planned Gemma, Chromium and Core workload, not in an isolated speech benchmark. |
| Network | Packet capture/firewall test shows zero model/API network dependence after installation. |
| Licence bundle | Ship Apache/MIT notices, model card snapshot, exact commit IDs, model SHA-256 manifest and dependency licences in the classroom image. |

The TTS acceptance set should deliberately attack the code-switch boundary:

```text
"Đây là a market."
"Con nói: market."
"Market nghĩa là chợ."
"Chào con! Look at the red apple."
"Đây là banana, quả chuối."
"Good job! Con làm đúng rồi."
"Không phải cat. Look again, it is a dog."
"Ba quả apples. How many apples?"
```

This catches the failure mode hidden by ordinary monolingual demos: a model can sound excellent in Vietnamese and excellent in English while becoming unstable, changing accent, inserting pauses, or mangling G2P exactly where the language switches.

For ASR, make the mixed corpus similarly adversarial:

```text
"Con thấy a dog."
"Đây là market."
"Em chọn red."
"Không, it's a cat."
"Ba apples."
"I don't know cô ơi."
"Con think là two."
```

Whisper's multilingual architecture makes these plausible with one model, but neither its general multilingual training nor faster-whisper's speed benchmark proves performance on young Vietnamese children's intra-sentence code-switching. fileciteturn26file0L2-L2 That is the one area where Bright's own recordings matter more than any model card.

**Final recommendation:** ship a prototype branch with **VieNeu-TTS v3 Turbo v3.2.5, ONNX INT8** and **faster-whisper `small` multilingual INT8**. Pin both source commits and vendor every weight. VieNeu is the only surveyed TTS I would currently put through serious Bright acceptance testing because it addresses the actual semantic whole of the problem: one Vietnamese teacher identity that can naturally carry English instructional targets inside the same sentence. faster-whisper `small` is the opposite kind of choice, mature and conservative: Bright already owns the integration, multilingual `small` fixes the English-only mistake, its licence is clean, and its published CPU performance leaves substantial room under the two-second ASR budget. citeturn25search4turn25search6 fileciteturn22file0L2-L2

**Explicitly out of the production design:** ElevenLabs, Google Speech, Azure Speech and OpenAI speech APIs as primary paths; MMS-TTS and XTTS-v2 because Bright's stated redistribution/licensing rule rejects their non-commercial restrictions; Hermes-native TTS/STT; AIRI's streaming TTS server; two-Piper-voice sentence stitching; and any deployment that silently contacts Hugging Face on first classroom boot.