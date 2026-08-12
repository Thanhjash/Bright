"""Ports, health-waiting, and killing things safely.

The one rule that matters here: **never `pkill -f`**. The pattern matches this
process's own command line and kills the shell running the suite. Two agents
lost their shell that way during development. Everything below either kills a
PID we spawned ourselves, or resolves a PID from the port it is listening on.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

#: Ports the live demo uses. The suite must never bind or kill these.
RESERVED_PORTS = {3000, 8001, 8004, 8642}


def free_port(avoid: set[int] | None = None) -> int:
    """An unused loopback port, guaranteed not to be one the demo is using."""
    blocked = RESERVED_PORTS | (avoid or set())
    for _ in range(200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in blocked:
            return port
    raise RuntimeError("could not find a free port")


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: float = 30.0, host: str = "127.0.0.1") -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port, host):
            return True
        time.sleep(0.1)
    return False


def wait_for_port_closed(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_open(port):
            return True
        time.sleep(0.1)
    return False


def wait_for_http(url: str, timeout: float = 60.0, expect_status: int = 200) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == expect_status:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            pass
        time.sleep(0.25)
    return False


def pid_on_port(port: int) -> int | None:
    """Resolve the listening PID from the port. Never matches our own cmdline."""
    try:
        out = subprocess.run(
            ["ss", "-lptnH", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    marker = "pid="
    idx = out.find(marker)
    if idx == -1:
        return None
    tail = out[idx + len(marker) :]
    digits = ""
    for ch in tail:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else None


def kill_by_port(port: int, *, sig: int = signal.SIGTERM, timeout: float = 10.0) -> bool:
    """Kill whatever is listening on `port`. Returns True if the port freed up."""
    pid = pid_on_port(port)
    if pid is None:
        return not port_open(port)
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass
    if wait_for_port_closed(port, timeout=timeout):
        return True
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return wait_for_port_closed(port, timeout=timeout)
