"""Download every model VERITAS needs into models/ (run ONCE with internet; the fair runs offline).

    uv run python scripts/download_models.py          # from the veritas/ folder
    uv run python scripts/download_models.py --check  # just verify what is installed

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
    print(f"  total {total / 1e6:.0f} MB")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check() else 1)
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    print("VERITAS model download -> models/")
    for role, spec in HF_MODELS.items():
        fetch_hf(role, spec)
    for rel, spec in URL_MODELS.items():
        fetch_url(rel, spec)
    shutil.rmtree(TMP_CACHE, ignore_errors=True)
    print()
    ok = check()
    print("\nAll models installed - the lab can now run offline." if ok else "\nSome models are missing - re-run with internet.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
