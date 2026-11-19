"""Assemble the VERITAS Hugging Face Docker Space from this working tree and upload it. Re-runnable.

    .venv/bin/python scripts/build_hf_space.py                # assemble + upload (needs `hf auth login` once)
    .venv/bin/python scripts/build_hf_space.py --wait         # ... and wait until the Space is running
    .venv/bin/python scripts/build_hf_space.py --dry-run      # only list what would be uploaded
    .venv/bin/python scripts/build_hf_space.py --status       # show the Space's current stage / build log tail
    .venv/bin/python scripts/build_hf_space.py --upload-models  # (re)publish the face-swap ONNX mirror <user>/veritas-models

What goes in: every file git would commit (git ls-files --cached --others --exclude-standard) MINUS models/,
eval_data/, .venv/, dist/, _incoming, deploy/, the GitHub README.md and every video except web/samples/lab/*.mp4;
PLUS deploy/hf-space/* at the Space root (Dockerfile + the Space README, tokens filled from
../_incoming/publish.json). As a safety net, any file byte-identical to research-dataset media in
../_incoming/media/video aborts the build. Files that are on the Space but no longer in the tree are deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "hf-space"
PUBLISH = ROOT.parent / "_incoming" / "publish.json"
# FaceForensics++, Celeb-DF, Google DFD and our Wav2Lip clip: never uploaded anywhere. (The audio exhibits in the repo,
# e.g. the CC BY-SA WaveFake voice, are redistributable and stay.)
DATASET_MEDIA = ROOT.parent / "_incoming" / "media" / "video"
SPACE_NAME = "veritas"
MODELS_REPO = "veritas-models"
MODEL_CARD = DEPLOY / "model-card" / "README.md"

EXCLUDE_PREFIXES = ("models/", "eval_data/", ".venv/", "dist/", "_incoming", "deploy/", "winkit/", "_usb/", ".git/",
                    ".github/", "docs/readme/")   # GitHub-only: CI and README images
EXCLUDE_EXACT = {"README.md", ".gitignore", ".gitattributes"}   # the Space keeps its own LFS .gitattributes
VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".3gp"}
MEDIA_EXT = VIDEO_EXT | {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic",
                         ".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac"}
EXCLUDE_EXT = {".zip", ".pyc", ".part", ".log"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_publish() -> dict:
    try:
        return json.loads(PUBLISH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def allowed(rel: str) -> bool:
    if rel in EXCLUDE_EXACT or rel.startswith(EXCLUDE_PREFIXES) or "/__pycache__/" in f"/{rel}":
        return False
    ext = os.path.splitext(rel)[1].lower()
    if ext in EXCLUDE_EXT:
        return False
    if ext in VIDEO_EXT:
        return rel.startswith("web/samples/lab/") and rel.count("/") == 3 and ext == ".mp4"
    return True


def tree_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
                         check=True, capture_output=True).stdout.decode("utf-8")
    files = sorted({f for f in out.split("\0") if f})
    return [f for f in files if allowed(f) and (ROOT / f).is_file()]


def dataset_guard(files: list[str]) -> None:
    """Abort if any media file to be uploaded is byte-identical to a research-dataset clip in ../_incoming/media/video."""
    if not DATASET_MEDIA.is_dir():
        return
    by_size: dict[int, set[str]] = {}
    for p in DATASET_MEDIA.rglob("*"):
        if p.is_file() and p.suffix.lower() in MEDIA_EXT:
            by_size.setdefault(p.stat().st_size, set()).add(sha256(p))
    bad = [f for f in files if os.path.splitext(f)[1].lower() in MEDIA_EXT
           and (ROOT / f).stat().st_size in by_size and sha256(ROOT / f) in by_size[(ROOT / f).stat().st_size]]
    if bad:
        sys.exit("ABORT: these files are research-dataset media and must never be uploaded:\n  " + "\n  ".join(bad))


def fill_tokens(text: str, pub: dict, hf_user: str, space_url: str) -> str:
    vals = {"SPACE_URL": space_url, "HF_USER": hf_user, "SITE_URL": pub.get("site_url"), "SCHOOL": pub.get("school"),
            "REPO_URL": pub.get("repo_url")}
    vals = {k: v for k, v in vals.items() if isinstance(v, str) and v.strip() and "{{" not in v}
    text = text.replace("HF_USER/", f"{hf_user}/")
    out = []
    for line in text.splitlines():
        for k, v in vals.items():
            line = line.replace("{{" + k + "}}", v)
        if "{{" in line:   # value unknown: drop the parenthesis that needs it, otherwise the whole line
            line = re.sub(r"\s*\([^()]*\{\{[A-Z_]+\}\}[^()]*\)", "", line)
            if "{{" in line or not line.strip():
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def assemble(dst: Path, pub: dict, hf_user: str, space_url: str) -> list[str]:
    files = tree_files()
    dataset_guard(files)
    for rel in files:
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, out)
    for p in sorted(DEPLOY.iterdir()):
        if p.is_file():
            if p.suffix == ".md":
                (dst / p.name).write_text(fill_tokens(p.read_text(encoding="utf-8"), pub, hf_user, space_url),
                                          encoding="utf-8")
            else:
                shutil.copy2(p, dst / p.name)
            files.append(p.name)
    return files


def space_host(api, repo_id: str) -> str:
    try:
        info = api.space_info(repo_id)
        host = getattr(info, "host", None)
        if host:
            return host.rstrip("/")
        sub = getattr(info, "subdomain", None)
        if sub:
            return f"https://{sub}.hf.space"
    except Exception:  # noqa: BLE001
        pass
    return "https://" + re.sub(r"[^a-z0-9-]", "-", repo_id.lower().replace("/", "-")) + ".hf.space"


def log_tail(repo_id: str, kind: str = "build", seconds: float = 8.0, n: int = 40) -> list[str]:
    """Last lines of the Space's build or run log (server-sent events; read for a few seconds)."""
    import requests
    from huggingface_hub import get_token

    lines: list[str] = []
    try:
        with requests.get(f"https://huggingface.co/api/spaces/{repo_id}/logs/{kind}", stream=True, timeout=15,
                          headers={"Authorization": f"Bearer {get_token()}"}) as r:
            t0 = time.monotonic()
            for raw in r.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data:"):
                    try:
                        lines.append(json.loads(raw[5:]).get("data", "").rstrip())
                    except Exception:  # noqa: BLE001
                        lines.append(raw[5:].strip())
                if time.monotonic() - t0 > seconds:
                    break
    except Exception as e:  # noqa: BLE001
        lines.append(f"(could not read the {kind} log: {e})")
    return lines[-n:]


