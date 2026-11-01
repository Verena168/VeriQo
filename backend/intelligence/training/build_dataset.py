"""Build a labelled clone / non-clone pair dataset for the clone classifier.

Source code comes from real, human-written corpora available offline:
  * the CPython standard library (Python)
  * JavaScript files from an npm node_modules tree (optional, --js-root)

Files are split into train / val / test BEFORE pairs are generated, so no file (or variant of it)
appears in more than one split. Positives are plagiarism-style transformations of a file;
negatives are pairs of different files, including hard negatives from the same package.

Usage:  python -m training.build_dataset [--js-root ../../frontend/node_modules] [--per-lang 450]
"""

import argparse
import ast
import csv
import random
import sys
from pathlib import Path

from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Name

from app.ast_engine.features import FEATURE_NAMES, pair_features
from app.ast_engine.fingerprint import fingerprint_source

SEED = 7
OUT = Path(__file__).parent / "data" / "clone_pairs.csv"


def collect_python(limit: int, rng: random.Random) -> list[Path]:
    lib = Path(sys.base_prefix) / "Lib"
    files = [
        p for p in lib.rglob("*.py")
        if "site-packages" not in p.parts and "__pycache__" not in p.parts and 60 <= _line_count(p) <= 2500
    ]
    rng.shuffle(files)
    return files[:limit]


def collect_js(root: Path | None, limit: int, rng: random.Random) -> list[Path]:
    if not root or not root.exists():
        return []
    files = []
    for p in root.rglob("*.js"):
        name = p.name
        if ".min." in name or "dist" in p.parts or "umd" in p.parts or "cjs" in p.parts:
            continue
        n = _line_count(p)
        if 60 <= n <= 2500 and p.stat().st_size / n < 120:  # skip bundled/minified code
            files.append(p)
    rng.shuffle(files)
    # at most 3 files per package so one big package doesn't dominate
    per_pkg: dict[str, int] = {}
    out = []
    for p in files:
        pkg = p.relative_to(root).parts[0]
        if per_pkg.get(pkg, 0) < 3:
            per_pkg[pkg] = per_pkg.get(pkg, 0) + 1
            out.append(p)
        if len(out) >= limit:
            break
    return out


def _line_count(p: Path) -> int:
    try:
        return p.read_text(encoding="utf-8").count("\n")
    except (UnicodeDecodeError, OSError):
        return 0


# ---------------------------------------------------------------- transformations

def rename_and_recomment(code: str, lexer: str, rng: random.Random) -> str:
    """Consistently rename identifiers and rewrite every comment."""
    mapping: dict[str, str] = {}
    out = []
    for ttype, value in get_lexer_by_name(lexer, stripnl=False, ensurenl=False).get_tokens(code):
        if ttype in Name and ttype not in Name.Builtin and value.isidentifier():
            if value not in mapping:
                mapping[value] = f"{rng.choice(['tmp', 'val', 'obj', 'item', 'data', 'res'])}_{len(mapping)}"
            out.append(mapping[value])
        elif ttype in Comment.Single:
            out.append(("# " if lexer == "python" else "// ") + rng.choice(["updated", "helper", "handle case", "main logic"]))
        else:
            out.append(value)
    return "".join(out)


