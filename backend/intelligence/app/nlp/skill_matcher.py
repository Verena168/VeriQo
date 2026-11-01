"""Embedding + cosine-similarity matching of a profile against hackathon requirements (Module A).

Implements whitebook Algorithm 1, extended with requirement weights and a category fallback:
  exact match           -> 1.0
  semantic match        -> cosine similarity, if above the threshold (default 0.65, see config)
  same-category skill   -> 0.5 (e.g. requirement "Machine Learning", candidate knows "PyTorch")
  otherwise             -> 0
Score = weighted mean over requirements, as a percentage.
"""

import logging
import threading
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.nlp.taxonomy import canonicalize, category_of

log = logging.getLogger(__name__)
CATEGORY_CREDIT = 0.5


_model_lock = threading.Lock()
_model_state: dict = {}


def _model():
    """Load the sentence-transformer once (thread-safe). Returns None if it can't be loaded.

    The local cache is tried first: the default online load asks the Hugging Face Hub for
    updates, which together with the PyTorch import made the first match after a restart
    take over 2 minutes and time out the API call.
    """
    with _model_lock:
        if "model" not in _model_state:
            _model_state["model"] = _load_model()
        return _model_state["model"]


def _load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        log.warning("sentence-transformers unavailable, semantic matching disabled: %s", exc)
        return None
    name = get_settings().embedding_model
    try:
        return SentenceTransformer(name, device="cpu", local_files_only=True)
    except Exception:
        log.info("Embedding model not cached locally; downloading %s", name)
    try:
        return SentenceTransformer(name, device="cpu")
    except Exception as exc:
        log.warning("Embedding model unavailable, semantic matching disabled: %s", exc)
        return None


def model_ready() -> bool:
    return _model_state.get("model") is not None


@lru_cache(maxsize=4096)
def _embed_one(text: str) -> np.ndarray | None:
    model = _model()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True)


def _cosine_matrix(reqs: list[str], cands: list[str]) -> np.ndarray | None:
    vecs_r = [_embed_one(r) for r in reqs]
    vecs_c = [_embed_one(c) for c in cands]
    if any(v is None for v in vecs_r + vecs_c):
        return None
    return np.stack(vecs_r) @ np.stack(vecs_c).T  # vectors are normalised -> cosine


def match(candidate_skills: list[str], requirements: list[dict], threshold: float | None = None) -> dict:
    """requirements: [{"skill": str, "weight": int}] ; returns score 0-100 plus per-requirement breakdown."""
    threshold = get_settings().semantic_threshold if threshold is None else threshold
    cands = sorted({canonicalize(s) or s for s in candidate_skills})
    cand_set = {c.lower() for c in cands}
    cand_categories = {category_of(c): c for c in cands if category_of(c)}

    reqs = [(canonicalize(r["skill"]) or r["skill"], max(int(r.get("weight", 1)), 1)) for r in requirements]
    sims = _cosine_matrix([r for r, _ in reqs], cands) if reqs and cands else None

    breakdown, total, weight_sum = [], 0.0, 0
    for i, (req, weight) in enumerate(reqs):
        item = {"skill": req, "weight": weight, "matched_by": "none", "evidence": None, "score": 0.0}
        if req.lower() in cand_set:
            item.update(matched_by="exact", evidence=req, score=1.0)
        else:
            if sims is not None:
                j = int(np.argmax(sims[i]))
                if sims[i, j] > threshold:
                    item.update(matched_by="semantic", evidence=cands[j], score=round(float(sims[i, j]), 3))
            cat = category_of(req)
            if item["matched_by"] == "none" and cat in cand_categories:
                item.update(matched_by="category", evidence=cand_categories[cat], score=CATEGORY_CREDIT)
        total += item["score"] * weight
        weight_sum += weight
        breakdown.append(item)

    return {
        "score": round(100 * total / weight_sum, 1) if weight_sum else 0.0,
        "breakdown": breakdown,
        "semantic_enabled": sims is not None or not (reqs and cands),
    }
