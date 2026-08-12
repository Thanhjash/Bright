# Second opinion — five days out

**Date:** 2026-08-11
**Author:** external second opinion (Fable), asked to disagree where disagreement is useful
**Read first:** [north star](../1-vision/north-star.md) · [state of the project](../4-build/state-of-the-project.md) · [tracker](../4-build/tracker.md) · [architecture](../3-design/architecture.md)
**Context:** 5 build days, then 7 buffer days, then a judged Intel × UN presentation.

---

## 0. The one-paragraph verdict

You have built the right floor and proved it honestly. The danger in the next five days is not that you build too little — it is that you build the wrong five things. The demo you will actually give is a *composition* of parts that have each passed their own gate and have **never run together in one session**, in a codebase whose four worst bugs were all silent seam bugs. And the single claim that decides an Intel competition — *it runs locally, offline, on Intel silicon* — is currently false: the brain is a hosted API. Fix the composition and the locality. Cut nearly everything else.

---

## 1. What to build, what to refuse

### Build, in this order

| Day | Build | Why it wins |
|---|---|---|
| 1–3 | **Local model behind `TeacherAgent`** — timeboxed, go/no-go decided by day 2–3 | The north star already says it: an Intel entry that calls a cloud API has thrown away its own strongest claim. Get *anything* serving locally first — your own architecture doc names llama.cpp as the fallback if OVMS grammar support is unverified, and "runs offline on Intel hardware" is true either way. OpenVINO is the bonus claim if it lands; do not let "OpenVINO specifically" block "local at all." If local E4B picks bad actions, NS-1 already saves you: **DEGRADED mode on a local model is a stronger Intel story than FULL mode over WiFi** |
| 1–2 | **The demo script, written as a document** — then the one demo lesson it specifies, authored end to end from the **six working activity types only** | The script is the spec. Authoring the lesson against it measures SP-0 — your own #1 risk, untouched — as a byproduct. Two birds, one artifact |
| 2–3 | **Agent initiative via checkpoints** — Core emits `activity.ended` / timer / silence checkpoints that *trigger* an agent turn; the agent starts the session and closes it | This is the whole "reactive vs autonomous" gap at demo scale, and it is orchestration, not architecture. The runner already has timers and stage transitions; give the agent standing to act on them |
| 3–4 | **Mask the agent's latency** — reflex-tier acknowledgment (warm Piper is 100–190 ms; a canned backchannel fires instantly), and the hard rule: **the agent's output is commentary and steering, never a gate on advancement** | See §2. This is the difference between a demo that breathes and a demo with 10-second holes in it |
| 4–5 | **Run the composed pipeline daily**: voice in → agent → speech out → avatar, one session, kill-switch included | The seams are where your bugs live. You wrote that yourself, three times |
| slack only | Make "fallback language is per-lesson configuration" literally true (it is already in the frontmatter schema). No i18n system | One honest sentence for a UN judge, at config-change cost |

**Hard feature freeze at day 5.** The seven buffer days are rehearsal, story, and the avatar swap *only if drop-in*. Your own §8 caution says this team polishes what works; make the freeze a rule, not a mood.

### Refuse to build

| Cut | Why |
|---|---|
| **All five placeholder activities** — matching, sentence builder, pronunciation, roleplay, explore *as code* | New content, not new scene kinds, inside 5 days. Author EXPLORE from existing primitives — image + narration + choice *is* penguin → Antarctica → ice. The philosophy survives; the code sprint dies |
| **Pronunciation scoring** | Infeasible in 5 days, and your own north star bans uncalibrated numbers. Scoring real children with an uncalibrated model at a UN event is worse than absence. Say to judges: "we refuse to show a fake percentage" — that refusal is a *good* story |
| **Perception, identity fusion, mic arrays** | Not started. Obviously out |
| **Class-scale memory / 30-student turn model** | Single-student greet-by-name is enough for the demo. The class-scale model is real Phase-3 architecture (see §4) |
| **Hermes migration** | `DirectAgent` works and NS-4 is the reason you can defer this forever. Never swap runtimes the week of a competition |
| **Any further polish on the lesson player** | It is done. Your state-of-the-project says the drift risk is exactly this |
| **The full avatar re-rig** | Not in build week. See §5 |

