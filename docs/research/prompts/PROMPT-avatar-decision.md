# Deep research prompt — the AI teacher avatar

Paste the block below into a deep-research tool. Written 2026-08-11.

Answer wanted: **which avatar format and which character** for an AI English teacher shown to Vietnamese schoolchildren on a projector — with licensing that survives commercial release.

---

```
I am building an offline AI English teacher for Vietnamese primary/secondary
schools. An animated character appears on a projector beside an interactive
whiteboard, speaks English (and Vietnamese for scaffolding), lip-syncs to
generated speech, and shows emotions. Classes are 20-40 children. The target is
under-resourced public schools; hardware is a cheap Intel box, everything runs
offline. It will eventually be sold or distributed at some scale, so licensing
must survive commercial release.

Current state: a prototype using Live2D Cubism 4 via pixi-live2d-display, with
the official "Haru" sample model. I have verified that the Cubism SDK
Publication License is only required above JPY 10,000,000 (~USD 67,000) annual
gross revenue, so I am currently exempt. I know Haru itself cannot ship.

Research these five questions. Cite primary sources (official licence pages,
repository LICENSE files, storefront terms) — not blog summaries.

1. FORMAT DECISION: Live2D Cubism vs VRM (three-vrm) vs something else
   (Spine, Rive, Godot, plain sprite/2D animation, video-based).
   For each, report: runtime licence terms and any revenue thresholds; whether
   the runtime is open source; CPU/GPU cost for a browser rendering one
   character at 1080p+ on integrated Intel graphics; lip-sync fidelity from
   audio; ease of authoring and iterating a character; and maturity of a React
   (not Vue) integration path. I care about total licence exposure and CPU
   headroom, because the same machine simultaneously runs speech recognition,
   text-to-speech, and a language model.

2. LICENSING IN DETAIL, for each format: what exactly must be paid, to whom,
   at what revenue or usage thresholds, and what changes if the buyer is a
   government body, a public school, or an NGO rather than a company. Flag any
   term that restricts use in education, restricts distribution as part of a
   hardware appliance, or requires attribution on screen. Note anything that
   differs for Vietnam specifically.

3. WHERE TO GET A CHARACTER that is legally shippable in a commercial product:
   marketplaces, free/CC0 model collections, commission pricing for a custom
   2D (Live2D-rigged) vs 3D (VRM) character, and typical turnaround. Give
   realistic USD price ranges for a rigged, expression-capable, lip-sync-ready
   character. Include whether "commercial use" on each source covers embedding
   in a sold software product, which is stricter than streaming use.

4. CHARACTER DESIGN FOR THE ACTUAL AUDIENCE — the part I care most about.
   What does research on children's educational media, pedagogical agents, and
   learning companions say about the design of an on-screen teaching character
   for primary/secondary students? Specifically:
     - realistic human vs stylized vs animal vs abstract/non-human
     - age and authority signals: peer-like companion vs adult teacher figure,
       and how that affects whether children speak up and take correction
     - gender presentation and its effect on engagement and on teacher/parent
       acceptance
     - cultural fit for Vietnam: is a Japanese-anime VTuber aesthetic an asset,
       neutral, or a liability with children, teachers, parents, and provincial
       education authorities?
     - how much visual detail survives projection in a bright classroom viewed
       from 8+ metres, and what that implies for silhouette, contrast, and
       facial expression scale
     - risks: uncanny valley, over-attachment, distraction from the lesson
       content, and any published guidance on avatars for minors
   Cite education research and real deployed products, not opinion pieces.

5. PRIOR ART: existing AI tutors, educational robots, and classroom companions
   aimed at children — especially in Vietnam and Southeast Asia (e.g. Pika by
   StepUp) and globally. What characters did they choose, in what format, and
   is there any published or reported evidence about how children responded?

Deliver:
  (a) a recommendation on format, with the licence reasoning made explicit;
  (b) a recommendation on character direction, with a short design brief I
      could hand to an illustrator or rigger;
  (c) a table of concrete sourcing options with prices and licence terms;
  (d) anything you found that would change my mind about the whole approach.

Be blunt about weak evidence. If the research on a point is thin or
contradictory, say so rather than manufacturing a confident answer.
```

---

## Why the prompt is shaped this way

Question 4 is the real question and gets the most space. Licensing (1–3) is a
solvable procurement problem — the character being *wrong for Vietnamese
children* is not something you can fix by paying someone.

Question 5 exists because Pika already deployed to this exact audience. Whatever
they learned about what children respond to is worth more than any amount of
general theory.

The instruction to cite primary sources is deliberate: licence terms get
misreported constantly in blog posts, and the Live2D revenue threshold in
particular is quoted wrongly in several places.
