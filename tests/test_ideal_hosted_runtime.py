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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ideal-hosted.sh"
BUILD_SCRIPT = ROOT / "infra" / "hermes" / "build_pinned.py"
REQUIREMENTS = ROOT / "infra" / "hermes" / "requirements.txt"
VERIFY_RUNTIME = ROOT / "infra" / "hermes" / "verify_runtime.py"
ENV_EXAMPLE = ROOT / ".env.example"


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


def run_environment_probe(tmp_path: Path, *, env: dict[str, str], assertions: str) -> subprocess.CompletedProcess[str]:
    """Exercise launcher setup without exposing its in-memory credentials.

    The production launcher has no debug command by design: keys must never be
    printed.  This subprocess-only probe runs its definitions through
    ``load_environment`` and checks predicates in the child shell instead.
    """
    definitions, marker, _ = SCRIPT.read_text(encoding="utf-8").partition('case "${1:-start}" in')
    assert marker
    probe = tmp_path / "launcher-environment-probe.sh"
    probe.write_text(f"{definitions}\nload_environment\n{assertions}\n", encoding="utf-8")
    probe.chmod(0o700)
    return subprocess.run(
        ["bash", str(probe)],
        cwd=ROOT,
        env={**os.environ, "BRIGHT_ROOT": str(tmp_path / "isolated-root"), **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_health_status_match_accepts_compact_and_spaced_json(tmp_path: Path) -> None:
    """Gateway health JSON is semantically stable even when formatting changes."""
    result = run_environment_probe(
        tmp_path,
        env={},
        assertions="""
response_matches '{"status":"ok"}' json-status-ok
response_matches '{ "service": "hermes", "status": "ok" }' json-status-ok
! response_matches '{"status":"degraded"}' json-status-ok
! response_matches 'not-json' json-status-ok
response_matches '{"stt":true,"status":"ok"}' '"stt":true'
! response_matches '{"stt":false,"status":"ok"}' '"stt":true'
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_ideal_launcher_refuses_missing_hosted_provider_credential(tmp_path: Path) -> None:
    result = run_launcher(
        "check",
        env={
            "BRIGHT_ROOT": str(tmp_path / "isolated-root"),
            "HERMES_API_KEY": "",
            "API_SERVER_KEY": "",
            "BRIGHT_MCP_TOKEN": "",
            "HERMES_MODEL_API_KEY": "",
            "LLM_API_KEY": "",
            "HERMES_MODEL_PROVIDER": "",
            "HERMES_MODEL_BASE_URL": "",
            "HERMES_MODEL_NAME": "",
            "LLM_BASE_URL": "",
            "LLM_MODEL": "",
        },
    )

    assert result.returncode != 0
    assert "HERMES_MODEL_API_KEY is required" in result.stderr
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
            "HERMES_MODEL_API_KEY": "CHANGE-ME-HOSTED-PROVIDER-KEY",
        },
    )

    assert result.returncode != 0
    assert "placeholder" in result.stderr.lower()


def test_ideal_launcher_rejects_copied_profile_placeholders_before_runtime_checks(
    tmp_path: Path,
) -> None:
    """A copied template remains fail-closed even after policy acknowledgement.

    Use an isolated root so a developer's untracked ``.env`` cannot mask the
    template values.  The root intentionally has no Python environments or
    services: a placeholder must be diagnosed before the launcher inspects
    either of them.
    """
    result = run_launcher(
        "check",
        env={
            "BRIGHT_ROOT": str(tmp_path / "copied-profile"),
            "HERMES_API_KEY": "CHANGE-ME-LOCAL-GATEWAY-KEY",
            "API_SERVER_KEY": "CHANGE-ME-API-SERVER-KEY",
            "BRIGHT_MCP_TOKEN": "CHANGE-ME-MCP-TOKEN",
            "HERMES_MODEL_PROVIDER": "custom",
            "HERMES_MODEL_BASE_URL": "https://provider.example/v1",
            "HERMES_MODEL_API_KEY": "CHANGE-ME-HOSTED-PROVIDER-KEY",
            "HERMES_MODEL_NAME": "CHANGE-ME-HOSTED-TEACHER-MODEL",
            "BRIGHT_DATA_POLICY": "hosted_ephemeral_transcript",
            "BRIGHT_HOSTED_RAW_ACK": "1",
        },
    )

    assert result.returncode != 0
    assert "HERMES_MODEL_API_KEY is a placeholder" in result.stderr
    assert "classroom-core Python is missing" not in result.stderr
    assert "speech Python is missing" not in result.stderr


def test_env_example_documents_legacy_provider_and_ephemeral_local_keys() -> None:
    """The template must not make copied local secrets a setup prerequisite."""
    example = ENV_EXAMPLE.read_text(encoding="utf-8")

    for name in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "BRIGHT_DATA_POLICY",
        "BRIGHT_HOSTED_RAW_ACK",
    ):
        assert f"{name}=" in example

    assert "BRIGHT_DATA_POLICY=hosted_ephemeral_transcript" in example
    assert "BRIGHT_HOSTED_RAW_ACK=0" in example
    assert "raw ASR transcript" in example
    assert "reuses the LLM_* provider configuration" in example
    assert "fresh loopback-only credentials in memory" in example
    assert "HERMES_API_KEY=" not in example
    assert "API_SERVER_KEY=" not in example
    assert "BRIGHT_MCP_TOKEN=" not in example


def test_ideal_launcher_never_calls_running_services_a_ready_classroom() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "classroom awaits Stage + Control capability leases" in source
    assert 'say "ideal hosted stack is ready"' not in source


def test_status_is_diagnostic_without_a_configured_hermes_key() -> None:
    result = run_launcher("status", env={"HERMES_API_KEY": ""})

    assert "unbound variable" not in result.stderr
    assert "hermes" in result.stdout


def test_status_uses_unauthenticated_hermes_health_across_launcher_invocations(
    tmp_path: Path,
) -> None:
    """A generated per-run bearer must not make a later status probe lie.

    Hermes intentionally leaves ``/health`` unauthenticated.  Model this
    contract with a server that rejects any Authorization header, then run the
    actual launcher status command against a live PID file.
    """
    requests: list[str | None] = []

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            requests.append(self.headers.get("Authorization"))
            if self.headers.get("Authorization"):
                self.send_response(401)
                self.end_headers()
                return
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sleeper = subprocess.Popen(["sleep", "30"])
    runtime = tmp_path / "runtime"
    (runtime / "pids").mkdir(parents=True)
    (runtime / "pids" / "hermes.pid").write_text(str(sleeper.pid), encoding="utf-8")
    try:
        result = run_launcher(
            "status",
            env={
                "BRIGHT_IDEAL_RUNTIME_DIR": str(runtime),
                "HERMES_PORT": str(server.server_port),
                # Deliberately differs from the running gateway's unknown,
                # ephemeral key.  A bearer header must not be sent at all.
                "HERMES_API_KEY": "new-invocation-key-that-must-not-be-sent",
            },
        )
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=5)
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    # Other components are intentionally absent, so status is non-zero; the
    # Hermes line itself must accurately report this live health endpoint.
    assert result.returncode != 0
    assert "ready hermes" in result.stdout
    assert requests == [None]


def test_product_start_and_acceptance_start_use_distinct_lessons() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "content/lessons/market-food/market-food-01.run.json" in source
    assert 'acceptance-start)' in source
    assert 'tests/fixtures/ideal_composed_one_turn.run.json' in source
    assert 'tests/fixtures/ideal_composed_three_turn.run.json' in source
    assert 'BRIGHT_ACCEPTANCE_FIXTURE must be one-turn or three-turn' in source
    assert 'HERMES_API_TIMEOUT_S="${BRIGHT_ACCEPTANCE_HERMES_TIMEOUT_S:-$AGENT_TURN_TIMEOUT_S}"' in source


def test_port_override_is_the_single_core_to_hermes_endpoint() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'export HERMES_API_URL="http://127.0.0.1:${HERMES_PORT}"' in source


def test_launcher_explicitly_enables_and_pins_the_api_server_platform() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "export API_SERVER_ENABLED=true" in source
    assert "export API_SERVER_HOST=127.0.0.1" in source
    assert 'export API_SERVER_PORT="$HERMES_PORT"' in source
    assert "export API_SERVER_MODEL_NAME=bright-classroom" in source


def test_hermes_launcher_runs_the_pinned_api_server_in_the_foreground() -> None:
    """The release gate must start the gateway server, not Hermes' bare CLI."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'start_one hermes "$HERMES_BIN" gateway run --external-supervisor' in source
    assert 'start_one hermes "$HERMES_BIN" gateway\n' not in source


def test_hermes_runtime_installs_its_api_server_transport() -> None:
    assert "aiohttp==" in REQUIREMENTS.read_text(encoding="utf-8")


def test_bootstrap_reinstalls_exact_wheel_and_verifier_checks_installed_bytes() -> None:
    launcher = SCRIPT.read_text(encoding="utf-8")
    verifier = VERIFY_RUNTIME.read_text(encoding="utf-8")

    assert "--force-reinstall --no-deps" in launcher
    assert "bright_live_sha256" in verifier
    assert "hashlib.sha256(installed_module.read_bytes())" in verifier


def test_ideal_launcher_accepts_a_complete_local_runtime_layout_with_legacy_llm(tmp_path: Path) -> None:
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
            "HERMES_API_KEY": "CHANGE-ME-LOCAL-GATEWAY-KEY",
            "API_SERVER_KEY": "CHANGE-ME-API-SERVER-KEY",
            "BRIGHT_MCP_TOKEN": "CHANGE-ME-MCP-TOKEN",
            "HERMES_MODEL_API_KEY": "",
            "HERMES_MODEL_BASE_URL": "",
            "HERMES_MODEL_NAME": "",
            "HERMES_MODEL_PROVIDER": "",
            "LLM_API_KEY": "hosted-provider-key",
            "LLM_BASE_URL": "https://provider.example/v1",
            "LLM_MODEL": "teacher-model",
            "BRIGHT_DATA_POLICY": "hosted_ephemeral_transcript",
            "BRIGHT_HOSTED_RAW_ACK": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "ideal hosted preflight passed" in result.stdout


def test_legacy_llm_defaults_and_local_gateway_key_stay_in_memory(tmp_path: Path) -> None:
    result = run_environment_probe(
        tmp_path,
        env={
            "HERMES_MODEL_PROVIDER": "",
            "HERMES_MODEL_BASE_URL": "",
            "HERMES_MODEL_API_KEY": "",
            "HERMES_MODEL_NAME": "",
            "LLM_BASE_URL": "https://legacy.provider.invalid/v1",
            "LLM_API_KEY": "legacy-provider-key",
            "LLM_MODEL": "legacy-teacher-model",
            "LLM_DISABLE_THINKING": "true",
            "HERMES_API_KEY": "CHANGE-ME-LOCAL-GATEWAY-KEY",
            "API_SERVER_KEY": "",
            "BRIGHT_MCP_TOKEN": "placeholder-mcp-token",
        },
        assertions="""
[[ "$HERMES_MODEL_PROVIDER" == custom ]]
[[ "$HERMES_MODEL_BASE_URL" == https://legacy.provider.invalid/v1 ]]
[[ "$HERMES_MODEL_API_KEY" == legacy-provider-key ]]
[[ "$HERMES_MODEL_NAME" == legacy-teacher-model ]]
[[ "$HERMES_MODEL_MIMO_DISABLE_THINKING" == true ]]
for name in HERMES_API_KEY API_SERVER_KEY BRIGHT_MCP_TOKEN; do
  value="${!name}"
  [[ ${#value} -ge 32 ]]
  ! is_placeholder "$value"
done
[[ "$HERMES_API_KEY" == "$API_SERVER_KEY" ]]
[[ "$HERMES_API_KEY" != "$BRIGHT_MCP_TOKEN" ]]
[[ "$API_SERVER_KEY" != "$BRIGHT_MCP_TOKEN" ]]
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_gateway_api_server_key_is_the_adapter_key(tmp_path: Path) -> None:
    """The Core-side Hermes adapter must authenticate with the live gateway key.

    Hermes resolves API_SERVER_KEY after config expansion, whereas Bright's
    adapter reads HERMES_API_KEY. A pre-existing developer file may contain
    different values; the launcher reconciles them in memory before either
    process starts.
    """
    result = run_environment_probe(
        tmp_path,
        env={
            "HERMES_API_KEY": "old-client-key-that-must-not-win",
            "API_SERVER_KEY": "server-key-that-gateway-uses",
        },
        assertions="""
[[ "$HERMES_API_KEY" == server-key-that-gateway-uses ]]
[[ "$API_SERVER_KEY" == server-key-that-gateway-uses ]]
[[ "$API_SERVER_ENABLED" == true ]]
[[ "$API_SERVER_HOST" == 127.0.0.1 ]]
[[ "$API_SERVER_PORT" == "$HERMES_PORT" ]]
[[ "$API_SERVER_MODEL_NAME" == bright-classroom ]]
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_explicit_hermes_model_override_wins_over_legacy_llm(tmp_path: Path) -> None:
    result = run_environment_probe(
        tmp_path,
        env={
            "HERMES_MODEL_PROVIDER": "custom",
            "HERMES_MODEL_BASE_URL": "http://127.0.0.1:9000/v1",
            "HERMES_MODEL_API_KEY": "local-model-key",
            "HERMES_MODEL_NAME": "local-teacher",
            "LLM_BASE_URL": "https://legacy.provider.invalid/v1",
            "LLM_API_KEY": "legacy-provider-key",
            "LLM_MODEL": "legacy-teacher-model",
            "LLM_DISABLE_THINKING": "true",
        },
        assertions="""
[[ "$HERMES_MODEL_PROVIDER" == custom ]]
[[ "$HERMES_MODEL_BASE_URL" == http://127.0.0.1:9000/v1 ]]
[[ "$HERMES_MODEL_API_KEY" == local-model-key ]]
[[ "$HERMES_MODEL_NAME" == local-teacher ]]
[[ "$HERMES_MODEL_MIMO_DISABLE_THINKING" == false ]]
""",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


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
    assert config["gateway"]["api_server"]["extra"]["bright_live"]["terminal_tool"] == (
        "mcp__bright_classroom__classroom_propose_move"
    )
    assert config["gateway"]["api_server"]["extra"]["bright_live"]["mimo_disable_thinking"] == (
        "${HERMES_MODEL_MIMO_DISABLE_THINKING}"
    )
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
