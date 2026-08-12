#!/usr/bin/env python3
"""SP-4 — measure what Bright actually costs, so the hardware SKU is a
measurement and not a guess.

    ./scripts/measure-budget.py --minutes 10
    ./scripts/measure-budget.py --minutes 10 --ports speech=18001,core=18004,ui=13000

Reports, per service and for the whole box:

  RSS      resident set size. The number everyone quotes. It DOUBLE COUNTS
           shared pages, and Chromium is ~20 processes sharing one binary and
           one GPU buffer, so summing RSS over-states the truth by a lot.
  PSS      proportional set size: shared pages divided by the number of
           processes sharing them. Summing PSS across every process is the
           honest answer to "how much RAM does this need".
  peak     VmHWM, the high-water mark of RSS. This is what a spec must cover,
           because the machine has to survive the worst moment of the lesson,
           not the average one.
  swap     any non-zero value here means the box is already too small: a page
           fault into swap during a spoken response is audible.
  CPU      per-service share of one core.

Sampling is done by reading /proc directly. No psutil, no pip install: this
has to run on an appliance in a school with no internet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PAGE = os.sysconf("SC_PAGE_SIZE")
HZ = os.sysconf("SC_CLK_TCK")


def pid_on_port(port: int) -> int | None:
    out = subprocess.run(["ss", "-lptn", f"sport = :{port}"],
                         capture_output=True, text=True).stdout
    m = re.search(r"pid=(\d+)", out)
    return int(m.group(1)) if m else None


def children_of(root: int) -> list[int]:
    """Whole process tree. Chromium is a tree; a browser measured by its main
    process only is off by an order of magnitude."""
    kids = {root}
    changed = True
    ppid = {}
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat = (p / "stat").read_text()
            ppid[int(p.name)] = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            pass
    while changed:
        changed = False
        for pid, parent in ppid.items():
            if parent in kids and pid not in kids:
                kids.add(pid)
                changed = True
    return sorted(kids)


def proc_mem(pid: int) -> dict[str, int]:
    """kB. Uses smaps_rollup for PSS; falls back to RSS-only if unreadable."""
    out = {"rss": 0, "pss": 0, "swap": 0, "peak": 0}
    try:
        for line in (Path(f"/proc/{pid}/status")).read_text().splitlines():
            if line.startswith("VmRSS:"):
                out["rss"] = int(line.split()[1])
            elif line.startswith("VmHWM:"):
                out["peak"] = int(line.split()[1])
            elif line.startswith("VmSwap:"):
                out["swap"] = int(line.split()[1])
    except OSError:
        return out
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
            if line.startswith("Pss:"):
                out["pss"] = int(line.split()[1])
            elif line.startswith("SwapPss:"):
                out["swap"] = max(out["swap"], int(line.split()[1]))
    except OSError:
        out["pss"] = out["rss"]
    return out


def proc_cpu(pid: int) -> float:
    try:
        f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(f[11]) + int(f[12])) / HZ          # utime + stime, seconds
    except (OSError, IndexError, ValueError):
        return 0.0


def sysmem() -> dict[str, int]:
    d = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        d[k] = int(v.split()[0])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--ports", default="speech=8001,core=8004,hermes=8642,ui=3000")
    ap.add_argument("--browser-port", type=int, default=0,
                    help="devtools port, to locate the kiosk process tree")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    targets: dict[str, int] = {}
    for pair in args.ports.split(","):
        name, _, port = pair.partition("=")
        pid = pid_on_port(int(port))
        if pid:
            targets[name] = pid
        else:
            print(f"  (not running: {name} on :{port})", file=sys.stderr)
    if args.browser_port:
        pid = pid_on_port(args.browser_port)
        if pid:
            targets["kiosk"] = pid

    if not targets:
        print("nothing to measure", file=sys.stderr)
        return 2
    print(f"measuring {', '.join(f'{k}(pid {v})' for k, v in targets.items())} "
          f"for {args.minutes} min\n", file=sys.stderr)

    samples: list[dict] = []
    cpu0 = {n: sum(proc_cpu(p) for p in children_of(r)) for n, r in targets.items()}
    t0 = time.monotonic()
    end = t0 + args.minutes * 60
    while time.monotonic() < end:
        row: dict = {"t": round(time.monotonic() - t0, 1), "svc": {}}
        for name, root in targets.items():
            pids = children_of(root)
            agg = {"rss": 0, "pss": 0, "swap": 0, "peak": 0, "n": len(pids)}
            for p in pids:
                m = proc_mem(p)
                agg["rss"] += m["rss"]
                agg["pss"] += m["pss"]
                agg["swap"] += m["swap"]
                agg["peak"] += m["peak"]
            agg["cpu_s"] = sum(proc_cpu(p) for p in pids)
            row["svc"][name] = agg
        mi = sysmem()
        row["sys"] = {
            "used": mi["MemTotal"] - mi["MemAvailable"],
            "avail": mi["MemAvailable"],
            "swap_used": mi["SwapTotal"] - mi["SwapFree"],
            "cached": mi["Cached"],
        }
        samples.append(row)
        time.sleep(args.interval)

    elapsed = samples[-1]["t"] - samples[0]["t"] if len(samples) > 1 else 1.0

    def mb(kb: float) -> str:
        return f"{kb/1024:7.0f}"

    print("\n" + "=" * 78)
    print(f"RESOURCE BUDGET — {len(samples)} samples over {elapsed/60:.1f} min")
    print("=" * 78)
    print(f"{'service':<10}{'procs':>6}{'RSS avg':>10}{'PSS avg':>10}"
          f"{'PSS max':>10}{'peak RSS':>10}{'swap':>8}{'CPU':>8}")
    print(f"{'':<10}{'':>6}{'MB':>10}{'MB':>10}{'MB':>10}{'MB':>10}{'MB':>8}{'cores':>8}")
    print("-" * 78)
    tot_pss_avg = tot_pss_max = tot_peak = tot_swap = 0.0
    for name in targets:
        rows = [s["svc"][name] for s in samples]
        rss_avg = sum(r["rss"] for r in rows) / len(rows)
        pss_avg = sum(r["pss"] for r in rows) / len(rows)
        pss_max = max(r["pss"] for r in rows)
        peak = max(r["peak"] for r in rows)
        swap = max(r["swap"] for r in rows)
        cpu = (rows[-1]["cpu_s"] - cpu0[name]) / elapsed
        nproc = max(r["n"] for r in rows)
        tot_pss_avg += pss_avg
        tot_pss_max += pss_max
        tot_peak += peak
        tot_swap += swap
        print(f"{name:<10}{nproc:>6}{mb(rss_avg):>10}{mb(pss_avg):>10}"
              f"{mb(pss_max):>10}{mb(peak):>10}{mb(swap):>8}{cpu:>8.2f}")
    print("-" * 78)
    print(f"{'TOTAL':<10}{'':>6}{'':>10}{mb(tot_pss_avg):>10}"
          f"{mb(tot_pss_max):>10}{mb(tot_peak):>10}{mb(tot_swap):>8}")

    sys_used = [s["sys"]["used"] for s in samples]
    sys_swap = [s["sys"]["swap_used"] for s in samples]
    print(f"\nwhole machine   used {min(sys_used)/1024:.0f}–{max(sys_used)/1024:.0f} MB"
          f"   swap in use {min(sys_swap)/1024:.0f}–{max(sys_swap)/1024:.0f} MB")
    print("NOTE: 'whole machine' includes everything else on this box. On an\n"
          "      appliance only the TOTAL row plus the OS itself is present.")

    if args.out:
        Path(args.out).write_text(json.dumps(samples))
        print(f"\nraw samples -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
