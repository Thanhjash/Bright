"""Contracts for the fail-closed ideal hosted runtime launcher.

These tests deliberately exercise the shell entrypoint.  The launcher is the
boundary that prevents a polished demo from silently becoming the authored
offline path when a real dependency is absent.
"""

from __future__ import annotations

import os
import subprocess
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ideal-hosted.sh"
BUILD_SCRIPT = ROOT / "infra" / "hermes" / "build_pinned.py"
REQUIREMENTS = ROOT / "infra" / "hermes" / "requirements.txt"
VERIFY_RUNTIME = ROOT / "infra" / "hermes" / "verify_runtime.py"


def run_launcher(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_ideal_launcher_refuses_missing_hosted_credential() -> None:
    result = run_launcher(
        "check",
        env={
            "HERMES_API_KEY": "",
            "API_SERVER_KEY": "",
            "BRIGHT_MCP_TOKEN": "",
            "HERMES_MODEL_API_KEY": "",
        },
    )

    assert result.returncode != 0
    assert "HERMES_API_KEY is required" in result.stderr
    assert "authored" not in (result.stdout + result.stderr).lower()


def test_ideal_launcher_never_echoes_credential_values() -> None:
    secret = "must-not-appear-9e70dd"
    result = run_launcher(
        "check",
        env={
            "HERMES_API_KEY": secret,
            "API_SERVER_KEY": secret,
            "BRIGHT_MCP_TOKEN": secret,
            "HERMES_MODEL_API_KEY": secret,
        },
    )

    assert result.returncode != 0
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_ideal_launcher_rejects_placeholder_credentials_before_starting() -> None:
    result = run_launcher(
        "check",
        env={
            "HERMES_API_KEY": "CHANGE-ME",
            "API_SERVER_KEY": "CHANGE-ME",
            "BRIGHT_MCP_TOKEN": "CHANGE-ME",
            "HERMES_MODEL_API_KEY": "real-provider-key",
        },
    )

    assert result.returncode != 0
    assert "placeholder" in result.stderr.lower()


def test_ideal_launcher_never_calls_running_services_a_ready_classroom() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "classroom awaits Stage + Control capability leases" in source
    assert 'say "ideal hosted stack is ready"' not in source


def test_status_is_diagnostic_without_a_configured_hermes_key() -> None:
    result = run_launcher("status", env={"HERMES_API_KEY": ""})

    assert "unbound variable" not in result.stderr
    assert "hermes" in result.stdout


def test_product_start_and_acceptance_start_use_distinct_lessons() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "content/lessons/market-food/market-food-01.run.json" in source
    assert 'acceptance-start)' in source
    assert 'tests/fixtures/ideal_composed_one_turn.run.json' in source
    assert 'HERMES_API_TIMEOUT_S="${BRIGHT_ACCEPTANCE_HERMES_TIMEOUT_S:-$AGENT_TURN_TIMEOUT_S}"' in source


def test_port_override_is_the_single_core_to_hermes_endpoint() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'export HERMES_API_URL="http://127.0.0.1:${HERMES_PORT}"' in source


def test_hermes_runtime_installs_its_api_server_transport() -> None:
    assert "aiohttp==" in REQUIREMENTS.read_text(encoding="utf-8")


def test_bootstrap_reinstalls_exact_wheel_and_verifier_checks_installed_bytes() -> None:
    launcher = SCRIPT.read_text(encoding="utf-8")
    verifier = VERIFY_RUNTIME.read_text(encoding="utf-8")

    assert "--force-reinstall --no-deps" in launcher
    assert "bright_live_sha256" in verifier
    assert "hashlib.sha256(installed_module.read_bytes())" in verifier


def test_ideal_launcher_accepts_a_complete_local_runtime_layout(tmp_path: Path) -> None:
    root = tmp_path / "bright"
    (root / "models" / "piper").mkdir(parents=True)
    (root / "models" / "whisper" / "models--Systran--faster-whisper-small.en").mkdir(parents=True)
    (root / "apps" / "classroom-ui" / "dist").mkdir(parents=True)
    (root / "tests" / "fixtures").mkdir(parents=True)
    (root / "infra" / "hermes").mkdir(parents=True)
    (root / "models" / "piper" / "en_US-lessac-medium.onnx").write_bytes(b"voice")
    (root / "apps" / "classroom-ui" / "dist" / "index.html").write_text("ok")
    (root / "tests" / "fixtures" / "ideal_composed_one_turn.run.json").write_text("{}")
    (root / "infra" / "hermes" / "verify_runtime.py").write_text("raise SystemExit(0)\n")
    hermes_home = root / ".runtime" / "hermes" / "classroom"
    hermes_home.mkdir(parents=True)
    (hermes_home / "config.yaml").write_text("gateway: {}\n")
    executable = root / "fake-python"
    executable.write_text("#!/usr/bin/env bash\nexit 0\n")
    executable.chmod(0o755)
    hermes = root / "fake-hermes"
    hermes.write_text("#!/usr/bin/env bash\nexit 0\n")
    hermes.chmod(0o755)

    result = run_launcher(
        "check",
        env={
            "BRIGHT_ROOT": str(root),
            "CORE_PY": str(executable),
            "SPEECH_PY": str(executable),
            "HERMES_PY": str(executable),
            "HERMES_BIN": str(hermes),
            "HERMES_HOME": str(hermes_home),
            "CORE_LESSON_RUN": str(root / "tests" / "fixtures" / "ideal_composed_one_turn.run.json"),
            "HERMES_API_KEY": "local-sidecar-key",
            "API_SERVER_KEY": "api-server-key",
            "BRIGHT_MCP_TOKEN": "mcp-key",
            "HERMES_MODEL_API_KEY": "hosted-provider-key",
            "HERMES_MODEL_BASE_URL": "https://provider.example/v1",
            "HERMES_MODEL_NAME": "teacher-model",
            "HERMES_MODEL_PROVIDER": "custom",
            "BRIGHT_DATA_POLICY": "hosted_ephemeral_transcript",
            "BRIGHT_HOSTED_RAW_ACK": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "ideal hosted preflight passed" in result.stdout


def test_pinned_builder_verification_never_dirties_the_vendor_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    subprocess.run(["git", "init"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=vendor, check=True)
    subprocess.run(["git", "config", "user.name", "Bright test"], cwd=vendor, check=True)
    tracked = vendor / "runtime.txt"
    tracked.write_text("upstream\n")
    subprocess.run(["git", "add", "runtime.txt"], cwd=vendor, check=True)
    subprocess.run(["git", "commit", "-m", "upstream"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    tracked.write_text("bright patch\n")
    patch = subprocess.run(
        ["git", "diff"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)

    hermes = tmp_path / "hermes"
    hermes.mkdir()
    patch_path = hermes / "bright.patch"
    patch_path.write_text(patch)
    manifest = hermes / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "upstream_commit": commit,
                "version": "test",
                "patches": [{"file": "bright.patch", "sha256": __import__("hashlib").sha256(patch.encode()).hexdigest()}],
            }
        )
    )
    spec = importlib.util.spec_from_file_location("bright_build_pinned_test", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "HERE", hermes)
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(sys, "argv", ["build_pinned.py", "--repo", str(vendor), "--verify-only"])

    assert module.main() == 0
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    assert status == ""


def test_live_profile_keeps_its_terminal_mcp_schema_model_visible() -> None:
    import yaml

    config = yaml.safe_load((ROOT / "infra" / "hermes" / "config.yaml").read_text())

    assert config["tools"]["tool_search"] is False
    assert config["gateway"]["api_server"]["extra"]["bright_live"]["enabled"] is True
    assert config["platform_toolsets"]["api_server"] == ["bright-classroom"]
    assert config["mcp_servers"]["bright-classroom"]["tools"]["include"] == [
        "classroom_propose_move"
    ]


def test_pinned_builder_ignores_but_preserves_vendor_worktree_changes(
    tmp_path: Path, monkeypatch
) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    subprocess.run(["git", "init"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=vendor, check=True)
    subprocess.run(["git", "config", "user.name", "Bright test"], cwd=vendor, check=True)
    tracked = vendor / "runtime.txt"
    tracked.write_text("upstream\n")
    subprocess.run(["git", "add", "runtime.txt"], cwd=vendor, check=True)
    subprocess.run(["git", "commit", "-m", "upstream"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    tracked.write_text("bright patch\n")
    patch = subprocess.run(
        ["git", "diff"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=vendor, check=True, stdout=subprocess.DEVNULL)

    hermes = tmp_path / "hermes"
    hermes.mkdir()
    patch_path = hermes / "bright.patch"
    patch_path.write_text(patch)
    manifest = hermes / "manifest.json"
    manifest.write_text(json.dumps({
        "upstream_commit": commit,
        "version": "test",
        "patches": [{"file": "bright.patch", "sha256": __import__("hashlib").sha256(patch.encode()).hexdigest()}],
    }))
    spec = importlib.util.spec_from_file_location("bright_build_pinned_dirty_test", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "HERE", hermes)
    monkeypatch.setattr(module, "MANIFEST_PATH", manifest)
    tracked.write_text("local developer work\n")
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    monkeypatch.setattr(sys, "argv", ["build_pinned.py", "--repo", str(vendor), "--verify-only"])

    assert module.main() == 0
    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=vendor, check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    assert after == before
