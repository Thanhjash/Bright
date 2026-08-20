"""The tool surface must agree everywhere it is declared.

Mirrors services/classroom-core/tests/test_tool_surface_agreement.py, which
checks mcp_server.TOOLS against config.yaml. This checks the Hermes adapter
side of the same boundary (docs/design/tool-surface.md §8).
"""

from __future__ import annotations

import re
from pathlib import Path

from bright_agent.hermes import TEACHER_TOOLS

ROOT = Path(__file__).resolve().parents[3]
CONFIG_YAML = ROOT / "infra" / "hermes" / "config.yaml"


def _include_list(text: str) -> set[str]:
    match = re.search(r"include:\n((?:\s+-\s+\S+\n)+)", text)
    assert match, "tools.include block not found in config.yaml"
    return set(re.findall(r"-\s+(\S+)", match.group(1)))


def _system_prompt_tools(text: str) -> set[str]:
    match = re.search(r"Tools:\s*([^\n]+)\.", text)
    assert match, "system_prompt has no `Tools: ...` line"
    return {name.strip() for name in match.group(1).split(",")}


def test_every_tool_name_agrees_across_hermes_and_config_yaml() -> None:
    # Pinned on both sides so a tool cannot appear on one and not the other.
    # Twelfth: docs/decisions/2026-08-20-the-room-knows-who.md
    assert len(TEACHER_TOOLS) == 12

    text = CONFIG_YAML.read_text(encoding="utf-8")
    assert set(TEACHER_TOOLS) == _include_list(text)
    assert set(TEACHER_TOOLS) == _system_prompt_tools(text)
