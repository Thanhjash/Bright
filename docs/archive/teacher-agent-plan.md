# Teacher-agent Layer 1 — cook this, not the cassette

> **Historical.** Layer 1 A–H and Layer 3 voice wiring shipped. Next cook
> is Layer 4 autonomy (no Start/Hold contract). Paste
> [HANDOFF.md](HANDOFF.md). Do not cook from this file.
>
> Doctrine: [teacher-agent-not-cassette.md](../decisions/teacher-agent-not-cassette.md),
> [north-star.md](../NORTH-STAR.md),
> [autonomous-classroom-roadmap.md](autonomous-classroom-roadmap.md).

**Layer 1 is closed.** Hermes teaches from the library. Same loop for
every unit. Text was the cheap channel. **This cook = Layer 3 voice
pipes** (Stage TTS of `say`, then ASR into `/teacher/turn`). AIRI body
is Layer 4 — keep `airi-bridge` SpeechPlayer, do not start Live2D.

## Anti-bias

`test_no_unit_pedagogy.py` fails if Core / Hermes adapter / live prompt
contain a unit answer key. Evals must not require `banana.svg`. Drive
must pass **market-food and colours** with the same driver.

## Cook order (capability — one period)

```text
A  write_board (markdown, 400/8) + read_board + show_image + play_clip   DONE
B  market-food map HOOK/INPUT/PRACTICE/EXIT + clips                      DONE
C  /learn: writing markdown, picture, clip+transcript                    DONE
D  live Hermes chat through the period; read_board before EXIT           DONE
E  H0 storage: evidence mode + SQL skill card in the teacher turn        DONE
F  BEATS teach-log + reopen summary + spoken clips                       DONE
G  colours keys table + clips; /learn honest pause; show the meant asset DONE
H  bright.3 teacher-loop patch + teacher-up + /teacher/status             DONE
I  voice: leases without lesson + speech process + Stage TTS + /learn ASR  WIRED
```

**Layer 1 closed.** Do not deepen Store B.
See [layer-1-memory-is-enough.md](../decisions/layer-1-memory-is-enough.md).
Layer 3: Stage is the only loudspeaker. `/learn` listen is Whisper → text.


`read_board` is OS state, not computer-use. Do not add scroll/click.

A–I shipped. Voice is Stage Piper + `/learn` Whisper, same 8 tools.
Do not start AIRI body / 20–40 / Gemma / FTS5 / GraphRAG here.

## Verification

```text
# conda base
python -m pytest \
  services/classroom-core/tests/test_no_unit_pedagogy.py \
  services/classroom-core/tests/test_library.py \
  services/classroom-core/tests/test_teacher_os.py \
  services/agent/tests/test_hermes.py \
  services/classroom-core/tests/test_option_b_mcp.py -q

./scripts/teacher-agent-l1.sh start
# then a live /teacher/session + turns through HOOK→EXIT
```

Capability is done when the live period uses write/show/play, `read_board` is available, and EXIT matches the board.
