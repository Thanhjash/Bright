"""The system prompt and the turn-context renderer.

Budget discipline (docs/archive/phase-1-plan.md §4): MiMo already spends ~250 prompt tokens on
a hidden preamble and reports `cached_tokens`. So:

  * SYSTEM_PROMPT is a module constant — byte-identical on every turn, so
    the provider's prefix cache can hit.
  * Everything volatile (state, actions, memory) goes in the final user
    message, rendered by `render_turn`.

This is sized for a 4.5B model even though Phase 1 runs a big one. Do not
grow it. If you need the model to know something new, ask whether an
`available_actions` label can carry it instead.
"""

from __future__ import annotations

from typing import Any

from bright_contracts import Scene, TurnContext

SYSTEM_PROMPT = """\
You are the teacher of a live English class in Vietnam. 20-40 children share one screen. \
You speak to the room, out loud, in real time.

HOW YOU ACT
- You never draw on the screen. Each turn you are given a numbered list of legal actions. \
Pick exactly ONE by calling classroom_choose_next with its exact id and the state_version shown.
- Never invent an action id. If none is ideal, pick the closest one on the list.
- classroom_say is your voice: 1-2 short sentences a beginner can follow. Say something before you act.
- classroom_record_observation when a named student showed what they can or cannot do yet.
- classroom_recall only when you need history you were not given.
- Finish the turn quickly. The class is waiting and you get one attempt.

SCAFFOLDING - when a student is lost, go down exactly ONE step. Never jump straight to Vietnamese.
1 English -> 2 simpler English -> 3 image or gesture -> 4 a concrete example \
-> 5 a short Vietnamese hint -> 6 a full Vietnamese explanation
Climb back to English on the next attempt. The goal is to think in English, not to translate.

EMOTION - you may place tokens inline in your spoken text:
<|ACT {"emotion":"happy"}|>   <|ACT {"emotion":"think","motion":"nod"}|>
Exactly these nine emotions, no others:
happy sad angry think surprised awkward question curious neutral
At most one token per sentence, and only when it means something."""


# ------------------------------------------------------------ rendering


def _clip(s: Any, n: int = 60) -> str:
    text = str(s).replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def summarize_scene(scene: Scene) -> str:
    """One line describing what is on the board. Semantic, never DOM."""
    p: dict[str, Any] = scene.props or {}
    k = scene.kind
    if k == "text":
        return f'text: "{_clip(p.get("text", ""))}"'
    if k in ("image", "video"):
        return f'{k}: {p.get("asset", "?")} {_clip(p.get("caption", ""), 40)}'.strip()
    if k == "vocabulary":
        words = ", ".join(_clip(i.get("text", i.get("id", "?")), 16) for i in p.get("items", [])[:8])
        hi = p.get("highlightId")
        return f"vocabulary: {words}" + (f" (highlight {hi})" if hi else "")
    if k == "choice":
        opts = ", ".join(
            f'{o.get("id")}={_clip(o.get("text") or o.get("asset") or "", 20)}'
            for o in p.get("options", [])[:6]
        )
        revealed = p.get("revealed")
        tail = f" (answered: {revealed})" if revealed else ""
        return f'choice: "{_clip(p.get("prompt", ""))}" [{opts}]{tail}'
    if k == "matching":
        return f'matching: {len(p.get("left", []))} pairs, {len(p.get("solved", []))} solved'
    if k == "sentence_builder":
        toks = " ".join(t.get("text", "") for t in p.get("tokens", [])[:10])
        return f'sentence_builder: tokens [{toks}] placed {p.get("placed", [])}'
    if k == "pronunciation":
        return f'pronunciation: "{p.get("word", "")}"'
    if k == "roleplay":
        return f'roleplay: {p.get("environment", "")} — you are {p.get("aiRole", "?")}'
    if k == "explore":
        return f'explore: {p.get("topic", "")} (focus {p.get("focusId", "-")})'
    return k


def render_turn(ctx: TurnContext) -> str:
    """Compact rendering of the volatile half of the prompt.

    Order matters a little: position, board, student, what just happened,
    memory, then the action list *last* so it is the freshest thing in the
    model's window when it chooses.
    """
    L = ctx.lesson
    lines: list[str] = [
        f"LESSON {L.lesson_id} · class {L.class_id} · stage {L.stage} · "
        f"activity {L.activity_index + 1}/{L.activity_count}",
        f"BOARD {summarize_scene(ctx.scene)}",
    ]

    if ctx.student:
        skills = ", ".join(f"{k} {v:.2f}" for k, v in sorted(ctx.student.skills.items())[:6])
        lines.append(
            f"STUDENT {ctx.student.name} ({ctx.student.id})" + (f" — {skills}" if skills else "")
        )

    if ctx.last_interaction:
        li = ctx.last_interaction
        outcome = f" → {li.outcome}" if li.outcome else ""
        lines.append(f"JUST DID {li.kind}: {_clip(li.detail, 80)}{outcome}")

    if ctx.recalled:
        lines.append("MEMORY")
        lines += [f"- {m.when}: {_clip(m.text, 90)}" for m in ctx.recalled[:5]]

    if ctx.available_actions:
        lines.append(f"ACTIONS (state_version {ctx.state_version}) — choose exactly one id:")
        for i, a in enumerate(ctx.available_actions, 1):
            params = f"  [params: {', '.join(a.params)}]" if a.params else ""
            lines.append(f"{i}. {a.id} — {a.label}{params}")
        lines.append("Say one short line, then call classroom_choose_next. Now.")
    else:
        lines.append(
            f"ACTIONS (state_version {ctx.state_version}): none available. "
            "Speak if useful, then stop."
        )

    return "\n".join(lines)


def build_messages(ctx: TurnContext, *, system: str = SYSTEM_PROMPT) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": render_turn(ctx)},
    ]


__all__ = ["SYSTEM_PROMPT", "summarize_scene", "render_turn", "build_messages"]
