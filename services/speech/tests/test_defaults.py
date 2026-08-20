"""What this service ships with when nobody configures it.

A default is a decision nobody re-reads, so it is the one place a contradiction
can sit for days without anyone noticing. One did: the resident ASR model
defaulted to `small.en` -- English-only weights -- while the whole language
clamp beneath it existed to choose between `en` and `vi`. The child's
Vietnamese could not be transcribed by construction, and the failure looked
like poor accuracy rather than a wrong file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from asr import parse_languages


def test_a_bilingual_deployment_does_not_default_to_monolingual_weights() -> None:
    """The rule, not the model name -- and the two settings against each other.

    `.en` checkpoints contain one language. If the deployment declares more
    than one, resident weights that can only hear one of them are not a tuning
    choice: they can never produce the other. An English-only appliance
    declares ASR_LANGUAGES=en and is then free to run `.en` weights, and this
    guard steps aside for it. What it refuses is the contradiction -- a
    deployment claiming two languages while shipping one.
    """
    languages = parse_languages(app.ASR_LANGUAGES)
    if len(languages) < 2:
        return  # a monolingual deployment may legitimately ship .en weights
    assert not app.WHISPER_MODEL.endswith(".en"), (
        f"ASR_LANGUAGES declares {languages} but the default resident model is "
        f"{app.WHISPER_MODEL!r}, which has no {languages[1]!r} in it at all. "
        "Forcing a language the weights do not contain returns silence, not a "
        "worse transcript -- measured empty on 'Con không biết'."
    )


def test_the_default_model_is_one_this_service_knows_and_has_on_disk() -> None:
    """local_files_only means an unknown or absent name fails at demo time.

    The failure is a mute classroom, and it happens on the first utterance --
    not at boot, where somebody would see it.
    """
    assert app.WHISPER_MODEL in app.KNOWN_MODELS, (
        f"{app.WHISPER_MODEL!r} is not in KNOWN_MODELS, so it would be refused "
        "rather than loaded"
    )
    assert app.WHISPER_MODEL in app._available_models(), (
        f"{app.WHISPER_MODEL!r} is known but its snapshot is not in "
        f"{app.WHISPER_DIR}; the service would come up deaf"
    )
