#!/usr/bin/env python3
"""Verify, patch, test and build Bright's pinned Hermes wheel.

The input checkout's HEAD must be exactly at the manifest commit. The working
tree may contain developer changes because the build never reads it: a clean,
detached disposable worktree is created from that exact commit, then the
tracked Bright patch is applied there. The produced wheel checksum is written
beside the wheel and must be promoted into the deployment bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
BRIGHT_ROOT = HERE.parents[1]
MANIFEST_PATH = HERE / "manifest.json"


def _run(
    args: list[str],
    *,
    cwd: Path,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        env=env,
    )
    return (result.stdout or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        type=Path,
        default=BRIGHT_ROOT / "references" / "hermes-agent",
    )
    # The appliance installer consumes release/wheels; build directly into
    # that bundle layout unless the caller requests another staging path.
    parser.add_argument("--outdir", type=Path, default=BRIGHT_ROOT / "wheels")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    args.outdir = args.outdir.resolve()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    repo = args.repo.resolve()
    expected_commit = manifest["upstream_commit"]
    actual_commit = _run(["git", "rev-parse", "HEAD"], cwd=repo, capture=True)
    if actual_commit != expected_commit:
        raise SystemExit(
            f"refusing unpinned Hermes checkout: expected {expected_commit}, got {actual_commit}"
        )
    # Build in a disposable worktree.  Applying the Bright patch directly to
    # ``repo`` made a successful build leave the vendor checkout dirty, so a
    # second invocation refused to run.  The source checkout remains a
    # verified immutable input while the worktree is the only mutable build
    # surface.
    with tempfile.TemporaryDirectory(prefix="bright-hermes-") as temporary:
        worktree = Path(temporary) / "source"
        _run(
            ["git", "worktree", "add", "--detach", str(worktree), expected_commit],
            cwd=repo,
        )
        try:
            for entry in manifest["patches"]:
                patch = HERE / entry["file"]
                actual_hash = _sha256(patch)
                if actual_hash != entry["sha256"]:
                    raise SystemExit(
                        f"patch checksum mismatch for {patch.name}: {actual_hash}"
                    )
                _run(["git", "apply", "--check", str(patch)], cwd=worktree)
                _run(["git", "apply", str(patch)], cwd=worktree)

            _run(["git", "diff", "--check"], cwd=worktree)
            if args.test:
                _run(
                    [
                        "scripts/run_tests.sh",
                        "tests/agent/test_bright_live_profile.py",
                        "tests/gateway/test_bright_live_api_server.py",
                        "-q",
                    ],
                    cwd=worktree,
                )
            if args.verify_only:
                print(f"verified {manifest['version']} against {expected_commit}")
                return 0

            args.outdir.mkdir(parents=True, exist_ok=True)
            uv = shutil.which("uv")
            build_command = (
                [uv, "build", "--wheel", "--out-dir", str(args.outdir)]
                if uv
                else [sys.executable, "-m", "build", "--wheel", "--outdir", str(args.outdir)]
            )
            build_env = dict(os.environ)
            build_env["HERMES_BRIGHT_BUILD"] = manifest["version"]
            build_env["SOURCE_DATE_EPOCH"] = _run(
                ["git", "show", "-s", "--format=%ct", expected_commit],
                cwd=worktree,
                capture=True,
            )
            _run(build_command, cwd=worktree, env=build_env)
            wheels = sorted(args.outdir.glob("hermes_agent-0.20.0+bright.1-*.whl"))
            if len(wheels) != 1:
                raise SystemExit(f"expected one Bright wheel, found {len(wheels)}")
            wheel = wheels[0]
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                required = {
                    "agent/bright_live.py",
                    "gateway/platforms/api_server.py",
                    "tools/mcp_tool.py",
                }
                missing = sorted(required - names)
                if missing:
                    raise SystemExit(f"Bright wheel is missing runtime files: {missing}")
                metadata_name = next(
                    (name for name in names if name.endswith(".dist-info/METADATA")),
                    "",
                )
                metadata = archive.read(metadata_name).decode("utf-8", "replace") if metadata_name else ""
                if f"Version: {manifest['version']}\n" not in metadata:
                    raise SystemExit("Bright wheel metadata has the wrong version")
            wheel_hash = _sha256(wheel)
            expected_wheel_hash = manifest.get("wheel_sha256")
            if expected_wheel_hash and wheel_hash != expected_wheel_hash:
                raise SystemExit(
                    "wheel checksum differs from the promoted artifact: "
                    f"expected {expected_wheel_hash}, got {wheel_hash}"
                )
            checksum_file = wheel.with_suffix(wheel.suffix + ".sha256")
            checksum_file.write_text(f"{wheel_hash}  {wheel.name}\n", encoding="utf-8")
            print(f"built {wheel}")
            print(f"sha256 {wheel_hash}")
            return 0
        finally:
            _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo)


if __name__ == "__main__":
    raise SystemExit(main())
