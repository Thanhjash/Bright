"""Tables. One command, one clear answer."""

from __future__ import annotations

from typing import Iterable, Sequence

from .graders import ClassMetrics, Graded
from .scenarios import CLASSES

#: SP-3's kill criterion (open-questions.md): tool_routing < 85% means the
#: tool surface must shrink or the model must grow.
KILL_THRESHOLD = 85.0


def _rule(widths: Sequence[int], ch: str = "-") -> str:
    return "  ".join(ch * w for w in widths)


def _row(cells: Sequence[str], widths: Sequence[int], align: str = "") -> str:
    out = []
    for i, (c, w) in enumerate(zip(cells, widths)):
        out.append(c.ljust(w) if (align[i : i + 1] or "l") == "l" else c.rjust(w))
    return "  ".join(out).rstrip()


def per_class_table(metrics: list[ClassMetrics], title: str) -> str:
    head = ["class", "n", "sel%", "args%", "halluc%", "policy%", "repair%", "err%", "p50 s", "prompt", "cached", "compl"]
    widths = [14, 3, 6, 6, 8, 8, 8, 6, 6, 7, 7, 6]
    align = "lrrrrrrrrrrr"
    lines = [title, _rule(widths, "=")]
    lines.append(_row(head, widths, align))
    lines.append(_rule(widths))
    for m in metrics:
        lines.append(_row([
            m.cls, str(m.n),
            f"{m.selection_accuracy:.1f}", f"{m.arg_validity:.1f}",
            f"{m.hallucinated_rate:.1f}", f"{m.policy_violation_rate:.1f}",
            "-" if m.repair_rate is None else f"{m.repair_rate:.1f}",
            f"{m.error_rate:.1f}",
            f"{m.latency_p50:.2f}",
            f"{m.prompt_tokens:.0f}", f"{m.cached_tokens:.0f}", f"{m.completion_tokens:.0f}",
        ], widths, align))
    return "\n".join(lines)


def matrix_table(rows: list[tuple[str, str, ClassMetrics, ClassMetrics]]) -> str:
    """One line per (model, variant): routing accuracy + overall + cost.

    `rows` is (model, variant, tool_routing metrics, ALL metrics).
    """
    head = ["model", "variant", "routing%", "all sel%", "args%", "halluc%", "policy%", "p50 s", "prompt", "cached", "SP-3"]
    widths = [14, 15, 9, 9, 6, 8, 8, 6, 7, 7, 5]
    align = "llrrrrrrrrl"
    lines = [_rule(widths, "=")]
    lines.append(_row(head, widths, align))
    lines.append(_rule(widths))
    for model, variant, routing, allm in rows:
        verdict = "PASS" if routing.selection_accuracy >= KILL_THRESHOLD else "KILL"
        lines.append(_row([
            model, variant,
            f"{routing.selection_accuracy:.1f}", f"{allm.selection_accuracy:.1f}",
            f"{allm.arg_validity:.1f}", f"{allm.hallucinated_rate:.1f}",
            f"{allm.policy_violation_rate:.1f}", f"{allm.latency_p50:.2f}",
            f"{allm.prompt_tokens:.0f}", f"{allm.cached_tokens:.0f}", verdict,
        ], widths, align))
    lines.append(_rule(widths, "="))
    lines.append(f"SP-3 kill criterion: tool_routing selection accuracy < {KILL_THRESHOLD:.0f}%")
    return "\n".join(lines)


def failures(graded: Iterable[Graded], limit: int = 25) -> str:
    bad = [g for g in graded if not g.ok]
    if not bad:
        return "no failures"
    lines = [f"{len(bad)} failing scenarios (showing {min(limit, len(bad))}):"]
    for g in bad[:limit]:
        chose = g.trace.chosen_action
        why = []
        if not g.selection_ok:
            why.append(f"chose {chose!r}, accept={sorted(g.scenario.accept) or '(none)'}")
        if not g.args_ok:
            why.append("args invalid")
        if g.hallucinated:
            why.append("HALLUCINATED")
        why += g.violations
        lines.append(f"  {g.scenario.cls:<13} {g.scenario.id:<34} {'; '.join(why)[:140]}")
    return "\n".join(lines)


def class_metrics(graded: list[Graded]) -> list[ClassMetrics]:
    from .graders import aggregate

    return [aggregate(graded, c) for c in CLASSES] + [aggregate(graded, "ALL")]


__all__ = ["per_class_table", "matrix_table", "failures", "class_metrics", "KILL_THRESHOLD"]
