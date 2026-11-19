"""Print how long each part of "1 - SETUP (run once).bat" took, from the time stamps in setup-log.txt.

    python .github/scripts/setup_timings.py <install-dir>/setup-log.txt [label]

Also appends a small table to the GitHub Actions job summary ($GITHUB_STEP_SUMMARY) when it is set.
Standard library only. Never fails the job (exit 0), it only reports.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{2})")
MARKS = [("start", re.compile(r"^VERITAS setup log - ")),
         ("1 copy", re.compile(r"^==== STEP 1 ")),
         ("2 uv + Python + libraries (download + install)", re.compile(r"^==== STEP 2 ")),
         ("3 AI models (download, SHA-256 check)", re.compile(r"^==== STEP 3 ")),
         ("4 demo clips (download + re-encode)", re.compile(r"^==== STEP 4 ")),
         ("5 library check, shortcuts, self-test", re.compile(r"^==== STEP 5 ")),
         ("end", re.compile(r"^SETUP (COMPLETE|FAILED) - "))]


def secs(line: str) -> float | None:
    m = list(TIME.finditer(line))
    if not m:
        return None
    h, mi, s, cs = (int(x) for x in m[-1].groups())
    return h * 3600 + mi * 60 + s + cs / 100


def main() -> int:
    log = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else log.parent.name
    if not log.exists():
        print(f"no setup log at {log}")
        return 0
    found: dict[str, float] = {}
    clips = ""
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        for name, rx in MARKS:
            if name not in found and rx.search(line):
                t = secs(line)
                if t is not None:
                    found[name] = t
        if "research clips ready" in line:
            clips = line.strip()
    order = [n for n, _ in MARKS if n in found]
    if len(order) < 2:
        print("could not find the time stamps in the setup log")
        return 0

    def dur(a: str, b: str) -> float:
        d = found[b] - found[a]
        return d + 86400 if d < 0 else d   # past midnight

    rows = [(order[i], dur(order[i], order[i + 1])) for i in range(len(order) - 1) if order[i] != "start"]
    total = dur(order[0], order[-1])
    dl = sum(d for n, d in rows if n[0] in "234")
    out = [f"### Setup timings ({label})", "", "| part | time |", "|---|---|"]
    out += [f"| step {n} | {d / 60:.1f} min ({d:.0f} s) |" for n, d in rows]
    out += [f"| **total setup** | **{total / 60:.1f} min ({total:.0f} s)** |",
            f"| downloads + installs (steps 2-4) | {dl / 60:.1f} min ({dl:.0f} s) |", ""]
    if clips:
        out += [f"Demo clips: `{clips}`", ""]
    text = "\n".join(out)
    print(text)
    print(f"TIMING total-setup: {total:.0f} s; steps 2-4 (downloads + installs): {dl:.0f} s")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
