"""Render /teacher/status as one human line. Used by watch-teacher.sh."""
import json
import sys
import textwrap

PHASE = {
    "asleep": "\033[90mngu\033[0m",
    "listening": "\033[32mdang nghe\033[0m",
    "thinking": "\033[33mdang nghi\033[0m",
    "fault": "\033[31mLOI\033[0m",
}

try:
    d = json.load(sys.stdin)
except Exception:
    print("core khong tra loi")
    raise SystemExit(0)

phase = str(d.get("phase") or "?")
lop = "MO" if d.get("sessionOpen") else "chua mo"
loa = "co" if d.get("stageAudioOwner") else "CHUA (mo /classroom di)"
bits = [
    "trang thai: " + PHASE.get(phase, phase),
    "lop: " + lop,
    "bai: " + str(d.get("unitId") or "-"),
    "loa: " + loa,
]
out = "  |  ".join(bits)

say = str(d.get("lastSay") or "").strip()
if say:
    out += "\n  co noi: " + textwrap.fill(say, 96, subsequent_indent=" " * 10)

plan = str(d.get("plan") or "").strip()
if plan:
    out += "\n  \033[36mke hoach cua co:\033[0m " + textwrap.fill(
        plan, 96, subsequent_indent=" " * 18
    )

esc = d.get("escalation")
if esc:
    out += ("\n  \033[31m*** CO GOI NGUOI LON ***\033[0m " + str(esc.get("reason"))
            + "\n  " + textwrap.fill(str(esc.get("detail") or ""), 96, subsequent_indent=" " * 2))

fault = d.get("lastFault")
if fault:
    out += "\n  \033[31mloi:\033[0m " + json.dumps(fault, ensure_ascii=False)[:180]

print(out)