def reorder_python(code: str, rng: random.Random) -> str | None:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    defs = [i for i, n in enumerate(tree.body) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    if len(defs) < 3:
        return None
    nodes = [tree.body[i] for i in defs]
    rng.shuffle(nodes)
    for i, n in zip(defs, nodes):
        tree.body[i] = n
    return ast.unparse(tree)


def heavy_edit(code: str, donor: str, rng: random.Random) -> str:
    """Delete ~10% of lines and splice in ~12% foreign lines."""
    donor_lines = donor.splitlines() or [""]
    out = []
    for line in code.splitlines():
        if rng.random() < 0.10:
            continue
        out.append(line)
        if rng.random() < 0.12:
            out.append(rng.choice(donor_lines))
    return "\n".join(out)


MIN_COPIED_TOKENS = 30


def partial_copy(source: str, host: str, frac: tuple[float, float], rng: random.Random, ext: str) -> str | None:
    """Insert a contiguous chunk of `source` into an unrelated `host` file.

    Returns None when the chunk holds too little real code (e.g. only comments or blank lines),
    which would otherwise be a mislabelled "clone" that shares nothing with its source.
    """
    s, h = source.splitlines(), host.splitlines()
    n = max(int(len(s) * rng.uniform(*frac)), 5)
    start = rng.randrange(0, max(len(s) - n, 1))
    chunk = s[start:start + n]
    fp = fingerprint_source(f"chunk{ext}", "\n".join(chunk))
    if fp is None or fp.n_tokens < MIN_COPIED_TOKENS:
        return None
    pos = rng.randrange(0, len(h) + 1)
    return "\n".join(h[:pos] + chunk + h[pos:])


# ---------------------------------------------------------------- pair generation

def build_split(files: list[Path], lang: str, split: str, rng: random.Random) -> list[dict]:
    ext, lexer = (".py", "python") if lang == "python" else (".js", "javascript")
    codes = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    fps = {p: fingerprint_source(f"x{ext}", c) for p, c in codes.items()}
    files = [p for p in files if fps[p] is not None]
    by_dir: dict[Path, list[Path]] = {}
    for p in files:
        by_dir.setdefault(p.parent, []).append(p)

    rows = []

    def add(suspect_code: str | None, source: Path, label: int, kind: str):
        if suspect_code is None:
            return
        a = fingerprint_source(f"s{ext}", suspect_code)
        if a is None:
            return
        b = fps[source]
        f = pair_features(a, b)
        n_shared = len({h for h, _ in a.fps} & {h for h, _ in b.fps})
        rows.append({
            "split": split, "lang": lang, "kind": kind, "label": label, **dict(zip(FEATURE_NAMES, f.round(6))),
            "n_shared": n_shared, "tokens_a": a.n_tokens, "tokens_b": b.n_tokens, "source": str(source.relative_to(source.anchor)),
        })

    for p in files:
        others = [q for q in files if q != p]
        if not others:
            continue
        code = codes[p]
        # positives
        add(rename_and_recomment(code, lexer, rng), p, 1, "rename_recomment")
        if lang == "python":
            add(reorder_python(code, rng), p, 1, "reorder")
        add(heavy_edit(code, codes[rng.choice(others)], rng), p, 1, "heavy_edit")
        add(partial_copy(code, codes[rng.choice(others)], (0.25, 0.5), rng, ext), p, 1, "partial_25_50")
        add(partial_copy(code, codes[rng.choice(others)], (0.15, 0.25), rng, ext), p, 1, "partial_15_25")
        # negatives: suspect is an unrelated file, "source" is p
        for q in rng.sample(others, min(2, len(others))):
            add(codes[q], p, 0, "random_pair")
        siblings = [q for q in by_dir.get(p.parent, []) if q != p]
        for q in rng.sample(siblings, min(2, len(siblings))):
            add(codes[q], p, 0, "same_package")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--js-root", type=Path, default=None)
    ap.add_argument("--per-lang", type=int, default=450)
    args = ap.parse_args()
    rng = random.Random(SEED)

    rows = []
    for lang, files in (("python", collect_python(args.per_lang, rng)), ("js", collect_js(args.js_root, args.per_lang, rng))):
        if not files:
            print(f"{lang}: no files, skipped")
            continue
        n = len(files)
        splits = {"train": files[: int(0.7 * n)], "val": files[int(0.7 * n): int(0.85 * n)], "test": files[int(0.85 * n):]}
        for split, part in splits.items():
            r = build_split(part, lang, split, rng)
            rows += r
            print(f"{lang:6s} {split:5s} files={len(part):4d} pairs={len(r):5d} positives={sum(x['label'] for x in r)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} pairs -> {OUT}")


if __name__ == "__main__":
    main()
