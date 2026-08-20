"""The tool surface must agree everywhere it is declared.

docs/design/tool-surface.md §8: adding or changing a tool touches
mcp_server.py, teacher_os.py, hermes.py and infra/hermes/config.yaml
(both `tools.include` *and* the tool list inside `system_prompt` -- nothing
scans that prompt string, so a missed edit is a silent bug). This file checks
the classroom-core side against config.yaml; services/agent/tests checks the
Hermes adapter side against the same file.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp_server import TOOLS

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


def test_every_tool_name_agrees_across_mcp_server_and_config_yaml() -> None:
    mcp_names = {tool["name"] for tool in TOOLS}
    # The count is pinned so that adding a tool is a deliberate act with a
    # decision doc behind it, not a drive-by. Twelfth:
    # docs/decisions/2026-08-20-the-room-knows-who.md
    assert len(mcp_names) == 12

    text = CONFIG_YAML.read_text(encoding="utf-8")
    assert mcp_names == _include_list(text)
    assert mcp_names == _system_prompt_tools(text)
