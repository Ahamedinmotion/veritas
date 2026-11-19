"""Build dist/VERITAS-Windows.zip - the one download a non-technical teammate needs.

    python scripts/build_release_zip.py            (any Python 3.9+, standard library only; needs git)

Layout (the names are a contract with the guide PDF, the README and the GitHub Actions test):
    VERITAS/1 - SETUP (run once).bat       <- scripts/release/1 - SETUP (run once).bat
    VERITAS/2 - START VERITAS.bat          <- scripts/release/2 - START VERITAS.bat
    VERITAS/VERITAS Guide.pdf              <- dist/VERITAS-Guide.pdf (only if it exists)
    VERITAS/app/...                        <- the app: git ls-files --cached --others --exclude-standard, minus the
                                              exclusions below
Never in the zip: models/ (downloaded by setup), eval_data/, .venv/, dist/, deploy/, winkit/, _incoming, .github/,
and anything named like a research-dataset clip (ffpp_, celebdf_, dfd_, wav2lip): those datasets may not be
redistributed - setup re-creates the booth clips from their public mirrors (scripts/fetch_demo_clips.py).
Every .bat gets CRLF line endings (cmd.exe misreads labels in LF files) and must be pure ASCII.
"""
from __future__ import annotations

import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "VERITAS-Windows.zip"
TOP = "VERITAS"
LAUNCHERS = ["1 - SETUP (run once).bat", "2 - START VERITAS.bat"]
GUIDE_SRC, GUIDE_NAME = ROOT / "dist" / "VERITAS-Guide.pdf", "VERITAS Guide.pdf"
EXCLUDE_DIRS = ("models/", "eval_data/", ".venv/", "dist/", "deploy/", "winkit/", "_incoming", ".github/",
                "scripts/release/", "demo-clips/")
RESEARCH_TOKENS = ("ffpp_", "celebdf_", "dfd_", "wav2lip")   # research-dataset clip names: never shipped
MAX_FILE_MB = 60   # anything bigger is almost certainly a model or a dataset by mistake


def git_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
                         check=True, capture_output=True).stdout
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def is_research(rel: str) -> bool:
    low = rel.lower()
    return any(t in low for t in RESEARCH_TOKENS)


def crlf_ascii(path: Path) -> bytes:
    data = path.read_bytes()
    try:
        data.decode("ascii")
    except UnicodeDecodeError as e:
        raise SystemExit(f"ERROR: {path.relative_to(ROOT)} is not pure ASCII ({e}) - cmd.exe would misread it")
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def main() -> int:
    files, skipped, research = [], [], []
    for rel in git_files():
        if rel.startswith(EXCLUDE_DIRS):
            skipped.append(rel)
            continue
        if is_research(rel):
            research.append(rel)
            continue
        p = ROOT / rel
        if not p.is_file():          # deleted in the working tree but still in the index
            continue
        if p.stat().st_size > MAX_FILE_MB * 1024 * 1024:
            raise SystemExit(f"ERROR: {rel} is {p.stat().st_size / 1e6:.0f} MB - too big for the app zip. "
                             "Models are downloaded by setup; add it to the exclusions if this is intended.")
        files.append(rel)
    for name in LAUNCHERS:
        if not (ROOT / "scripts" / "release" / name).is_file():
            raise SystemExit(f"ERROR: scripts/release/{name} is missing")
    for need in ("scripts/setup_windows.bat", "scripts/start_windows.bat", "scripts/download_models.py",
                 "scripts/fetch_demo_clips.py", "scripts/selftest.py", "scripts/assets/veritas.ico",
                 "server/app.py", "web/index.html", "web/lab.html", "pyproject.toml", "uv.lock"):
        if need not in files:
            raise SystemExit(f"ERROR: {need} would be missing from the zip (not tracked by git and not untracked?)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".zip.part")
    now = time.localtime()[:6]

    def add(zf: zipfile.ZipFile, arc: str, data: bytes) -> None:
        zi = zipfile.ZipInfo(arc, date_time=now)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        zf.writestr(zi, data, compresslevel=9)

    with zipfile.ZipFile(tmp, "w") as zf:
        for name in LAUNCHERS:
            add(zf, f"{TOP}/{name}", crlf_ascii(ROOT / "scripts" / "release" / name))
        if GUIDE_SRC.is_file():
            add(zf, f"{TOP}/{GUIDE_NAME}", GUIDE_SRC.read_bytes())
        for rel in files:
            p = ROOT / rel
            data = crlf_ascii(p) if rel.lower().endswith((".bat", ".cmd")) else p.read_bytes()
            add(zf, f"{TOP}/app/{rel}", data)
    tmp.replace(OUT)

    # ---- check what was written
    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        bad = [n for n in names if is_research(n) or "/app/models/" in n or n.lower().endswith((".onnx", ".safetensors"))]
        if bad:
            OUT.unlink()
            raise SystemExit(f"ERROR: forbidden files in the zip: {bad[:5]}")
        for n in names:
            if n.lower().endswith(".bat"):
                d = zf.read(n)
                if b"\n" in d.replace(b"\r\n", b""):
                    raise SystemExit(f"ERROR: {n} has LF-only lines")
        for name in LAUNCHERS:
            assert f"{TOP}/{name}" in names
    size = OUT.stat().st_size / 1e6
    print(f"wrote {OUT.relative_to(ROOT)}  ({size:.1f} MB, {len(names)} files)")
    print(f"  {TOP}/{LAUNCHERS[0]}\n  {TOP}/{LAUNCHERS[1]}")
    print(f"  {TOP}/{GUIDE_NAME}" if GUIDE_SRC.is_file() else f"  (no {GUIDE_SRC.relative_to(ROOT)} yet - zip has no guide PDF)")
    print(f"  {TOP}/app/  ({len(files)} files)")
    if research:
        print(f"  left out {len(research)} research-clip-like file(s): {', '.join(research[:5])}")
    print(f"  left out {len(skipped)} file(s) under {', '.join(sorted({s.split('/')[0] + '/' for s in skipped}))}"
          if skipped else "  nothing under the excluded folders was tracked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
