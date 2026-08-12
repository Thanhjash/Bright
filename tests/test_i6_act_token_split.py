"""I6 — an ACT token split across two SSE chunks is never spoken. RELEASE GATE.

PROTOCOL §5.4.1 calls tail retention "the single most common bug in
reimplementations", and the failure is inaudible in every place people usually
look: the subtitle can be clean while the room hears the token read out, or the
token can be swallowed whole and the avatar's face never move.

So this test asserts on both ends of the pipeline:

* **nothing token-shaped reaches the synthesiser** — the fake speech service
  records every `POST /audio/speech`, and that is by definition what the class
  would have heard;
* **the emotion still lands** — a parser that simply deleted everything
  suspicious would pass the first assertion and break the avatar.

And it does so against the module instance the running app loaded, resolved
from the page's own request list. A probe that imports the same file by a
different URL gets a different module instance and cheerfully reports a broken
patch as working; that has already happened once on this project.
"""

from __future__ import annotations

import json

import pytest

from harness import llm_script as script
from harness import run_scenario

pytestmark = [pytest.mark.browser, pytest.mark.slow]

#: Anything of this shape reaching TTS means the class heard markup.
LEAK_MARKERS = ("<|", "|>", "ACT ", "ACT{", '"emotion"', "DELAY ")


def _leaks(texts: list[str]) -> list[str]:
    return [t for t in texts if any(m in t for m in LEAK_MARKERS)]


@pytest.mark.itest(id="I6", title="ACT token split across two SSE chunks is never spoken", gate=True)
async def test_act_token_never_reaches_the_synthesiser(core, ui, tts, llm):
    # Phase C's model reply: `classroom_say` whose JSON arguments are cut in
    # half *inside* the ACT token, so the two halves are in different SSE
    # frames on the wire.
    say_text = 'Listen carefully. <|ACT {"emotion":"surprised"}|> A cat says meow!'
    args = {"text": say_text}
    raw = json.dumps(args)
    cut = raw.index("<|ACT") + 3  # mid-token
    llm.script(
        [
            script.tool_call("classroom_say", args, split_args_at=cut),
            script.text("done"),
        ],
        non_stream={"content": "ok"},
    )

    out = run_scenario(
        "i6_act_split",
        {"uiOrigin": ui.origin, "coreHttp": core.http, "ttsUrl": tts.base_url},
        timeout=300,
    )
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"

    # ── A. the parser, against the app's own module instance ─────────────
    a = out["phaseA"]
    assert not a.get("error"), f"{a['error']} (act requests seen: {a.get('actRequests')})"
    assert a["moduleUrl"], "could not resolve the ACT parser URL the app requested"
    for case in a["cases"]:
        name = case.get("name")
        assert not case.get("error"), f"{name}: {case['error']}"
        if name == "unterminated":
            assert "<|" not in case["spoken"] and "ACT" not in case["spoken"], (
                f"an unterminated token leaked into spoken text: {case['spoken']!r}"
            )
            assert case["specials"] == [], "an unterminated token was dispatched as a special"
            continue
        assert case["spoken"] == "Yes!  Well done.".replace("  ", " ") or "<|" not in case["spoken"], (
            f"{name}: token fragments leaked into spoken text: {case['spoken']!r}"
        )
        assert not any(m in case["spoken"] for m in LEAK_MARKERS), (
            f"{name}: spoken text contains markup: {case['spoken']!r}"
        )
        assert case["specials"] == ['<|ACT {"emotion":"happy"}|>'], (
            f"{name}: the token was not reassembled into one special: {case['specials']}"
        )

    # ── B. a whole payload, end to end ───────────────────────────────────
    b = out["phaseB"]
    assert b["tts"], (
        "the speech pipeline never called TTS, so 'nothing leaked' proves nothing. "
        f"store said emotion={b['emotion']!r} subtitle={b['subtitle']!r}"
    )
    assert not _leaks(b["tts"]), f"ACT markup was sent to the synthesiser: {_leaks(b['tts'])}"
    assert not _leaks([b["subtitle"]]), f"ACT markup was projected as a subtitle: {b['subtitle']!r}"
    assert b["emotion"] == "happy", (
        f"the token was stripped but its emotion never landed (avatar={b['emotion']!r}); "
        "a parser that only deletes is not a parser"
    )

    # ── C. split across two SSE frames, all the way through ──────────────
    c = out["phaseC"]
    assert c.get("turn"), f"the agent turn did not run: {c}"
    assert c["tts"], (
        "the split-token turn produced no TTS call at all — the assertion below "
        f"would be vacuous. turn={c['turn']}"
    )
    assert not _leaks(c["tts"]), (
        "a token split across two SSE frames was sent to the synthesiser: "
        f"{_leaks(c['tts'])}"
    )
    assert not _leaks([c["subtitle"]]), f"split token projected as a subtitle: {c['subtitle']!r}"
    assert c["emotion"] == "surprised", (
        f"the split token's emotion did not land (avatar={c['emotion']!r}) — either the "
        "halves were never rejoined, or the whole token was dropped"
    )

    assert not out["pageErrors"], f"uncaught errors in the page: {out['pageErrors']}"