def wait_running(api, repo_id: str, timeout_s: int) -> str:
    t0, last = time.monotonic(), None
    while time.monotonic() - t0 < timeout_s:
        try:
            stage = api.get_space_runtime(repo_id).stage
        except Exception as e:  # noqa: BLE001
            stage = f"unknown ({e})"
        if stage != last:
            print(f"  [{time.monotonic() - t0:5.0f} s] stage: {stage}", flush=True)
            last = stage
        if stage == "RUNNING":
            return stage
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"):
            kind = "build" if stage != "RUNTIME_ERROR" else "run"
            print(f"\n--- last lines of the {kind} log ---")
            print("\n".join(log_tail(repo_id, kind)))
            return stage
        time.sleep(20)
    return f"TIMEOUT (last stage {last})"


def upload_models(api, hf_user: str) -> None:
    """Publish the face-swap ONNX mirror: ONLY our verified exports of MIT-licensed weights (download_models.py
    MIRROR_FILES), each SHA-256 checked against download_models.py first, plus the model card."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import download_models as dm

    repo_id = f"{hf_user}/{MODELS_REPO}"
    src = ROOT / "models" / "face_swap"
    for fn in dm.MIRROR_FILES:
        want = dm.FACESWAP_FILES[fn]["sha256"]
        got = sha256(src / fn) if (src / fn).exists() else "missing"
        if got != want:
            sys.exit(f"ABORT: models/face_swap/{fn} is {got[:12]}..., expected {want[:12]}... - not uploading")
        print(f"  verified {fn}  {want}")
    api.create_repo(repo_id, repo_type="model", private=False, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="veritas-models-") as tmp:
        t = Path(tmp)
        (t / "README.md").write_text(MODEL_CARD.read_text(encoding="utf-8"), encoding="utf-8")
        for fn in dm.MIRROR_FILES:   # hard links: no 1.8 GB copy
            try:
                os.link(src / fn, t / fn)
            except OSError:
                shutil.copy2(src / fn, t / fn)
        remote = set(api.list_repo_files(repo_id))
        stale = sorted(f for f in remote - {"README.md", *dm.MIRROR_FILES} if f != ".gitattributes")
        print(f"Uploading to https://huggingface.co/{repo_id} ...", flush=True)
        api.upload_folder(folder_path=str(t), repo_id=repo_id, repo_type="model",
                          commit_message="VERITAS face-swap ONNX mirror (verified exports, SHA-256 in the card)",
                          delete_patterns=stale or None)
    print(f"Done: https://huggingface.co/{repo_id}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="Space id (default: <hf_user>/veritas, hf_user from publish.json or `hf auth whoami`)")
    ap.add_argument("--dry-run", action="store_true", help="assemble and list the files, do not upload")
    ap.add_argument("--keep", help="assemble into this folder (kept) instead of a temporary one")
    ap.add_argument("--wait", action="store_true", help="after uploading, wait until the Space is RUNNING")
    ap.add_argument("--wait-minutes", type=int, default=45)
    ap.add_argument("--status", action="store_true", help="only print the Space's stage and recent build log")
    ap.add_argument("--upload-models", action="store_true", help="only (re)publish the face-swap ONNX model mirror")
    a = ap.parse_args()

    pub = load_publish()
    hf_user = pub.get("hf_user") if isinstance(pub.get("hf_user"), str) and "{{" not in pub.get("hf_user", "{{") else None
    api = None
    if not a.dry_run or not hf_user:
        try:
            from huggingface_hub import HfApi

            api = HfApi()
            hf_user = hf_user or api.whoami()["name"]
        except Exception as e:  # noqa: BLE001
            if not a.dry_run:
                sys.exit(f"Not logged in to Hugging Face ({e}). Run: .venv/bin/hf auth login")
            hf_user = hf_user or "HF_USER"
    repo_id = a.repo or f"{hf_user}/{SPACE_NAME}"
    if a.upload_models:
        upload_models(api, hf_user)
        return
    if a.status:
        try:
            rt = api.get_space_runtime(repo_id)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"{repo_id}: no such Space or no access ({e})")
        print(f"{repo_id}: {rt.stage}  hardware={rt.hardware}")
        print("\n".join(log_tail(repo_id, "build" if rt.stage != "RUNNING" else "run")))
        return
    space_url = space_host(api, repo_id) if api else f"https://{hf_user.lower()}-{SPACE_NAME}.hf.space"

    work = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="veritas-space-"))
    if work.exists() and a.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        files = assemble(work, pub, hf_user, space_url)
        size = sum((work / f).stat().st_size for f in files)
        print(f"Space folder: {len(files)} files, {size / 1e6:.1f} MB  ({work})")
        vids = [f for f in files if os.path.splitext(f)[1].lower() in VIDEO_EXT]
        print(f"  videos included: {vids}")
        if a.dry_run:
            for f in files:
                print("   ", f)
            return

        from huggingface_hub import HfApi

        api = api or HfApi()
        try:
            api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            if getattr(getattr(e, "response", None), "status_code", None) == 402 or "402" in str(e):
                sys.exit(f"Hugging Face refused to create the Docker Space {repo_id} (HTTP 402): Docker Spaces on "
                         f"cpu-basic now need a PRO subscription on the account that owns them "
                         f"(https://huggingface.co/pro). Subscribe, then re-run this command. Nothing was uploaded.")
            raise
        try:
            remote = set(api.list_repo_files(repo_id, repo_type="space"))
        except Exception:  # noqa: BLE001
            remote = set()
        stale = sorted(f for f in remote - set(files) if f != ".gitattributes")
        if stale:
            print(f"  deleting {len(stale)} file(s) no longer in the tree: {stale[:8]}{' ...' if len(stale) > 8 else ''}")
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip() or "?"
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                    text=True).stdout.strip())
        print(f"Uploading to https://huggingface.co/spaces/{repo_id} ...", flush=True)
        api.upload_folder(folder_path=str(work), repo_id=repo_id, repo_type="space",
                          commit_message=f"VERITAS from {rev}{' + working tree' if dirty else ''}",
                          delete_patterns=stale or None)
        space_url = space_host(api, repo_id)
        print(f"Uploaded. Space page: https://huggingface.co/spaces/{repo_id}\n          App URL:    {space_url}")
        print("  (web/js/config.js onlineApi and publish.json space_url must equal the App URL)")
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    if a.wait:
        print("Waiting for the Space to build and start (a full rebuild takes about 10-20 minutes) ...")
        stage = wait_running(api, repo_id, a.wait_minutes * 60)
        print(f"Final stage: {stage}")
        sys.exit(0 if stage == "RUNNING" else 1)


if __name__ == "__main__":
    main()
