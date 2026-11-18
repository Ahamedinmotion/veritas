"""Fusion: combine the individual test scores into one verdict.

How it works (the version the students explain):
  1. Every test gives a 0-100 'synthetic likelihood'. Tests that could not run (no face, not a JPEG...) drop out.
  2. Each score is turned into log-odds  z = ln(s / (100 - s))  so a confident 95 counts more than a lukewarm 60.
  3. Votes are weighted. AI-model tests carry the biggest weights because they were most accurate in our
     experiment; classic forensic tests have small weights, but a test that finds STRONG, SPECIFIC evidence
     (a localised splice, a periodic up-sampling grid, an AI tag, a frozen face, ...) gets its weight amplified -
     up to 3x - so it can still move the result. Vague "too smooth / too little grain" evidence is never amplified,
     because ordinary phone denoising, webcams and video compression produce it too.
  4. Weighted mean log-odds -> back to 0-100 with a gain/bias learnt on the calibration split.
  5. Hard evidence overrides: an AI-tool tag in the metadata guarantees at least 88.
Confidence = how much the tests agree with the final call, blended with how far the score is from 50.
"""
from __future__ import annotations

import math

import numpy as np

from . import config

NAMES_SHORT = {  # kept for other modules that import it
    "ai_generated": "AI-image detector", "ai_face": "face analysis", "ela": "error-level analysis",
    "noise": "noise analysis", "fft": "frequency spectrum", "jpeg_quant": "JPEG table check",
    "metadata": "metadata check", "blink": "blink-rate test", "landmark_jitter": "landmark-jitter test",
    "temporal_flicker": "flicker test", "ai_voice": "AI-voice detector", "spectral_cutoff": "spectral cut-off test",
    "prosody": "pitch analysis", "breath_silence": "breath and silence analysis",
}
AMPLIFY = 2.0   # extra weight multiplier (x(1+AMPLIFY)) for a classic test at score 100
# categories whose high scores are specific evidence by default; compression / noise / frequency tests opt in per
# finding by setting t["_amplify"] = True (only for a localised splice or a periodic generator grid)
AMPLIFY_DEFAULT = {"metadata", "biometric", "temporal", "acoustic"}


def _logit(s: float) -> float:
    p = min(0.985, max(0.015, s / 100.0))
    return math.log(p / (1 - p))


def verdict_for(score: float) -> str:
    if score < config.THRESH_SUSPICIOUS:
        return "authentic"
    if score > config.THRESH_SYNTHETIC:
        return "synthetic"
    return "suspicious"


def fuse(kind: str, tests: list[dict], hard_ai_marker: bool = False) -> dict:
    base_w = config.weights_for(kind)
    cal = config.CALIBRATION.get("fusion", {}).get(kind, {})
    gain, bias = float(cal.get("gain", 1.0)), float(cal.get("bias", 0.0))
    active = []
    for t in tests:
        w = float(base_w.get(t["id"], 0.0))
        if t["status"] != "ok" or t["score"] is None or w <= 0:
            t["weight"] = 0.0
            continue
        eff = w
        amplify = t.get("_amplify", t["category"] in AMPLIFY_DEFAULT)
        if t["category"] != "ai_model" and amplify and t["score"] > config.THRESH_SYNTHETIC:
            eff = w * (1 + AMPLIFY * (t["score"] - config.THRESH_SYNTHETIC) / (100 - config.THRESH_SYNTHETIC))
        active.append((t, eff))
    if not active:
        for t in tests:
            t["weight"] = 0.0
        return {"score": 50, "verdict": "suspicious", "confidence": 0.0,
                "summary": "No test could analyse this file, so no verdict is possible."}
    tot = sum(e for _, e in active)
    Z = 0.0
    for t, e in active:
        t["weight"] = round(e / tot, 3)
        Z += (e / tot) * _logit(t["score"])
    score = 100.0 / (1.0 + math.exp(-(gain * Z + bias)))
    if hard_ai_marker:
        score = max(score, 88.0)
    score = float(np.clip(score, 0, 100))
    verdict = verdict_for(score)
    # confidence
    agree = 1.0 - sum(t["weight"] * abs(t["score"] - score) / 100.0 for t, _ in active)
    decis = abs(score - 50) / 50.0
    n_ok = len(active)
    conf = (0.45 * agree + 0.55 * decis) * (0.75 if n_ok < 3 else 1.0)
    conf = float(np.clip(conf, 0.05, 0.99))
    return {"score": int(round(score)), "verdict": verdict, "confidence": round(conf, 2),
            "summary": summarise(kind, verdict, active, hard_ai_marker)}


