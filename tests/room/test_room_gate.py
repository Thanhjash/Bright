from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import room_test  # noqa: E402
from room_test import Row, load_cases, summarise  # noqa: E402


def test_one_false_accept_in_one_condition_fails_release_even_if_authoring_disagrees():
    row = Row(
        model="future-provider",
        condition="real",
        case="q/trap",
        source="real",
        say="not cat",
        intent="wrong",
        oracle="correct",  # authoring defect, still unsafe to release
        heard="cat",
        outcome="correct",
    )
    report, passed, _ = summarise([row], ["future-provider"], systematic_k=2)
    assert passed is False
    assert "FAIL" in report


def test_checked_in_corpus_declares_provenance_license_and_limitations():
    corpus = json.loads((HERE / "cases.json").read_text())["corpus"]
    assert corpus["id"] and corpus["version"] >= 1
    assert corpus["license"] == "CC0-1.0"
    assert corpus["provenance"]
    assert any("child" in item.lower() for item in corpus["limitations"])


def test_filename_convention_cannot_bypass_real_recording_manifest(
    tmp_path: Path, monkeypatch, capsys
):
    wav_dir = tmp_path / "wavs"
    wav_dir.mkdir()
    (wav_dir / "q_animal__wrong_dog__unmanifested.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(room_test, "WAV_DIR", wav_dir)
    cases = load_cases(HERE / "cases.json")
    assert room_test.load_real_cases({case.key: case for case in cases}) == []
    assert "no manifest/consent metadata" in capsys.readouterr().err
