"""Download every model VERITAS needs into models/ (run ONCE with internet; the fair runs offline).

    uv run python scripts/download_models.py          # from the veritas/ folder
    uv run python scripts/download_models.py --check  # just verify what is installed
    uv run python scripts/download_models.py --faceswap-from E:\\winkit\\models\\face_swap   # face-swap files from the USB kit

Sizes: the three original networks + face tools about 530 MB; the face-swap detector (models/face_swap/) about
1.5 GB (+0.3 GB for the optional int8 fallback). The face-swap ONNX files are our verified exports of published
MIT-licensed weights. Without a local copy they come from our public Hugging Face mirror (FACESWAP_MIRROR, SHA-256
checked, resumable), and only if that fails are they REBUILT from the pinned originals (scripts/export_faceswap_onnx.py).

Models were chosen by scripts/compare_models.py on our calibration split (see docs/MODEL_SELECTION.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
TMP_CACHE = MODELS / ".download_cache"

# role -> (Hugging Face repo, revision, weight file, extra notes)
HF_MODELS = {
    "ai_generated": {
        "repo": "buildborderless/CommunityForensics-DeepfakeDet-ViT",
        "revision": "ac6ee457bea904a373065754107451793b56db00",
        "files": ["config.json", "preprocessor_config.json", "model.safetensors"],
        "sha256": {"model.safetensors": "275ba982236ddd6afddf7131f8133e89f537574b964cf8fa5825b4956d741692"},
        "licence": "MIT",
        "why": "Best AUC on our calibration split (whole images and face crops); 87 MB ViT-Small; CVPR 2025.",
    },
    "face_deepfake": {
        # The same network, applied to each face crop. Face-specific classifiers on the Hub scored at chance
        # level on modern AI faces in our experiment (docs/MODEL_SELECTION.md).
        "repo": "buildborderless/CommunityForensics-DeepfakeDet-ViT",
        "revision": "ac6ee457bea904a373065754107451793b56db00",
        "files": ["config.json", "preprocessor_config.json", "model.safetensors"],
        "sha256": {"model.safetensors": "275ba982236ddd6afddf7131f8133e89f537574b964cf8fa5825b4956d741692"},
        "licence": "MIT",
        "why": "Highest face-crop AUC on our calibration split.",
    },
    "audio_deepfake": {
        "repo": "abhishtagatya/wav2vec2-base-960h-itw-deepfake",
        # pinned: the voice probe in server/calibration.json is tied to these exact layer-4 weights
        "revision": "cb2350dec8246c67a5924462659c1796214f019f",
        "files": ["config.json", "preprocessor_config.json", "model.safetensors"],
        "sha256": {"model.safetensors": "0acca7cfc4fd790b1fb7cad4017606fa93e7a0ef030f0c2e2e5d426fb91af272"},
        "licence": "Apache-2.0",
        "why": "Best AUC (0.73) of 7 audio candidates on our calibration split at base-model speed; "
               "the large XLS-R models were 10x slower and no better on our data.",
    },
}
URL_MODELS = {
    "face_detector/face_detection_yunet_2023mar.onnx": {
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "licence": "MIT (OpenCV Zoo)",
    },
    "face_landmarker/face_landmarker.task": {
        "url": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "sha256": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
        "licence": "Apache-2.0 (Google MediaPipe)",
        "local_copy": ROOT / "web" / "vendor" / "mediapipe" / "face_landmarker.task",
    },
}


# Face-swap detector (video): models/face_swap/. These exact files were benchmarked and verified
# (../_incoming/detector/BENCHMARK.md). Where they come from, in order:
#   1. already in models/face_swap/ with the right SHA-256 (the normal case: models\ is copied to the booth laptop),
#   2. a verified local copy: --faceswap-from DIR, $VERITAS_FACESWAP_SRC, winkit/models/face_swap (the offline kit),
#      ../_usb/winkit/models/face_swap, ../_usb/models/face_swap, or the benchmark's
#      ../_incoming/detector/work/deploy_models (SHA-256 checked),
#   3. rebuilt from the PUBLISHED weights at pinned URLs (SHA-256 checked) by scripts/export_faceswap_onnx.py and
#      checked numerically against the benchmarked files (an ONNX export is not byte-identical across PyTorch versions).
FACESWAP_FILES = {
    "det_10g.onnx": {   # SCRFD-10G face detector (GenD's), InsightFace buffalo_l v0.7 - byte-identical official file
        "sha256": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
        "zip_url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "zip_member": "det_10g.onnx",
        "licence": "InsightFace pretrained models: non-commercial research purposes only",
    },
    "gend_clip.onnx": {  # GenD CLIP ViT-L/14, fp32 (exact published weights), 1.21 GB
        "sha256": "371b05b7c3e66d6998313406a4d1fb5610cb195fe87634c1b1c842981364889f",
        "build": "gend", "licence": "MIT (GenD, Yermakov et al., WACV 2026); trained on FaceForensics++ (FF++ terms)",
    },
    "dfdc_b7.onnx": {    # DFDC first-place EfficientNet-B7 (one of 7 checkpoints), 255 MB
        "sha256": "6c14e1dae05a7ed999c971e581f620f7fe9f677d9e605307c006978a818bd7f1",
        "build": "b7", "licence": "MIT (Selim Seferbekov 2020); trained on the DFDC dataset (research terms)",
    },
    "gend_clip_int8.onnx": {  # OPTIONAL RAM fallback (VERITAS_FACESWAP=int8): dynamic int8 quantisation, 308 MB
        "sha256": "4234075cd6dc79e8be489944b057ba062bd4431d7417e18df1f415628c529e9e",
        "optional": True, "licence": "MIT (derived from GenD)",
    },
}
# Public mirror of OUR verified ONNX exports of the MIT-licensed weights (GenD fp32 + int8, DFDC-B7). It holds no
# other model (det_10g.onnx is InsightFace, non-commercial: always from the official zip) and no media.
# VERITAS_MODEL_MIRROR=off skips it (e.g. to test the rebuild path); VERITAS_MODEL_MIRROR=user/repo points elsewhere.
FACESWAP_MIRROR = "Ahamedinmotion42/veritas-models"
MIRROR_FILES = ("gend_clip.onnx", "dfdc_b7.onnx", "gend_clip_int8.onnx")
MIRROR_URL = "https://huggingface.co/{repo}/resolve/main/{file}"
UA = {"User-Agent": "veritas-setup/1.1"}

FACESWAP_TEXT = {   # tiny text files, written directly
    "clip_preprocessor/preprocessor_config.json": {   # openai/clip-vit-large-patch14 (MIT)
        "crop_size": 224, "do_center_crop": True, "do_normalize": True, "do_resize": True,
        "feature_extractor_type": "CLIPFeatureExtractor", "image_mean": [0.48145466, 0.4578275, 0.40821073],
        "image_std": [0.26862954, 0.26130258, 0.27577711], "resample": 3, "size": 224},
    "thresholds.json": {   # chosen on the 45 FaceForensics++ test clips ONLY (mean of 8 frames)
        "n_frames": 8, "gend": 0.812141, "dfdc": 0.6968, "pair_gend+dfdc": 0.117826, "gend_int8": 0.673306,
        "pair_gend_int8+dfdc": 0.193495,
        "_note": "FF++-chosen clip thresholds (mean of 8 evenly spaced frames; 45 FF++ c23 test clips only) from "
                 "_incoming/detector/bench_results.json, pair keys as fixed by the 19 Nov 2026 verification. Never "
                 "tuned on Celeb-DF, DFD or the demo clips."},
}


def _mb(n: float) -> str:
    return f"{n / 1e6:,.0f} MB"


def download(url: str, out: Path, want_sha: str | None = None, label: str = "", tries: int = 6) -> None:
    """Robust HTTPS download: writes <out>.part, resumes it after a dropped connection (HTTP Range), retries with
    back-off, shows progress, checks the SHA-256 and only then renames to <out>. Raises on failure."""
    import time
    import urllib.error

    label = label or out.name
    part = out.with_name(out.name + ".part")
    out.parent.mkdir(parents=True, exist_ok=True)
    tty = sys.stdout.isatty()
    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers=dict(UA, **({"Range": f"bytes={have}-"} if have else {})))
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:      # server ignored the Range header: start again
                    have = 0
                total = r.headers.get("Content-Length")
                total = int(total) + have if total and total.isdigit() else None
                got, t0, last = have, time.monotonic(), 0.0
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                        got += len(b)
                        now = time.monotonic()
                        if now - last >= (0.5 if tty else 15):
                            last = now
                            rate = (got - have) / max(now - t0, 1e-3)
                            pct = f"{100 * got / total:5.1f}%  " if total else ""
                            msg = f"    {label}: {pct}{_mb(got)}{' of ' + _mb(total) if total else ''}  ({rate / 1e6:.1f} MB/s)"
                            print(("\r" + msg.ljust(78)) if tty else msg, end="" if tty else "\n", flush=True)
                if tty:
                    print()
                if total and got < total:
                    raise urllib.error.URLError(f"connection closed at {_mb(got)} of {_mb(total)}")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 416:   # .part is already complete (or bad)
                pass
            elif isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                raise RuntimeError(f"{url} -> HTTP {e.code}") from e
            else:
                if tty:
                    print()
                wait = min(60, 5 * attempt)
                print(f"    {label}: download interrupted ({e}); retry {attempt}/{tries} in {wait} s "
                      f"(it resumes where it stopped) ...", flush=True)
                time.sleep(wait)
                continue
        if want_sha:
            got_sha = sha256(part)
            if got_sha != want_sha:
                part.unlink(missing_ok=True)
                if attempt < tries:
                    print(f"    {label}: checksum mismatch - downloading again ...", flush=True)
                    continue
                raise RuntimeError(f"checksum mismatch for {label} ({got_sha[:12]}... != {want_sha[:12]}...)")
        os.replace(part, out)
        return
    raise RuntimeError(f"could not download {label} after {tries} tries - check the internet connection and re-run")


def mirror_repo() -> str | None:
    m = os.environ.get("VERITAS_MODEL_MIRROR", FACESWAP_MIRROR).strip().strip("\"'")
    return None if m.lower() in ("", "off", "0", "none") or m.startswith("HF_USER/") else m


def fetch_from_mirror(fn: str, out: Path, spec: dict) -> bool:
    repo = mirror_repo()
    if not repo or fn not in MIRROR_FILES:
        return False
    url = MIRROR_URL.format(repo=repo, file=fn)
    print(f"  downloading face_swap/{fn} from the VERITAS model mirror (huggingface.co/{repo}) ...", flush=True)
    try:
        download(url, out, spec["sha256"], label=fn)
    except Exception as e:  # noqa: BLE001
        print(f"  note: mirror download of {fn} failed ({e}); trying the next source")
        return False
    print(f"  ok  face_swap/{fn} (from the mirror, SHA-256 verified)")
    return True


def faceswap_sources(extra: str | None) -> list[Path]:
    if os.environ.get("VERITAS_NO_LOCAL_COPIES") == "1":   # testing: force the mirror / rebuild path
        return []
    c = [extra, os.environ.get("VERITAS_FACESWAP_SRC"),
         ROOT / "winkit" / "models" / "face_swap",                       # the offline kit copied into C:\veritas\winkit
         ROOT.parent / "_usb" / "winkit" / "models" / "face_swap",       # where build_winkit.sh writes it on the Mac
         ROOT.parent / "_usb" / "models" / "face_swap",
         ROOT.parent / "_incoming" / "detector" / "work" / "deploy_models"]
    return [Path(x) for x in c if x]


def fetch_faceswap(src_dir: str | None = None) -> bool:
    """Returns False only if a REQUIRED file could not be installed."""
    import subprocess
    import zipfile

    dst = MODELS / "face_swap"
    dst.mkdir(parents=True, exist_ok=True)
    for rel, obj in FACESWAP_TEXT.items():
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            out.write_text(json.dumps(obj, indent=1))
        print(f"  ok  face_swap/{rel}")
    ok = True
    for fn, spec in FACESWAP_FILES.items():
        out = dst / fn
        if out.exists() and out.stat().st_size > 0 and sha256(out) == spec["sha256"]:
            print(f"  ok  face_swap/{fn}")
            continue
        copied = False
        for d in faceswap_sources(src_dir):
            cand = d / fn
            if cand.exists() and sha256(cand) == spec["sha256"]:
                shutil.copyfile(cand, out)
                print(f"  ok  face_swap/{fn} (copied from {d})")
                copied = True
                break
        if copied:
            continue
        if fetch_from_mirror(fn, out, spec):
            continue
        try:
            if spec.get("zip_url"):
                TMP_CACHE.mkdir(parents=True, exist_ok=True)
                z = TMP_CACHE / spec["zip_url"].rsplit("/", 1)[-1]
                if not z.exists():
                    print(f"  downloading {spec['zip_url']} (~280 MB, only {fn} is kept) ...", flush=True)
                    download(spec["zip_url"], z, None, label=z.name)
                with zipfile.ZipFile(z) as zf:
                    name = next(n for n in zf.namelist() if n.rsplit("/", 1)[-1] == spec["zip_member"])
                    out.write_bytes(zf.read(name))
                if sha256(out) != spec["sha256"]:
                    out.unlink()
                    raise RuntimeError(f"checksum mismatch for {fn} from {spec['zip_url']}")
                print(f"  ok  face_swap/{fn} (from the official InsightFace release)")
            elif spec.get("build"):
                # the ONNX export needs two packages the engine does not: onnx (exporter) and timm (B7 architecture).
                # `uv run --with` adds them in a throw-away layer; .venv stays exactly as locked. With the locked torch
                # the rebuilt files were byte-identical to the benchmarked ones (checked 19 Nov 2026).
                uv = shutil.which("uv")
                if not uv:
                    raise RuntimeError("rebuilding the face-swap files needs `uv` - copy the models/face_swap folder instead")
                cmd = [uv, "run", "--with", "onnx==1.23.2", "--with", "timm==1.0.31", "python",
                       str(ROOT / "scripts" / "export_faceswap_onnx.py"), spec["build"]]
                subprocess.run(cmd, check=True, cwd=str(ROOT))
                if sha256(out) != spec["sha256"]:
                    print(f"  note: face_swap/{fn} differs byte-wise from the benchmarked file but passed the numeric check")
            elif spec.get("optional"):
                print(f"  --  face_swap/{fn} not installed (optional RAM fallback; re-run setup with internet if wanted)")
            else:
                raise RuntimeError("no source")
        except Exception as e:  # noqa: BLE001
            if spec.get("optional"):
                print(f"  --  face_swap/{fn} skipped (optional): {e}")
            else:
                print(f"  FAILED face_swap/{fn}: {e}")
                ok = False
    return ok


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch_hf(role: str, spec: dict):
    from huggingface_hub import hf_hub_download

    dst = MODELS / role
    dst.mkdir(parents=True, exist_ok=True)
    want = spec.get("sha256", {})
    for fn in spec["files"]:
        out = dst / fn
        if out.exists() and out.stat().st_size > 0 and (fn not in want or sha256(out) == want[fn]):
            continue
        print(f"  downloading {spec['repo']}/{fn} ...", flush=True)
        # download into a temporary cache inside models/ (deleted afterwards) so no second ~460 MB copy is left
        # behind in %USERPROFILE%\.cache\huggingface
        p = hf_hub_download(spec["repo"], fn, revision=spec.get("revision"), cache_dir=str(TMP_CACHE))
        shutil.copyfile(p, out)
        if fn in want and sha256(out) != want[fn]:
            raise RuntimeError(f"checksum mismatch for models/{role}/{fn} - delete it and run setup again")
    (dst / "veritas.json").write_text(json.dumps({"repo": spec["repo"], "revision": spec.get("revision"),
                                                  "licence": spec["licence"], "why": spec["why"]}, indent=1))
    print(f"  ok  {role:15s} <- {spec['repo']}")


def fetch_url(rel: str, spec: dict):
    out = MODELS / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and sha256(out) == spec["sha256"]:
        print(f"  ok  {rel}")
        return
    src = spec.get("local_copy")
    if src and Path(src).exists() and sha256(Path(src)) == spec["sha256"]:
        shutil.copyfile(src, out)
        print(f"  ok  {rel} (copied from {Path(src).relative_to(ROOT)})")
        return
    print(f"  downloading {spec['url']} ...", flush=True)
    req = urllib.request.Request(spec["url"], headers={"User-Agent": "veritas-setup/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())
    got = sha256(out)
    if got != spec["sha256"]:
        print(f"  WARNING: checksum mismatch for {rel} ({got[:12]}...); keeping file anyway")
    print(f"  ok  {rel}")


def check() -> bool:
    ok = True
    total = 0
    for role, spec in HF_MODELS.items():
        for fn in spec["files"]:
            p = MODELS / role / fn
            present = p.exists() and p.stat().st_size > 0
            ok &= present
            total += p.stat().st_size if present else 0
            print(f"  [{'x' if present else ' '}] models/{role}/{fn}")
    for rel in URL_MODELS:
        p = MODELS / rel
        ok &= p.exists()
        total += p.stat().st_size if p.exists() else 0
        print(f"  [{'x' if p.exists() else ' '}] models/{rel}")
    for rel in list(FACESWAP_FILES) + list(FACESWAP_TEXT):
        p = MODELS / "face_swap" / rel
        opt = FACESWAP_FILES.get(rel, {}).get("optional", False)
        if not opt:
            ok &= p.exists()
        total += p.stat().st_size if p.exists() else 0
        print(f"  [{'x' if p.exists() else ' '}] models/face_swap/{rel}{'  (optional)' if opt else ''}")
    print(f"  total {total / 1e6:.0f} MB")
    return ok


def main():
    global MODELS, TMP_CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--faceswap-from", default=None, help="folder with verified face_swap model files (USB stick)")
    ap.add_argument("--models-dir", default=None, help="install into this folder instead of models/ (testing)")
    ap.add_argument("--faceswap-only", action="store_true", help="only the face-swap detector files (testing)")
    a = ap.parse_args()
    if a.models_dir:
        MODELS = Path(a.models_dir).resolve()
        TMP_CACHE = MODELS / ".download_cache"
        os.environ["VERITAS_FACESWAP_EXPORT_DIR"] = str(MODELS / "face_swap")
        os.environ["VERITAS_DOWNLOAD_CACHE"] = str(TMP_CACHE)
    if a.check:
        sys.exit(0 if check() else 1)
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    print(f"VERITAS model download -> {MODELS}")
    if a.faceswap_only:
        ok = fetch_faceswap(a.faceswap_from)
        shutil.rmtree(TMP_CACHE, ignore_errors=True)
        sys.exit(0 if ok else 1)
    for role, spec in HF_MODELS.items():
        fetch_hf(role, spec)
    for rel, spec in URL_MODELS.items():
        fetch_url(rel, spec)
    fetch_faceswap(a.faceswap_from)
    shutil.rmtree(TMP_CACHE, ignore_errors=True)
    print()
    ok = check()
    print("\nAll models installed - the lab can now run offline." if ok else "\nSome models are missing - re-run with internet.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
