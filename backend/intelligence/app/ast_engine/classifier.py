"""Trained clone classifier (see training/train_clone_classifier.py). Falls back to a rule if absent."""

import json
import logging
from functools import lru_cache

import numpy as np

from app.core.config import get_settings

log = logging.getLogger(__name__)
MODEL_FILE = "clone_classifier.joblib"
METRICS_FILE = "clone_classifier_metrics.json"
FALLBACK_THRESHOLD = 0.5


@lru_cache
def _load():
    path = get_settings().models_dir / MODEL_FILE
    if not path.exists():
        log.warning("No trained clone classifier at %s; using containment >= %.1f rule", path, FALLBACK_THRESHOLD)
        return None
    import joblib

    return joblib.load(path)


def clone_probability(features: np.ndarray) -> np.ndarray:
    """features: (n, len(FEATURE_NAMES)) -> P(clone) per row."""
    features = np.atleast_2d(features)
    bundle = _load()
    if bundle is None:
        return (features[:, 0] >= FALLBACK_THRESHOLD).astype(float)
    return bundle["model"].predict_proba(features)[:, 1]


def threshold() -> float:
    bundle = _load()
    return bundle["threshold"] if bundle else 0.5


def model_info() -> dict:
    path = get_settings().models_dir / METRICS_FILE
    if _load() is None or not path.exists():
        return {"trained": False, "method": f"rule: containment >= {FALLBACK_THRESHOLD}"}
    return {"trained": True, **json.loads(path.read_text())}