One housekeeping line: **rotate the MiMo API key (P4) before any public demo.** It has been through a chat transcript and the tracker says so.

---

## 2. The biggest risk you are not seeing

**You have verified every latency row and never summed the column.**

```
child speaks → transcript      3.2–4.4 s
agent turn                     2.7–5.8 s
transition after an answer     2–4   s
                               ─────────
felt silence after a child speaks:  ~8–14 seconds
```

Each number passed its own gate, so each looks fine in its own table row. Composed, they mean that after every spoken answer the room holds **eight to fourteen seconds of dead air** — an eternity for children and an eternity for judges. This is the same shape as your §4 lesson (293 green unit tests, four seam bugs): every component measured, the composition never felt.

The cruel corollary: **FULL mode currently feels worse than OFFLINE mode.** The reflex tier answers a tap in 5–11 ms; the intelligence layer answers a voice in ten seconds. Your differentiating layer *degrades* the felt product, and nobody inside can see it because everyone inside reads the rows, not the sum.

And it is not hypothetical, because of the adjacent fact in your own state-of-the-project §3: **the agent and the voice have never run in the same session.** The demo path — child speaks, agent decides, avatar answers — is precisely the seam that has never been composed. In this codebase, unrun seams are where the silent bugs are.

Mitigation is cheap and already in your design vocabulary:

1. Reflex-tier acknowledgment the instant STT starts: avatar turns, "Hmm!" — canned, 100–190 ms.
2. The rule above: the agent never gates advancement. Grading and reveal stay reflex-speed; the agent's line arrives when it arrives, as color.
3. Compose the full pipeline this week and run it every day of buffer week.

**The named second risk:** you are producing evidence for engineers — measurements, gates, integration tests — while UN judges will score pedagogy, child privacy, deployment cost, and a plan. Your architecture doc says a written privacy policy is *required* and it does not exist. A judge will ask about cameras and microphones pointed at children. Write the one-page policy in buffer week; it costs an afternoon and its absence costs the room.

---

## 3. The competition: what actually changes the outcome

Judges see thirty minutes. They will remember one moment. You already own the best possible one:

**Mid-lesson, on stage, kill the agent process — announce it first — and the class does not stop.** WiFi visibly off the entire time. Every other team's demo dies when the model dies; yours provably does not, live, in front of them. NS-1 is not just your engineering principle, it is your theater. Rehearse those 30 seconds like a magic trick.

The rest, in priority order:

1. **Zero network dependency on the primary demo path.** Not "local with hosted backup" — the reverse is a self-inflicted wound at an Intel event, and venue WiFi is where demos go to die. Demo on the dev laptop with the radio off; your own doc rightly forbids picking production hardware early. **But confirm on day 1 that the demo machine is actually Intel silicon** — nothing in the docs says so, and "local inference on Intel" quietly breaks on an AMD laptop. If it isn't, sourcing an Intel machine is a day-1 errand, not a buffer-week one.
2. **Story order: floor, then ceiling.** Lead with the child and the 40 million. Show the class running with zero AI. *Then* bring the agent in: it greets Minh by name, scaffolds instead of answering, distinguishes a silent child from a wrong one. "Everything you just saw survives the AI dying — watch." The narrative is the architecture.
3. **Scripted, rehearsed, drilled.** The facilitator knows every recovery path. Nothing is typed live. The demo lesson uses only the six activity types that work.
4. **Are you optimising for the right thing?** Almost. You are optimising for *true* — measurements, gates — and judges experience *felt*: the pause, the voice, the face. The 10/10 integration tests are invisible in the room; the ten-second silence is not. Buffer week goes to rehearsal and felt-experience, not features.

---

## 4. Player with garnish, or teacher?

