"""Pair features shared by training and runtime, so the model sees identical inputs in both."""

import numpy as np

from app.ast_engine.fingerprint import FileFingerprint

FEATURE_NAMES = ["containment_a", "containment_b", "jaccard", "ast_jaccard", "size_ratio", "log_shared"]

# A pair is only scored when there is enough material to be evidence at all. Used identically by
# the runtime comparison and by training/evaluation, so reported metrics match real behaviour.
MIN_SHARED = 2  # shared fingerprints
MIN_TOKENS = 50  # tokens in each file; tiny files (e.g. empty __init__.py) are never flagged


def comparable(n_shared: int, tokens_a: int, tokens_b: int) -> bool:
    return n_shared >= MIN_SHARED and min(tokens_a, tokens_b) >= MIN_TOKENS


def pair_features(a: FileFingerprint, b: FileFingerprint, shared: set[int] | None = None) -> np.ndarray:
    """a is the file under suspicion, b the candidate source."""
    ha, hb = {h for h, _ in a.fps}, {h for h, _ in b.fps}
    shared = ha & hb if shared is None else shared
    n = len(shared)
    union = len(ha | hb) or 1
    ast_union = len(a.ast | b.ast)
    return np.array([
        n / (len(ha) or 1),
        n / (len(hb) or 1),
        n / union,
        len(a.ast & b.ast) / ast_union if ast_union else 0.0,
        min(a.n_tokens, b.n_tokens) / (max(a.n_tokens, b.n_tokens) or 1),
        np.log1p(n),
    ], dtype=float)
