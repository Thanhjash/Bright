"""`services/agent/evals` — the tool-routing and pedagogy suite (SP-3).

docs/4-build/open-questions.md SP-3 asks one question with a kill criterion:
*at Tau2 42.2, can E4B drive our tool surface?* Phase 1 runs mimo-v2.5-pro,
which is far stronger than what ships, so a good score here proves nothing on
its own. The suite therefore always measures **two configurations** and reports
the gap: what works because the design is right survives the weaker model;
what works because the model is strong does not.

Layout:

    scenarios.py   the scenario corpus + acceptable-set expectations
    variants.py    prompt/tool-surface variants (the fallback ladder, §3)
    runner.py      executes one scenario x one variant, live or from cassette
    graders.py     the eight SP-3 metrics
    report.py      the table
    probe_provider.py  does the endpoint support constrained decoding?
    __main__.py    one command
"""

from __future__ import annotations

__all__ = ["scenarios", "variants", "runner", "graders", "report"]