You asked for the honest answer, so: **today it is a lesson player with an advisory LLM at the branch points.** The agent is consulted after Core has graded, chooses among options Core computed, and goes silent until summoned again. Core owns the arc; the agent decorates it. Your suspicion is correct as a description of *what is built*.

But it is wrong as an indictment of *the architecture*, and the distinction matters this week:

- The constrained-`available_actions` design is not the reason the agent isn't a teacher — it is the only reason a 4.5B model at Tau2 42.2 can ever *be* one. N1 proved the model never invents actions and the scaffolding policy survives into behaviour. That is the hard part, and it works.
- What is missing is **initiative**, and initiative is an orchestration change, not a rearchitecture: who calls the agent, and when. Today the answer is "the grading path, once." Make it "Core's checkpoints — session start, activity end, timers, silence — and the agent owns the session loop from greeting to close." Same tools, same contract, same boundaries. Days, not weeks.
- **Do not answer the "garnish" anxiety by widening the model's authority** — free-form control, more tools, DOM access. That road violates NS-2/NS-3 and dies on E4B's 42.2. Autonomy comes from *more occasions to decide* and *memory across decisions*, never from bigger decisions.

The one genuine architectural gap for autonomy is the one your north star already names: the whole state and turn model is **single-student**, and a teacher of thirty is an attention-allocation problem — who to call on, who has gone quiet. That is real Phase-3 architecture work. Defer it past the competition, explicitly, and say so on the slide; naming it is more credible than hiding it.

So: mislabelled today, correctly architected for tomorrow, and the relabelling costs a checkpoint loop, not a rewrite.

---

## 5. The avatar licence

The tracker's P1 analysis is right about development and wrong to be relaxed about distribution, for one specific reason:

**The ¥10M small-business exemption attaches to the publishing entity.** Distribution through a UN programme means the publishers are ministries, large NGOs, and UN bodies — exactly the entity class the exemption does not cover. And that is only the *runtime*; the sample model (Hiyori) is Live2D Inc. material that is **not yours to redistribute inside a product at all**, at any revenue, including zero. "Donated" is not a defense — donation at scale *is* distribution. A humanitarian product presented at a UN programme containing a character you may not ship is the kind of exposure that surfaces at exactly the wrong moment.

What to do, concretely:

| When | Action |
|---|---|
| Build week | Nothing. Do not spend build days here |
| The demo | Demo with Hiyori — development and demonstration use is fine — with one line in the deck: *"placeholder character; production character is commissioned, VRM format, fully owned"* |
| Buffer week | Swap only if a genuinely drop-in, cleanly licensed model exists. No porting, no re-rigging, no risk to the demo |
| The deck | Commit publicly to **VRM + an owned character**, with a cost line. MIT runtime, open format, zero licence exposure, and VRoid makes iteration cheap — your tracker already reached this conclusion; promote it from tracker footnote to stated plan |

And note that the licence question and the design question converge on the same answer. Even if Hiyori were public domain, a Japanese anime sample character is not what an AI teacher should look like to a Vietnamese schoolchild — or to a child in any of the other countries the UN framing obliges you to mean. Replace it because it is not yours, and replace it because it is not *theirs*. Saying that out loud to judges — "the character is the one thing on screen we don't own yet, and here is the brief for the one we will" — is a strength, not a confession.

---

## 6. The five days, on one line each

```
Day 1   Demo script written. Local model spike starts. Key rotated.
        Confirm the demo machine is Intel silicon.
Day 2   Demo lesson authored from the script (SP-0 measured for free).
        Local model go/no-go decided.
Day 3   Checkpoint loop: agent starts, paces, and ends the session.
Day 4   Latency masking. Full composed pipeline runs once, end to end.
Day 5   Composed pipeline again. Feature freeze — hard.
Buffer  Rehearse daily. Privacy one-pager. Deck. Avatar swap iff drop-in.
        Kill-the-agent moment drilled until it is boring.
```

The floor is real, the measurements are honest, and the architecture has survived contact with implementation better than most do. Spend the five days making the one demo that composes it all run offline on Intel silicon, and the seven days making it impossible to fail in the room. Everything else is after the competition.
