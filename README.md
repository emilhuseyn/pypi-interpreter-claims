# Replication package: declared Python version support on PyPI

Scripts, metadata-level data, results and hand-adjudication records for the article. No third-party
source code is redistributed: every measured file is identified by its PyPI URL and SHA-256 in
`v2/data/dists_U.jsonl` and `v2/data/dists_P.jsonl`, and `v2/scripts/23_fetch_extract.py` downloads
and extracts it again.

## Re-derive every number offline

    python v2/scripts/28_analyse.py

reads only the files in this package and rewrites `v2/results/analysis.json` and
`v2/draft/numbers.tex` (the macros the manuscript prints). `v2/scripts/33_gate.py` checks the
manuscript against them and `v2/scripts/34_gate_mutation.py` shows each check failing on corrupted
input.

## Re-run the measurement

| step | script | needs |
|---|---|---|
| Frame U sample and metadata (28.08.2026) | `scripts/04_harvest_claims.py` | network |
| CPython releases, Frame P metadata | `v2/scripts/22_frames.py` | network |
| download and extract counted files | `v2/scripts/23_fetch_extract.py U|P` | network |
| compile in CPython 3.4 to 3.14, module table | `v2/scripts/25_run_containers.py` | Docker, official `python:3.N-slim` images; runs with `--network none`, compiles only |
| per-project measurement | `v2/scripts/26_measure.py U|P` | none |
| ast approximation and Vermin 1.9.2 | `v2/scripts/27_validate.py U|P <vermin>` | Vermin |
| dependency check | `v2/scripts/29_deps_guard.py` | network |
| evidence for the case-by-case inspection | `v2/scripts/32_evidence.py U|P` | none |
| release-time check of one wheel or sdist | `v2/tools/check_release.py` | `packaging` |
| references | `v2/scripts/30_refs.py` | network |

`v2/research/PLAN_AMENDMENT_2026-11-14.md` is the analysis plan, committed before the corrected
instrument was run. `v2/research/adjudication.csv` holds the verdict and reason for every flagged
project. `data/source_floor.jsonl` is the earlier (28.08.2026) analysis of Frame U, kept for the
comparison reported in the article.

Data sources are public and need no credential: PyPI's simple index and JSON API, the files PyPI
serves, python.org's release list, and the `top-pypi-packages` ranking.
