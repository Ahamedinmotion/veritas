"""Rebuild the face-swap detector's ONNX files from the PUBLISHED weights (pinned URLs + SHA-256), then check them
numerically against the files we benchmarked. Called by scripts/download_models.py only when models/face_swap/ is
missing and no verified copy (USB stick / ../_incoming) is available. Needs internet once.

    uv run --with onnx==1.23.2 --with timm==1.0.31 python scripts/export_faceswap_onnx.py gend b7
    (onnx = the exporter, timm = the EfficientNet-B7 architecture; neither is needed to RUN the engine)

With the locked torch 2.15.0 both rebuilt files were byte-identical to the benchmarked ones (SHA-256, 19 Nov 2026).

Why export at all: ONNX Runtime runs both networks 1.1x (ViT-L) to 6x (EfficientNet-B7 on macOS) faster than PyTorch on
a CPU and gives the same outputs (logits within 2.4e-6 / 5e-7 of PyTorch in the benchmark). An exported file is not
byte-identical across PyTorch versions, so instead of a SHA-256 the result is checked on fixed inputs against reference
logits recorded from the verified files (tolerance 2e-3 in logit units).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("VERITAS_FACESWAP_EXPORT_DIR", ROOT / "models" / "face_swap"))
CACHE = Path(os.environ.get("VERITAS_DOWNLOAD_CACHE", ROOT / "models" / ".download_cache"))

UPSTREAM = {
    "gend": {   # GenD (Yermakov, Cech, Matas, Fritz, WACV 2026), MIT, trained on FaceForensics++ train
        "url": "https://huggingface.co/yermandy/GenD_CLIP_L_14/resolve/891ce014a0308386c4d7d25b3dcf436a22db5504/model.safetensors",
        "sha256": "d76f0bdfd74a29fe1b1c1b84a80ac92486993e426878e8c7a3944281fbb96833",
        "file": "gend_model.safetensors",
    },
    "b7": {     # DFDC 1st place (Selim Seferbekov 2020), MIT, trained on the DFDC training set; 1 of its 7 checkpoints
        "url": "https://github.com/selimsef/dfdc_deepfake_challenge/releases/download/0.0.1/"
               "final_999_DeepFakeClassifier_tf_efficientnet_b7_ns_0_23",
        "sha256": "849036dc211387420412feb68c7451e98a948072b94e213e1104e2f2bf7791ad",
        "file": "final_999_DeepFakeClassifier_tf_efficientnet_b7_ns_0_23",
    },
}
# CLIP ViT-L/14 vision tower (openai/clip-vit-large-patch14 config.json, vision part; MIT). No OpenAI weights are
# downloaded: every weight comes from GenD's safetensors.
CLIP_VISION = {"hidden_size": 1024, "intermediate_size": 4096, "projection_dim": 768, "num_hidden_layers": 24,
               "num_attention_heads": 16, "num_channels": 3, "image_size": 224, "patch_size": 14,
               "hidden_act": "quick_gelu", "layer_norm_eps": 1e-5, "attention_dropout": 0.0}
REF_FILE = Path(__file__).resolve().parent / "faceswap_onnx_reference.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(key: str) -> Path:
    spec = UPSTREAM[key]
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / spec["file"]
    if out.exists() and sha256(out) == spec["sha256"]:
        return out
    print(f"  downloading {spec['url']} ...", flush=True)
    req = urllib.request.Request(spec["url"], headers={"User-Agent": "veritas-setup/1.0"})
    tmp = out.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    tmp.replace(out)
    if sha256(out) != spec["sha256"]:
        out.unlink()
        raise RuntimeError(f"checksum mismatch for {spec['url']}")
    return out


def ref_inputs(kind: str) -> list[np.ndarray]:
    side = 224 if kind == "gend" else 380
    rng = np.random.default_rng(20261121)
    return [rng.normal(0, 1, (1, 3, side, side)).astype(np.float32) for _ in range(2)]


def onnx_outputs(path: Path, kind: str) -> list[list[float]]:
    import onnxruntime as ort
    s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    name = s.get_inputs()[0].name
    return [s.run(None, {name: x})[0].ravel().astype(float).tolist() for x in ref_inputs(kind)]


def check(path: Path, kind: str, tol: float = 2e-3) -> float:
    ref = json.loads(REF_FILE.read_text())[kind]
    got = onnx_outputs(path, kind)
    d = float(np.max(np.abs(np.array(got) - np.array(ref))))
    if d > tol:
        raise RuntimeError(f"{path.name}: outputs differ from the benchmarked file by {d:.2e} (> {tol}) - not used")
    return d


def export_gend(out: Path):
    import torch
    from safetensors.torch import load_file
    from transformers import CLIPVisionConfig, CLIPVisionModel

    sd = load_file(str(fetch("gend")))
    vision = CLIPVisionModel(CLIPVisionConfig(**CLIP_VISION)).vision_model
    vis = {k[len("feature_extractor.vision_model."):]: v for k, v in sd.items()
           if k.startswith("feature_extractor.vision_model.")}
    missing, unexpected = vision.load_state_dict(vis, strict=False)
    missing = [k for k in missing if not k.endswith("position_ids")]
    assert not missing and not unexpected, (missing, unexpected)
    head = torch.nn.Linear(sd["model.linear.weight"].shape[1], 2)
    head.load_state_dict({"weight": sd["model.linear.weight"], "bias": sd["model.linear.bias"]})

    class Wrap(torch.nn.Module):   # GenD: pooler_output -> L2 normalise -> Linear(1024, 2)
        def __init__(self, v, h):
            super().__init__()
            self.v, self.h = v, h

        def forward(self, px):
            f = torch.nn.functional.normalize(self.v(pixel_values=px).pooler_output, p=2, dim=1)
            return self.h(f)

    net = Wrap(vision, head).eval()
    x = torch.from_numpy(ref_inputs("gend")[0])
    torch.onnx.export(net, (x,), str(out), input_names=["x"], output_names=["y"], opset_version=17, dynamo=False)


def export_b7(out: Path):
    import re

    import timm
    import torch
    from torch import nn

    class DeepFakeClassifier(nn.Module):   # selimsef/dfdc_deepfake_challenge training/zoo/classifiers.py
        def __init__(self):
            super().__init__()
            self.encoder = timm.create_model("tf_efficientnet_b7", pretrained=False, drop_path_rate=0.2)
            self.avg_pool = nn.AdaptiveAvgPool2d((1, 1))
            self.dropout = nn.Dropout(0.0)
            self.fc = nn.Linear(2560, 1)

        def forward(self, x):
            x = self.encoder.forward_features(x)
            return self.fc(self.dropout(self.avg_pool(x).flatten(1)))

    # the release file is a legacy pickle holding numpy scalars next to the tensors; its SHA-256 was checked above,
    # and only these numpy types are allowed besides tensors
    from numpy._core.multiarray import scalar as np_scalar   # pickled under its NumPy-1 name below
    allowed = [(np_scalar, "numpy.core.multiarray.scalar"), np.dtype] + \
              [type(np.dtype(t)) for t in ("float64", "float32", "int64")]
    with torch.serialization.safe_globals(allowed):
        ck = torch.load(fetch("b7"), map_location="cpu", weights_only=True)
    sd = ck.get("state_dict", ck)
    sd = {re.sub(r"^module\.", "", k): v for k, v in sd.items()}
    net = DeepFakeClassifier()
    net.load_state_dict(sd, strict=True)
    net.eval()
    x = torch.from_numpy(ref_inputs("b7")[0])
    torch.onnx.export(net, (x,), str(out), input_names=["x"], output_names=["y"], opset_version=17, dynamo=False)


def build(kind: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / ("gend_clip.onnx" if kind == "gend" else "dfdc_b7.onnx")
    tmp = out.with_suffix(".building.onnx")
    (export_gend if kind == "gend" else export_b7)(tmp)
    d = check(tmp, kind)
    tmp.replace(out)
    print(f"  ok  models/face_swap/{out.name} rebuilt from the published weights (max logit diff {d:.1e})")
    return out


def record_reference():
    """Maintainers only: record the reference logits from the benchmarked files in models/face_swap/."""
    src = ROOT / "models" / "face_swap"
    ref = {k: onnx_outputs(src / f, k) for k, f in (("gend", "gend_clip.onnx"), ("b7", "dfdc_b7.onnx"))}
    REF_FILE.write_text(json.dumps(ref, indent=1))
    print("wrote", REF_FILE)


if __name__ == "__main__":
    args = sys.argv[1:] or ["gend", "b7"]
    if args == ["--record-reference"]:
        record_reference()
    else:
        for k in args:
            build(k)
