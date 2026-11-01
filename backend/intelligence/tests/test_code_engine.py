from app.ast_engine.compare import compare
from app.ast_engine.fingerprint import K, W, fingerprint_source, winnow
from app.ast_engine.tokenizer import normalize

ORIGINAL = '''
def binary_search(items, target):
    """Return index of target or -1."""
    lo, hi = 0, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2  # middle
        if items[mid] == target:
            return mid
        if items[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def bubble_sort(values):
    n = len(values)
    for i in range(n):
        for j in range(0, n - i - 1):
            if values[j] > values[j + 1]:
                values[j], values[j + 1] = values[j + 1], values[j]
    return values
'''

RENAMED = '''
def find(arr, x):
    # totally my own code
    a, b = 0, len(arr) - 1
    while a <= b:
        m = (a + b) // 2
        if arr[m] == x:
            return m
        if arr[m] < x:
            a = m + 1
        else:
            b = m - 1
    return -1


def sort_it(v):
    size = len(v)
    for p in range(size):
        for q in range(0, size - p - 1):
            if v[q] > v[q + 1]:
                v[q], v[q + 1] = v[q + 1], v[q]
    return v
'''

UNRELATED = '''
import json

class Config:
    def __init__(self, path):
        self.path = path
        self.data = {}

    def load(self):
        with open(self.path) as fh:
            self.data = json.load(fh)
        return self.data

    def get(self, key, default=None):
        return self.data.get(key, default)
'''


def test_normalisation_ignores_names_comments_and_docstrings():
    a = [t.kind for t in normalize(ORIGINAL, "python")]
    b = [t.kind for t in normalize(RENAMED, "python")]
    assert a == b
    assert "ID" in a and "NUM" in a


def test_winnowing_guarantee():
    kinds = [f"t{i % 37}" for i in range(400)]
    lines = list(range(400))
    fps = winnow(kinds, lines)
    # density roughly 2 / (W + 1)
    assert 0 < len(fps) < len(kinds)
    # every window of W consecutive k-grams contributes at least one selected position
    positions = sorted(ln for _, ln in fps)
    assert max(b - a for a, b in zip(positions, positions[1:])) <= W


def _src(sid, kind, files):
    return {"source_id": sid, "label": sid, "kind": kind, "files": files}


def test_compare_flags_renamed_copy_not_unrelated():
    sub = [fingerprint_source("a.py", RENAMED)]
    corpus = [_src("orig", "reference", [fingerprint_source("orig.py", ORIGINAL)]),
              _src("other", "submission", [fingerprint_source("cfg.py", UNRELATED)])]
    out = compare(sub, corpus)
    f = out["files"][0]
    assert f["flagged"] and f["best_match"]["source_id"] == "orig"
    assert f["best_match"]["containment"] > 0.9
    assert out["plagiarism_score"] > 90

    clean = compare([fingerprint_source("cfg.py", UNRELATED)], [_src("orig", "reference", [fingerprint_source("o.py", ORIGINAL)])])
    assert clean["plagiarism_score"] == 0 and not clean["files"][0]["flagged"]


def test_template_code_is_not_flagged():
    sub = [fingerprint_source("a.py", RENAMED)]
    corpus = [_src("starter", "template", [fingerprint_source("t.py", ORIGINAL)])]
    out = compare(sub, corpus)
    assert out["plagiarism_score"] == 0
    assert out["template_share"] > 90


def test_cross_language_never_matches():
    sub = [fingerprint_source("a.py", ORIGINAL)]
    js = fingerprint_source("a.js", "function f(a,b){ while (a <= b) { let m = (a + b) / 2; if (a[m] == b) return m; } return -1; }")
    out = compare(sub, [_src("js", "submission", [js])])
    assert out["files"][0]["best_match"] is None


def test_ast_features_present():
    fp = fingerprint_source("a.py", ORIGINAL)
    assert len(fp.ast) > 10 and fp.n_tokens > 50 and K > 0
