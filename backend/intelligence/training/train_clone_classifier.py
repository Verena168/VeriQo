"""Train the clone classifier on training/data/clone_pairs.csv.

* Candidates: logistic regression and histogram gradient boosting.
* Model selection on the validation split (average precision).
* Decision threshold chosen on validation: the lowest threshold whose false-positive rate is <= 2%,
  because a false plagiarism accusation costs more than a missed copy. FPR is used rather than
  precision because precision depends on the share of clones, which is ~60% in this dataset but
  far lower in a real hackathon.
* Final numbers are reported once, on the untouched test split, next to a plain-rule baseline
  (containment >= 0.5) so the value the model adds is visible.

Usage:  python -m training.train_clone_classifier
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ast_engine.classifier import METRICS_FILE, MODEL_FILE
from app.ast_engine.features import FEATURE_NAMES, comparable
from app.core.config import get_settings

DATA = Path(__file__).parent / "data" / "clone_pairs.csv"
MAX_FPR = 0.02
GATED_OUT: dict = {}
MONOTONIC = {"containment_a": 1, "containment_b": 1, "jaccard": 1, "ast_jaccard": 1, "size_ratio": 0, "log_shared": 1}


def load():
    with DATA.open() as fh:
        rows = list(csv.DictReader(fh))
    # Pairs the runtime would never score (too little shared code, tiny files) are excluded,
    # so training and the reported metrics reflect what the live engine actually decides.
    gated = [r for r in rows if comparable(int(r["n_shared"]), int(r["tokens_a"]), int(r["tokens_b"]))]
    print(f"{len(rows) - len(gated)} of {len(rows)} pairs fall below the comparison gate (never flagged at runtime)")
    GATED_OUT.update({"pairs": len(rows) - len(gated), "positives": sum(int(r["label"]) for r in rows) - sum(int(r["label"]) for r in gated)})
    rows = gated
    out = {}
    for split in ("train", "val", "test"):
        part = [r for r in rows if r["split"] == split]
        X = np.array([[float(r[f]) for f in FEATURE_NAMES] for r in part])
        y = np.array([int(r["label"]) for r in part])
        out[split] = (X, y, [r["kind"] for r in part], [r["lang"] for r in part])
    return out


def pick_threshold(y, p) -> float:
    fpr, tpr, thr = roc_curve(y, p)
    ok = [t for f, t in zip(fpr, thr) if f <= MAX_FPR and np.isfinite(t)]
    return float(min(ok)) if ok else 0.5


def scores(y, pred, prob=None) -> dict:
    d = {
        "precision": round(precision_score(y, pred, zero_division=0), 4),
        "recall": round(recall_score(y, pred, zero_division=0), 4),
        "f1": round(f1_score(y, pred, zero_division=0), 4),
        "false_positive_rate": round(float(((pred == 1) & (y == 0)).sum() / max((y == 0).sum(), 1)), 4),
    }
    if prob is not None:
        d["roc_auc"] = round(roc_auc_score(y, prob), 4)
        d["average_precision"] = round(average_precision_score(y, prob), 4)
    return d


def per_kind(y, pred, kinds) -> dict:
    out = {}
    for k in sorted(set(kinds)):
        m = np.array([x == k for x in kinds])
        label = int(y[m][0])
        rate = float((pred[m] == label).mean())
        out[k] = {"label": "clone" if label else "not_clone", "n": int(m.sum()),
                  ("recall" if label else "true_negative_rate"): round(rate, 4)}
    return out


def main() -> None:
    data = load()
    Xtr, ytr, _, _ = data["train"]
    Xva, yva, _, _ = data["val"]
    Xte, yte, kte, lte = data["test"]

    candidates = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        # Monotonic constraints: more shared code can never make a pair *less* likely to be a clone.
        # Without them the model flagged some pairs with ~0% overlap in sparse regions of feature space.
        "gradient_boosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, random_state=0,
            monotonic_cst=[MONOTONIC[f] for f in FEATURE_NAMES],
        ),
    }
    val_ap = {}
    for name, model in candidates.items():
        model.fit(Xtr, ytr)
        val_ap[name] = average_precision_score(yva, model.predict_proba(Xva)[:, 1])
        print(f"{name:20s} val AP={val_ap[name]:.4f}")
    best_name = max(val_ap, key=val_ap.get)
    model = candidates[best_name]
    thr = pick_threshold(yva, model.predict_proba(Xva)[:, 1])

    p_te = model.predict_proba(Xte)[:, 1]
    pred = (p_te >= thr).astype(int)
    base_pred = (Xte[:, 0] >= 0.5).astype(int)

    metrics = {
        "model": best_name,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": FEATURE_NAMES,
        "decision_threshold": round(thr, 4),
        "threshold_rule": f"lowest threshold with validation false-positive rate <= {MAX_FPR}",
        "pairs": {s: {"n": int(len(data[s][1])), "positives": int(data[s][1].sum())} for s in data},
        "excluded_by_gate": GATED_OUT | {"rule": "pairs need >= 2 shared fingerprints and >= 50 tokens per file"},
        "validation_average_precision": {k: round(v, 4) for k, v in val_ap.items()},
        "test": scores(yte, pred, p_te),
        "test_baseline_containment_0_5": scores(yte, base_pred),
        "test_by_case": per_kind(yte, pred, kte),
        "test_by_language": {
            lang: scores(yte[np.array(lte) == lang], pred[np.array(lte) == lang]) for lang in sorted(set(lte))
        },
        "caveat": "Positives are synthetic transformations of real code; real-world plagiarism is more varied, "
                  "so these figures are an upper bound until validated on the dry-run hackathon data. Negatives "
                  "from the same package can genuinely share copied code (CPython reuses code between modules), "
                  "so part of the measured false-positive rate is label noise rather than model error.",
    }
    out_dir = get_settings().models_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "threshold": thr, "features": FEATURE_NAMES}, out_dir / MODEL_FILE)
    (out_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: metrics[k] for k in ("model", "decision_threshold", "test", "test_baseline_containment_0_5")}, indent=2))
    print(json.dumps(metrics["test_by_case"], indent=2))


if __name__ == "__main__":
    main()
