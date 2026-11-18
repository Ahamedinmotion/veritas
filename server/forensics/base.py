"""Common shape of a forensic test result (see docs/ARCHITECTURE.md, "tests")."""
from __future__ import annotations

import logging
import time
import traceback

from .. import config
from ..util import r

log = logging.getLogger("veritas.forensics")

CATEGORIES = {"compression", "noise", "frequency", "metadata", "ai_model", "biometric", "temporal", "acoustic"}


def make_test(id: str, name: str, category: str, *, score=None, status="ok", finding="", explain="",
              visual=None, metrics=None, weight=None) -> dict:
    assert category in CATEGORIES, category
    words = finding.split()
    if len(words) > 14:
        finding = " ".join(words[:14]).rstrip(",;:") + "."
    return {
        "id": id, "name": name, "category": category,
        "score": None if score is None else int(round(max(0.0, min(100.0, float(score))))),
        "weight": weight if weight is not None else 0.0,
        "status": status, "finding": finding, "explain": explain,
        "visual": visual,
        "metrics": {k: r(v) if isinstance(v, (int, float)) or v is None else v for k, v in (metrics or {}).items()},
    }


def safe_run(fn, test_id: str, name: str, category: str, explain: str, *args, **kw) -> dict:
    """Run one test; any exception becomes status=error instead of crashing the whole report."""
    t0 = time.perf_counter()
    try:
        out = fn(*args, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("test %s failed: %s\n%s", test_id, e, traceback.format_exc(limit=3))
        out = make_test(test_id, name, category, status="error", finding="This test could not run on this file.",
                        explain=explain, metrics={"error": str(e)[:160]})
    out.setdefault("metrics", {})
    out["metrics"]["ms"] = int((time.perf_counter() - t0) * 1000)
    return out


def calibrated(test_id: str, raw_score: float | None) -> float | None:
    """Optional monotone re-mapping of a raw test score learnt on the calibration split (scripts/evaluate.py).
    Stored as piecewise-linear knots {"x": [...], "y": [...]} in server/calibration.json."""
    if raw_score is None:
        return None
    knots = config.CALIBRATION.get("curves", {}).get(test_id)
    if not knots:
        return raw_score
    import numpy as np

    return float(np.interp(raw_score, knots["x"], knots["y"]))


def feature_score(test_id: str, feats: dict) -> float | None:
    """Score from a small logistic model fitted on the calibration split: 100 * sigmoid(w . x + b).
    Stored in server/calibration.json under feature_models[test_id] = {features, coef, intercept, mean, std}."""
    fm = config.CALIBRATION.get("feature_models", {}).get(test_id)
    if not fm:
        return None
    import math

    z = fm["intercept"]
    for name, c, mu, sd in zip(fm["features"], fm["coef"], fm["mean"], fm["std"]):
        z += c * (feats[name] - mu) / (sd or 1.0)
    z = max(-30.0, min(30.0, z))
    return 100.0 / (1.0 + math.exp(-z))
