"""Model selection experiment: score every candidate detector on the CALIBRATION split only, in two
conditions (files as found, and 'laundered' = identical JPEG q90 re-encode without metadata).
The winner per role is what scripts/download_models.py installs. Held-out test files are never used here.

    uv run python scripts/compare_models.py --kind image   # candidates must be in the HF cache
    uv run python scripts/compare_models.py --kind audio

Writes eval_data/model_selection_<kind>.json and prints a table (copied into docs/MODEL_SELECTION.md).
"""
from __future__ import annotations

import argparse
import io
import json
import time

import numpy as np
from PIL import Image

from evalcommon import EVAL, launder, load_items, roc_auc

IMAGE_CANDIDATES = [
    "buildborderless/CommunityForensics-DeepfakeDet-ViT",
    "prithivMLmods/Deep-Fake-Detector-v2-Model",
    "dima806/deepfake_vs_real_image_detection",
    "prithivMLmods/open-deepfake-detection",
    "Wvolf/ViT_Deepfake_Detection",
    "Organika/sdxl-detector",
    "umm-maybe/AI-image-detector",
    "Ateeqq/ai-vs-human-image-detector",
    "dima806/ai_vs_human_generated_image_detection",
    "haywoodsloan/ai-image-detector-deploy",
    "Smogy/SMOGY-Ai-images-detector",
    "aaronkantrowitz/ai-image-detection",
]
AUDIO_CANDIDATES = [
    "MelodyMachine/Deepfake-audio-detection-V2",
    "mo-thecreator/Deepfake-audio-detection",
    "abhishtagatya/wav2vec2-base-960h-itw-deepfake",
    "Vansh180/deepfake-audio-wav2vec2",
    "DavidCombei/wavLM-base-Deepfake_V2",
    "garystafford/wav2vec2-deepfake-voice-detector",
    "Gustking/wav2vec2-large-xlsr-deepfake-audio-classification",
]


def snapshot(repo: str):
    from huggingface_hub import snapshot_download

    from pathlib import Path

    return Path(snapshot_download(repo, local_files_only=True))


def size_mb(folder) -> float:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file() and p.suffix in (".safetensors", ".bin")) / 1e6


def run_images(split: str):
    from server.models import FaceDetector, ImageClassifier, face_crop

    items = [it for it in load_items("images") if split == "all" or it["split"] == split]
    print(f"{len(items)} images ({sum(i['y'] for i in items)} fake) in split={split}")
    det = FaceDetector()
    # preload images + face crops once
    data = []
    for it in items:
        raw = it["path"].read_bytes()
        lau = launder(raw)
        im_o = Image.open(io.BytesIO(raw)).convert("RGB")
        im_l = Image.open(io.BytesIO(lau)).convert("RGB")
        faces = det.detect(np.asarray(im_l))
        crops_l = [Image.fromarray(face_crop(np.asarray(im_l), f["box"])) for f in faces[:3]]
        crops_o = [Image.fromarray(face_crop(np.asarray(im_o), f["box"])) for f in faces[:3]]
        data.append((it, im_o, im_l, crops_o, crops_l))
    print("faces found in", sum(1 for d in data if d[3]), "images")
    results = {}
    for repo in IMAGE_CANDIDATES:
        try:
            folder = snapshot(repo)
            clf = ImageClassifier(folder, repo)
        except Exception as e:  # noqa: BLE001
            print("skip", repo, e)
            continue
        t0 = time.perf_counter()
        whole_o = clf.predict([d[1] for d in data])
        whole_l = clf.predict([d[2] for d in data])
        t_whole = (time.perf_counter() - t0) / (2 * len(data)) * 1000
        face_o, face_l = [], []
        for d in data:
            face_o.append(max(clf.predict(d[3])) if d[3] else np.nan)
            face_l.append(max(clf.predict(d[4])) if d[4] else np.nan)
        y = np.array([d[0]["y"] for d in data])
        groups = np.array([d[0]["group"] for d in data])
        hasface = np.array([bool(d[3]) for d in data])
        res = {
            "size_mb": round(size_mb(folder)), "ms_per_image": round(t_whole),
            "auc_whole_orig": roc_auc(y, whole_o), "auc_whole_laund": roc_auc(y, whole_l),
            "auc_face_orig": roc_auc(y[hasface], np.array(face_o)[hasface]),
            "auc_face_laund": roc_auc(y[hasface], np.array(face_l)[hasface]),
            "acc50_whole_laund": float(((np.array(whole_l) > 0.5) == y).mean()),
            "mean_p_real_laund": float(np.mean(np.array(whole_l)[y == 0])),
            "mean_p_fake_laund": float(np.mean(np.array(whole_l)[y == 1])),
        }
        # per-group detection rate in the laundered condition
        res["per_group_mean_p"] = {g: round(float(np.mean(np.array(whole_l)[groups == g])), 3) for g in sorted(set(groups))}
        results[repo] = res
        print(f"{repo:55s} size={res['size_mb']:4d}MB {res['ms_per_image']:4d}ms  whole o/l={res['auc_whole_orig']:.3f}/{res['auc_whole_laund']:.3f}"
              f"  face o/l={res['auc_face_orig']:.3f}/{res['auc_face_laund']:.3f}  pReal={res['mean_p_real_laund']:.2f} pFake={res['mean_p_fake_laund']:.2f}", flush=True)
        print("     ", res["per_group_mean_p"], flush=True)
        del clf
    (EVAL / f"model_selection_images_{split}.json").write_text(json.dumps(results, indent=1))


def run_audio(split: str):
    from server.audio_io import load_audio
    from server.models import AudioClassifier

    items = [it for it in load_items("audio") if split == "all" or it["split"] == split]
    print(f"{len(items)} clips ({sum(i['y'] for i in items)} fake) in split={split}")
    waves = []
    for it in items:
        a = load_audio(it["path"].read_bytes(), it["name"])
        waves.append(a["wav16"])
    results = {}
    for repo in AUDIO_CANDIDATES:
        try:
            clf = AudioClassifier(snapshot(repo))
        except Exception as e:  # noqa: BLE001
            print("skip", repo, e)
            continue
        t0 = time.perf_counter()
        scores = [float(np.mean(clf.predict_windows(w)[1])) for w in waves]
        ms = (time.perf_counter() - t0) / len(waves) * 1000
        y = np.array([it["y"] for it in items])
        groups = np.array([it["group"] for it in items])
        res = {"auc": roc_auc(y, scores), "ms_per_clip": round(ms), "size_mb": round(size_mb(snapshot(repo))),
               "acc50": float(((np.array(scores) > 0.5) == y).mean()),
               "per_group_mean_p": {g: round(float(np.mean(np.array(scores)[groups == g])), 3) for g in sorted(set(groups))}}
        results[repo] = res
        print(f"{repo:55s} AUC={res['auc']:.3f} acc50={res['acc50']:.2f} {res['ms_per_clip']}ms  {res['per_group_mean_p']}", flush=True)
        del clf
    (EVAL / f"model_selection_audio_{split}.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="image")
    ap.add_argument("--split", default="calib")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    if a.only:
        AUDIO_CANDIDATES[:] = [c for c in AUDIO_CANDIDATES if a.only in c]
        IMAGE_CANDIDATES[:] = [c for c in IMAGE_CANDIDATES if a.only in c]
    (run_images if a.kind.startswith("image") else run_audio)(a.split)
