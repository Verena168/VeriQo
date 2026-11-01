# VERIQO — ML models: method and measured results

All numbers below were produced by the scripts in `backend/intelligence/training/` on 12 Oct 2026 and are
reproducible (`random.Random(7)` seed). They are measurements on a **synthetic benchmark**, not on real hackathon data;
see *Limitations*.

## 1. Clone classifier (Module C)

### What it decides
For a submitted file and its closest candidate source file (another submission or a reference repo), is the
submitted file a copy (fully or partly) of the source?

### Pipeline
1. **Parse** with tree-sitter (14 grammars). One pass yields
   - normalised leaf tokens: identifiers → `ID`, strings → `STR`, numbers → `NUM`, comments dropped, keywords/operators kept;
   - pre-order AST node-type 4-grams (structure).
2. **Winnowing** (Schleimer, Wilkerson & Aiken, 2003; the MOSS algorithm) over token 10-grams with window 6: any shared run of
   ≥ 15 normalised tokens is guaranteed to produce a shared fingerprint, independent of renaming, comments or formatting.
3. **Features** per (suspect, source) pair: containment of suspect in source, containment of source in suspect,
   Jaccard, AST-gram Jaccard, size ratio, log(shared fingerprints).
4. **Gate** (identical at runtime and in evaluation): a pair is only scored if it shares ≥ 2 fingerprints and both files
   have ≥ 50 tokens. 622 of 4,379 pairs fall below it and are never flagged.
5. **Classifier**: histogram gradient boosting with monotonic constraints (more overlap can never lower the clone
   probability), selected over logistic regression on validation average precision (0.987 vs 0.983).
6. **Threshold**: the lowest threshold with validation false-positive rate ≤ 2% → **0.71**. FPR is used rather than
   precision because precision depends on how common clones are, which differs between this dataset (~65% clones)
   and a real hackathon (few).

### Data
| | Source | Files |
|---|---|---|
| Python | CPython 3.13 standard library (60–2,500 lines) | 450 |
| JavaScript | npm packages installed by the frontend (non-minified, ≤ 3 files per package) | 103 |

Files are split 70/15/15 into train/val/test **before** pairs are made, so no file or variant of it appears in two splits.

| Pair type | Label | How it is made |
|---|---|---|
| `rename_recomment` | clone | every identifier consistently renamed, every comment rewritten |
| `reorder` | clone | top-level functions/classes shuffled (Python, via `ast`) |
| `heavy_edit` | clone | ~10% of lines deleted, ~12% foreign lines spliced in |
| `partial_25_50` | clone | 25–50% contiguous chunk (≥ 30 tokens) pasted into an unrelated file |
| `partial_15_25` | clone | 15–25% chunk pasted into an unrelated file |
| `random_pair` | not clone | two unrelated files |
| `same_package` | not clone | two different files from the same package (hard negatives: shared idioms) |

### Results on the held-out test split (529 scored pairs, 361 clones)

| | Precision | Recall | F1 | False-positive rate |
|---|---|---|---|---|
| **Trained classifier** | **0.982** | **0.906** | **0.942** | **0.036** |
| Baseline: containment ≥ 0.5 | 0.991 | 0.590 | 0.740 | 0.012 |

ROC-AUC 0.973, average precision 0.989. The classifier catches **31 percentage points more clones** than the baseline
rule, mostly partial copies the rule misses, at the cost of a higher false-positive rate.

By case:

| Case | n | Result |
|---|---|---|
| reorder | 51 | 98.0% caught |
| heavy_edit | 81 | 96.3% caught |
| rename_recomment | 84 | 91.7% caught |
| partial 25–50% | 72 | 87.5% caught |
| partial 15–25% | 73 | 80.8% caught |
| random_pair | 97 | 99.0% correctly cleared |
| same_package | 71 | 93.0% correctly cleared |

By language:

| Language | Precision | Recall | False-positive rate |
|---|---|---|---|
| Python | 0.993 | 0.903 | 0.013 |
| JavaScript | 0.934 | 0.919 | **0.308** (4 of 13 negatives) |

### Limitations — read before quoting these numbers
- **JavaScript is not yet reliable.** Only 103 JS files were available and the test split has 13 scored negatives, so
  the 31% FPR is a noisy estimate, but it is the honest one. Before using VERIQO on JS-heavy events, retrain with a
  larger JS corpus (`--js-root` pointing at a bigger `node_modules`, or curated repos) and consider a per-language threshold.
- **Synthetic positives.** Real plagiarism is messier (partial rewrites, LLM paraphrases, mixed sources). Treat the
  figures as an upper bound until validated on labelled data from the dry-run hackathon (roadmap week 11–12).
- **Label noise in negatives.** CPython reuses code between modules, so some `same_package` "negatives" genuinely share
  copied code; part of the measured FPR is mislabelled data, not model error.
- **The model judges file pairs, not intent.** Reports are evidence for judges; risk bands never auto-disqualify.

### AI-generated code
No AI-code detector is trained or shipped. The study surveyed in whitebook Ch. 2 found existing detectors near 50% accuracy on
code. `ai_generated_prob` is left empty; IDE telemetry (bulk insertions without a paste, paste spikes) is used instead.

## 2. Skill matching threshold (Module A)

Whitebook Algorithm 1 uses a semantic-similarity threshold of 0.8. Measured with `sentence-transformers/all-MiniLM-L6-v2`
on bare skill names:

| Pair | Cosine |
|---|---|
| React / React Native | 0.740 |
| Machine Learning / Deep Learning | 0.689 |
| Blockchain / Ethereum | 0.687 |
| PostgreSQL / MySQL | 0.547 |
| AWS / Google Cloud | 0.520 |
| Python / Java | 0.450 |
| JavaScript / TypeScript | 0.401 |
| Vue.js / React | 0.375 |
| Docker / Kubernetes | 0.315 |
| Flask / FastAPI | 0.230 |
| Figma / UI/UX Design | 0.039 |

At 0.8 the semantic step would never fire, so VERIQO uses **0.65** (config `SEMANTIC_THRESHOLD`). Related skills below
that still earn partial credit through the taxonomy's category fallback (0.5, e.g. "Machine Learning" ← PyTorch).
The whitebook's Algorithm 1 should be updated to cite this measurement.

## 3. Telemetry suspicion (Algorithm 2)

Rule-based, as in the whitebook: `high` if (pasted + bulk-inserted) / all inserted > 0.60 and fewer than 3,000 typed
characters over the event; `medium` if the ratio > 0.40. Thresholds are untuned; calibrate them on the dry-run data.
