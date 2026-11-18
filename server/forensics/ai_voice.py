"""Neural synthetic-speech detector (wav2vec2-family transformer fine-tuned on real vs. AI speech)."""
from __future__ import annotations

import numpy as np

from .. import charts, config
from ..models import REGISTRY
from .base import calibrated, make_test

NAME = "AI Voice Detector"
EXPLAIN = ("A wav2vec2 network, pre-trained on 960 hours of audiobook speech (LibriSpeech) and fine-tuned by its "
           "author on the In-the-Wild deepfake dataset, turns each 4-second window into 768 numbers describing its "
           "fine acoustic texture; a small logistic-regression 'probe' trained on our calibration clips reads them. "
           "It works best on voice generators like those it was tuned on - brand-new cloning tools can fool it.")


PROBE_LAYER = 4


def _active(wav16: np.ndarray, centres: list[float]) -> np.ndarray:
    """Windows that actually contain sound (silent windows carry no voice evidence)."""
    win = int(4.0 * 16000)
    rms = []
    for c in centres:
        s = int(max(0, (c - 2.0) * 16000))
        seg = wav16[s:s + win]
        rms.append(float(np.sqrt(np.mean(seg ** 2) + 1e-12)))
    rms = np.array(rms)
    if not len(rms):
        return rms.astype(bool)
    return rms > max(1e-3, 0.15 * rms.max())   # all False for a silent clip


def clip_embedding(wav16: np.ndarray, layer: int = PROBE_LAYER) -> np.ndarray:
    """Average layer-`layer` feature vector over the sounding windows (what the probe is trained on)."""
    centres, _, embs = REGISTRY.audio_deepfake.predict_windows(wav16, embed_layer=layer)
    act = _active(wav16, centres)
    return embs[act].mean(axis=0) if act.any() else embs.mean(axis=0)  # training clips always contain speech


def run(wav16: np.ndarray) -> dict:
    m = REGISTRY.audio_deepfake
    if m is None:
        return make_test("ai_voice", NAME, "ai_model", status="error", score=None,
                         finding="Voice model is not installed on this computer.", explain=EXPLAIN)
    probe = config.CALIBRATION.get("voice_probe")
    if probe:
        # transfer learning: the pretrained network's layer-N features + our logistic-regression 'probe'
        centres, head_probs, embs = m.predict_windows(wav16, embed_layer=int(probe["layer"]))
        mu, sd = np.asarray(probe["mean"]), np.asarray(probe["std"])
        coef, b = np.asarray(probe["coef"]), float(probe["intercept"])
        with np.errstate(all="ignore"):  # Apple Accelerate raises spurious FP warnings in matmul
            z = ((embs - mu) / sd) @ coef + b
        z = np.nan_to_num(z, nan=0.0)
        probs = list(1 / (1 + np.exp(-np.clip(z, -30, 30))))
    else:
        centres, probs = m.predict_windows(wav16)
        embs = None
    active = _active(wav16, centres)
    if not active.any():
        return make_test("ai_voice", NAME, "ai_model", status="skipped", score=None,
                         finding="No windows with enough sound to judge a voice.", explain=EXPLAIN,
                         metrics={"windows": len(probs)})
    pv = np.array(probs)[active]
    if probe:
        # the probe was trained on the clip-average feature vector, so score that (windows are for the chart)
        e = embs[active].mean(axis=0)
        with np.errstate(all="ignore"):
            zc = float(np.nan_to_num(((e - mu) / sd) @ coef + b))
        p = float(1 / (1 + np.exp(-np.clip(zc, -30, 30))))
    else:
        p = float(0.75 * pv.mean() + 0.25 * np.median(pv))
    score = calibrated("ai_voice", p * 100)
    win_scores = [calibrated("ai_voice", q * 100) for q in probs]
    visual = charts.bar_chart(np.array(centres), np.array(win_scores), [charts.score_color(s) for s in win_scores],
                              xlabel="time (s)", ylabel="synthetic %",
                              hlines=[(config.THRESH_SYNTHETIC, charts.SYN, "synthetic"),
                                      (config.THRESH_SUSPICIOUS, charts.AUTH, "authentic")],
                              width=1.6 if len(centres) > 1 else 1.0)
    n_fake = int(sum(s > config.THRESH_SYNTHETIC for s in win_scores))
    if score > config.THRESH_SYNTHETIC:
        finding = f"Synthetic-voice signature in {n_fake} of {len(win_scores)} windows."
    elif score >= config.THRESH_SUSPICIOUS:
        finding = "Some windows sound machine-generated; overall borderline."
    else:
        finding = "Voice texture matches natural human speech."
    return make_test("ai_voice", NAME, "ai_model", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"p_fake": p, "windows": len(probs), "windows_synthetic": n_fake,
                              "model": m.repo.split("/")[-1] + (" + probe" if probe else ""), "raw": p * 100})