# what each test found, phrased as evidence (never an accusation the test cannot back up)
FAKE_PHRASE = {
    "ai_generated": "the AI-image detector found generator fingerprints",
    "ai_face": "the face looks machine-made",
    "ela": "error levels are uneven",
    "noise": "the camera grain is weak or uneven",
    "fft": "the frequency spectrum looks unusual",
    "jpeg_quant": "the JPEG history looks re-saved",
    "metadata": "the metadata shows editing software",
    "blink": "the face hardly blinks",
    "landmark_jitter": "the face geometry moves unnaturally",
    "temporal_flicker": "the face flickers on its own",
    "ai_voice": "the AI-voice detector found synthetic-voice traces",
    "breath_silence": "the pauses are unnaturally silent",
}
REAL_PHRASE = {
    "ai_generated": "the AI-image detector", "ai_face": "the face analysis", "ela": "error-level analysis",
    "noise": "the noise analysis", "fft": "the frequency spectrum", "jpeg_quant": "the JPEG tables",
    "metadata": "the metadata", "blink": "the blink rate", "landmark_jitter": "the landmark motion",
    "temporal_flicker": "the lighting", "ai_voice": "the AI-voice detector", "breath_silence": "the pause analysis",
}


def summarise(kind: str, verdict: str, active: list, hard_ai_marker: bool) -> str:
    noun = {"image": "image", "video": "video", "audio": "recording"}[kind]

    def contrib(item):
        t, _ = item
        return t["weight"] * _logit(t["score"])

    if hard_ai_marker:
        return f"The file's own metadata names an AI tool, and the {noun} is treated as AI-generated."
    # tests leaning each way, strongest contribution first (weight x log-odds), so a heavily weighted AI detector at
    # 63 outranks a lightly weighted classic test at 72
    pro_fake = sorted([a for a in active if a[0]["score"] > 50], key=contrib, reverse=True)
    pro_real = sorted([a for a in active if a[0]["score"] < 50], key=contrib)
    rp = lambda a: REAL_PHRASE.get(a[0]["id"], f"the {a[0]['name'].lower()}")  # noqa: E731

    def fp(a):  # strong evidence (> 65) gets the full phrase; 51-65 only "leans synthetic", matching the test card
        if a[0]["score"] > config.THRESH_SYNTHETIC:
            return FAKE_PHRASE.get(a[0]["id"], f"the {a[0]['name'].lower()} raised concerns")
        return f"{rp(a)} leans synthetic"
    if verdict == "synthetic":
        if len(pro_fake) >= 2:
            return f"Likely synthetic: {fp(pro_fake[0])}, and {fp(pro_fake[1])}."
        if pro_fake:
            return f"Likely synthetic: {fp(pro_fake[0])}."
        return f"Several weak signals add up to a likely synthetic {noun}."
    if verdict == "authentic":
        if len(pro_real) >= 2:
            return f"No sign of manipulation: {rp(pro_real[0])} and {rp(pro_real[1])} both look genuine."
        if pro_real:
            return f"No sign of manipulation: {rp(pro_real[0])} looks like a genuine capture."
        return f"No test found meaningful signs that this {noun} was manipulated."
    if pro_fake and pro_real:
        return f"Inconclusive: {fp(pro_fake[0])}, but {rp(pro_real[0])} disagrees."
    if pro_fake:
        return f"Inconclusive: {fp(pro_fake[0])}; treat this {noun} with caution."
    return f"Inconclusive: the tests are on the fence about this {noun}; check the source."


def strip_private(rep: dict) -> dict:
    """Remove the private '_hint' keys tests leave for the fusion (they never reach the JSON report)."""
    for t in rep.get("tests", []):
        for k in [k for k in t if k.startswith("_")]:
            t.pop(k)
    return rep
