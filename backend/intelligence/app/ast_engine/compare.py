"""Compare one submission against a corpus of other submissions and reference repos (Module C)."""

from collections import Counter, defaultdict

import numpy as np

from app.ast_engine.classifier import clone_probability, threshold
from app.ast_engine.features import comparable, pair_features
from app.ast_engine.fingerprint import FileFingerprint

TOP_CANDIDATES = 5


def _ranges(lines: list[int], gap: int = 3) -> list[list[int]]:
    out: list[list[int]] = []
    for ln in sorted(set(lines)):
        if out and ln - out[-1][1] <= gap:
            out[-1][1] = ln
        else:
            out.append([ln, ln])
    return out


def compare(submission: list[FileFingerprint], corpus: list[dict]) -> dict:
    """corpus: [{"source_id", "label", "kind": "submission"|"reference"|"template", "files": [FileFingerprint]}]

    "template" sources are starter code the organizer allows: their fingerprints are removed from
    the submission before matching, so using the official boilerplate is never flagged.
    """
    allowed = {h for src in corpus if src["kind"] == "template" for f in src["files"] for h, _ in f.fps}
    sources = [s for s in corpus if s["kind"] != "template"]

    # Fingerprints present in many independent sources are generic boilerplate, not evidence.
    spread = Counter(h for s in sources for h in {h for f in s["files"] for h, _ in f.fps})
    common = {h for h, n in spread.items() if n > max(4, len(sources) // 2)}
    ignore = allowed | common

    index: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for si, src in enumerate(sources):
        for fi, f in enumerate(src["files"]):
            for h in {h for h, _ in f.fps} - ignore:
                index[h].append((si, fi))

    thr = threshold()
    total_tokens = sum(f.n_tokens for f in submission) or 1
    template_tokens = 0.0
    matched_tokens = 0.0
    per_source: Counter = Counter()
    files_out = []

    for f in submission:
        own = {h for h, _ in f.fps}
        if own:
            template_tokens += f.n_tokens * len(own & allowed) / len(own)
        probe = FileFingerprint(f.path, f.family, f.n_tokens, f.n_lines, [(h, ln) for h, ln in f.fps if h not in ignore], f.ast)
        counts = Counter(c for h in {h for h, _ in probe.fps} for c in index.get(h, ()))
        cands = [
            (si, fi) for (si, fi), n in counts.most_common()
            if sources[si]["files"][fi].family == f.family and comparable(n, f.n_tokens, sources[si]["files"][fi].n_tokens)
        ][:TOP_CANDIDATES]

        best = None
        if cands:
            feats, shared_sets = [], []
            for si, fi in cands:
                other = sources[si]["files"][fi]
                shared = {h for h, _ in probe.fps} & {h for h, _ in other.fps}
                shared_sets.append(shared)
                feats.append(pair_features(f, other, shared))
            probs = clone_probability(np.vstack(feats))
            k = max(range(len(cands)), key=lambda i: (probs[i] >= thr, feats[i][0], probs[i]))
            si, fi = cands[k]
            src, other, shared = sources[si], sources[si]["files"][fi], shared_sets[k]
            best = {
                "source_id": src["source_id"],
                "source_label": src["label"],
                "source_kind": src["kind"],
                "source_path": other.path,
                "probability": round(float(probs[k]), 3),
                "containment": round(float(feats[k][0]), 3),
                "jaccard": round(float(feats[k][2]), 3),
                "ast_similarity": round(float(feats[k][3]), 3),
                "sub_lines": _ranges([ln for h, ln in f.fps if h in shared]),
                "src_lines": _ranges([ln for h, ln in other.fps if h in shared]),
            }
        flagged = bool(best and best["probability"] >= thr)
        if flagged:
            share = f.n_tokens * best["containment"]
            matched_tokens += share
            per_source[(best["source_id"], best["source_label"], best["source_kind"])] += share
        files_out.append({"path": f.path, "family": f.family, "n_tokens": f.n_tokens, "flagged": flagged, "best_match": best})

    files_out.sort(key=lambda x: (not x["flagged"], -(x["best_match"] or {}).get("containment", 0)))
    return {
        "plagiarism_score": round(100 * matched_tokens / total_tokens, 1),
        "template_share": round(100 * template_tokens / total_tokens, 1),
        "files_compared": len(submission),
        "files_flagged": sum(x["flagged"] for x in files_out),
        "top_sources": [
            {"source_id": sid, "label": label, "kind": kind, "share": round(100 * tok / total_tokens, 1)}
            for (sid, label, kind), tok in per_source.most_common(5)
        ],
        "files": files_out,
        "decision_threshold": round(float(thr), 3),
    }
