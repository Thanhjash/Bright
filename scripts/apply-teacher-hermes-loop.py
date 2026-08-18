#!/usr/bin/env python3
"""Make the installed Hermes live profile a multi-tool teacher loop.

The stock 0.20.0+bright.2 pin exits after the first MCP call and forces
exact classroom_propose_move. This cook needs read_library then say.
Idempotent. Does not rebuild the wheel.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = (
    ROOT
    / ".runtime"
    / "layer1"
    / "hermes-venv"
    / "lib"
    / "python3.13"
    / "site-packages"
)

PATCHES: list[tuple[str, str, str]] = [
    (
        "agent/bright_live.py",
        'BRIGHT_PATCH_VERSION = "0.20.0+bright.2"',
        'BRIGHT_PATCH_VERSION = "0.20.0+bright.3"',
    ),
    (
        "agent/bright_live.py",
        "    agent.max_iterations = 1",
        "    agent.max_iterations = 8",
    ),
    (
        "agent/bright_live.py",
        """        request_overrides["tool_choice"] = {
            "type": "function",
            "function": {"name": profile.terminal_tool},
        }""",
        '        request_overrides["tool_choice"] = {"type": "required"}',
    ),
    (
        "agent/bright_live.py",
        """    if profile is None or not profile.enabled:
        return list(tool_calls)
    for tool_call in tool_calls:
        function = getattr(tool_call, "function", None)
        name = str(getattr(function, "name", None) or "")
        if name == profile.terminal_tool or name.endswith(f"__{profile.terminal_tool}"):
            return [tool_call]
    return []""",
        """    if profile is None or not profile.enabled:
        return list(tool_calls)
    kept: list[Any] = []
    for tool_call in tool_calls:
        function = getattr(tool_call, "function", None)
        name = str(getattr(function, "name", None) or "")
        if "bright_classroom" in name or name.endswith(
            ("read_library", "search_library", "write_board", "read_board", "show_image", "play_clip", "say", "record_evidence")
        ):
            kept.append(tool_call)
    return kept""",
    ),
    (
        "agent/bright_live.py",
        '("read_library", "search_library", "write_board", "show_image", "play_clip", "say", "record_evidence")',
        '("read_library", "search_library", "write_board", "read_board", "show_image", "play_clip", "say", "record_evidence")',
    ),
    (
        "agent/bright_live.py",
        "    agent.max_iterations = 6",
        "    agent.max_iterations = 8",
    ),
    (
        "gateway/platforms/api_server.py",
        "            6 if self._bright_live_profile.enabled else _current_max_iterations()",
        "            8 if self._bright_live_profile.enabled else _current_max_iterations()",
    ),
    (
        "gateway/run.py",
        """            turn_request_overrides["tool_choice"] = {
                "type": "function",
                "function": {"name": bright_profile.terminal_tool},
            }""",
        '            turn_request_overrides["tool_choice"] = {"type": "required"}',
    ),
    (
        "gateway/platforms/api_server.py",
        """        max_iterations = (
            1 if self._bright_live_profile.enabled else _current_max_iterations()
        )""",
        """        max_iterations = (
            8 if self._bright_live_profile.enabled else _current_max_iterations()
        )""",
    ),
    (
        "agent/conversation_loop.py",
        """                if _bright_live_profile is not None:
                    _turn_exit_reason = "bright_terminal_tool"
                    final_response = turn_content
                    break""",
        """                if _bright_live_profile is not None:
                    _last_names = [
                        str(getattr(getattr(tc, "function", None), "name", "") or "")
                        for tc in (assistant_message.tool_calls or [])
                    ]
                    if any(name.endswith("__say") or name.endswith(".say") or name == "say" for name in _last_names):
                        _turn_exit_reason = "bright_terminal_tool"
                        final_response = turn_content
                        break""",
    ),
]


def apply(site: Path) -> int:
    if not site.is_dir():
        print(f"teacher-hermes-loop: site-packages missing: {site}", file=sys.stderr)
        return 2
    changed = 0
    for rel, old, new in PATCHES:
        path = site / rel
        text = path.read_text(encoding="utf-8")
        if new in text:
            continue
        if old not in text:
            print(f"teacher-hermes-loop: skip {rel} (already different)", file=sys.stderr)
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        changed += 1
        print(f"teacher-hermes-loop: patched {rel}")
    if changed == 0:
        print("teacher-hermes-loop: already applied")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SITE
    raise SystemExit(apply(target))
