# Paper 28, plan amendment A, 14.11.2026 (frozen before any of it is computed)

## Why an amendment

The 28.08.2026 analysis (submitted to JSEP, desk-rejected 29.10.2026) was not pre-specified. A
re-read of `scripts/07_source_floor.py` and `scripts/08_analyse.py` on 14.11.2026, before any new
computation, found four defects in the instrument:

1. **Scale truncation.** The syntax search starts at 3.4 (`LOW = 4`), so a project declaring
   `>=3.0` or `>3.0` is always "contradicted" (detected 3.4 > declared 3.0). Two of the 19 reported
   contradictions (`MAST-U-DMS-GUI`, `NeuroAnalysisTools`) are this artefact and nothing else.
2. **Specifier parsing.** `declared_floor()` reads only `>=3.x`, `~=3.x`, `==3.x`, `>3.x`. 32 measured
   projects that DO publish a specifier (`>=3`, `~=2.7`, `>=2.7, !=3.0.*, ...`) were filed under
   "declares nothing". The paper's "496 declare nothing" is really 464, and `ludi` (`>=3`, needs 3.8)
   is a contradiction that was counted as silence. `>3.4` was read as 3.5, but PEP 440 admits 3.4.1.
3. **"Exact" detectors are not exact.** Python's own documentation calls `ast.parse(feature_version=)`
   a best-effort attempt with a minimum supported version of 3.7. A probe on 14.11.2026 (Python
   3.13.7) showed it accepts async generators at 3.5, does not gate f-strings at 3.5, and does not
   gate parenthesised context managers, unparenthesised starred returns or relaxed decorators. The
   stdlib detector ignores PyPI backports that install under the stdlib name (`dataclasses`,
   `contextvars`, `pathlib`, ...); seven of the 19 contradictions are `import dataclasses` with a
   declared floor of 3.6, which the `dataclasses` backport makes valid if it is declared.
4. **Files that are never installed or imported.** Every `.py` member of the smallest distribution was
   read, including `setup.py`, tests and examples in sdists (`lme-python`'s flagged files are under
   `comparisons/` and `python/examples/`).

And one reporting defect: "94 projects handle the same situation correctly" counts any guarded import
of any table module, not a guarded import of a module newer than the project's own floor.

All numbers of the 28.08 analysis are superseded. The manuscript reports, for each headline, the old
value, the new value and which correction moved it.

## Data

- **Frame U (unchanged).** The 1,500 projects drawn on 28.08.2026 from 879,335 (seed 20260828),
  `data/claims.jsonl`. The same distribution file per project as before (smallest file not over
  6 MB, recorded URL; PyPI file URLs are immutable). Files are re-downloaded and their SHA-256 stored.
- **Frame P (new).** The 1,000 most-downloaded projects in the latest 30-day ranking published by the
  public `top-pypi-packages` dataset (hugovk.github.io/top-pypi-packages), snapshot date recorded.
  Metadata and the smallest distribution not over 6 MB are harvested on 14.11.2026 with the same
  rules. If no credential-free ranking can be fetched, Frame P is dropped and that is reported.
- **CPython releases.** Final releases and their dates from python.org's public release API. A minor
  version 3.n is "released" for a frame if 3.n.0 final is dated on or before the frame's snapshot date.

## Corrected instrument (applies to both frames)

- **C1 Specifier semantics.** `packaging` 25.0 `SpecifierSet`, evaluated against every final CPython
  3.x release dated on or before the snapshot. Admitted set = minor versions with at least one admitted
  final release. Declared floor = lowest admitted minor. A specifier admitting no 3.x release is its
  own class ("excludes Python 3"). An unparsable specifier is its own class and is counted.
- **C2 Real interpreters for syntax.** Primary syntax instrument: the real CPython parser of each
  minor version, from the official Docker images `python:3.N-slim` (3.4 to 3.14 where the image
  exists), run with `--network none` on a read-only copy of the extracted files, compile-only
  (`compile(src, path, "exec", dont_inherit=True)`), nothing executed, no bytecode written. A file's
  syntax floor is the lowest minor whose real parser accepts it. Below the oldest available image,
  syntax is assumed to be monotone (a file the oldest image rejects is rejected by older ones too).
  `ast.parse(feature_version=)` under 3.13 is kept only as the comparison in V1.
- **C3 Stdlib table from real interpreters.** For every top-level module name and every
  `importlib.*` submodule importable in the Linux 3.13 image, availability in each image is read with
  `importlib.util.find_spec` inside the container. Introduced at v = absent in every image before v,
  present from v on. Removed at r = present before r, absent from r on. Replaces the hand table.
- **C3b Backports and self-provided modules.** An unguarded import of a module missing at the
  declared floor is NOT a contradiction if (a) the distribution's own declared dependencies
  (Requires-Dist in wheel METADATA or sdist PKG-INFO, else `[project] dependencies` in pyproject.toml,
  else `install_requires` read literally from setup.cfg / setup.py) include a backport that installs
  that import name, with no environment marker excluding the affected interpreters, or (b) the
  distribution itself ships a top-level module or package of that name. Backport table (import name
  -> distribution): dataclasses -> dataclasses; contextvars -> contextvars; graphlib ->
  graphlib_backport; typing -> typing; enum -> enum34; pathlib -> pathlib, pathlib2 does not count;
  asyncio -> asyncio; statistics -> statistics; secrets -> python2-secrets; selectors -> selectors2
  does not count; zoneinfo, tomllib, importlib.metadata, importlib.resources have NO same-name
  backport. For removed modules (E1): cgi, cgitb -> legacy-cgi; any module -> standard-<name>;
  distutils is excluded from E1 entirely (setuptools shims it). Each backport's existence on PyPI is
  checked before use.
- **C4 Installed, importable files only.** Wheel: every `.py` member outside `*.data/`. Sdist: files
  inside a package directory (a directory holding `__init__.py`) or top-level modules of the
  distribution root or `src/`, excluding `setup.py`, `conftest.py`. Both: excluding any path with a
  component in {tests, test, testing, docs, doc, examples, example, benchmarks, benchmark}.
- **C5 Guards.** An import inside `try` or under `if` at any depth is guarded (unchanged). Primary
  stdlib finding: unguarded import at module level (fails at import time). Secondary: unguarded import
  at any depth (fails when that function runs). Relative imports are ignored.
- **Contradiction (floor).** Declared floor f: (i) some counted file is rejected by the real parser
  of 3.f, or (ii) a primary unguarded import names a module absent from 3.f, not excused by C3b.
- **Classifier against specifier.** A classifier `Programming Language :: Python :: 3.n` for a
  released 3.n of which no final release is admitted. Classifiers naming unreleased versions are
  counted separately. The reverse direction (admitted, not classified) is reported and not a fault.
- **Guarded "same situation" (fixes the 94).** A project handles the situation correctly if it has
  a guarded import of a module absent from its own declared floor (or from 3.0 if it declares none).
  Compared with the number that have the same import unguarded.

## Validation

- **V1 Real against approximate parser.** File-level 2x2 of real 3.v verdict against
  `ast.parse(feature_version=(3, v))` under 3.13, for v = 3.5 ... 3.13, over every counted file the
  3.13 parser accepts. Reported: agreement, approximate-rejects-real-accepts (would be false
  positives), real-rejects-approximate-accepts (misses).
- **V2 Vermin.** The independent rule-based minimum-version detector `vermin` (version pinned in the
  results), defaults plus `--no-tips`, run per project over the counted files. Compared with our
  detected floor per project, and as an alternative contradiction detector. Every project where our
  floor exceeds vermin's is inspected. Of projects vermin flags and we do not, up to 20 drawn at random
  (seed 20261114) are adjudicated by hand to estimate how much a broader detector adds and at what
  precision.
- **V3 Manual adjudication.** Every reported contradiction (both kinds, both frames) is opened by hand:
  file, line, construct, whether the file is installed and imported on the package's normal path,
  and a verdict (confirmed / instrument artefact, with the reason). Precision is reported.
- **D1 Dependency guard.** For each confirmed floor contradiction at interpreter 3.f: if some direct
  dependency (C3b sources) has no release, uploaded on or before the snapshot date and matching the
  requirement, whose files admit 3.f, pip cannot install the project there and the contradiction is
  reported as blocked by a dependency rather than as an installable failure.

## Exploratory, labelled as such

- **E1 Removed modules against open ranges.** A project admitting a released 3.v at which a module it
  imports unguarded at module level has been removed (C3), not excused by C3b.
- **E2** Frame P against Frame U on every rate, with both Wilson intervals; no hypothesis test.

## Reporting rules

- Every rate with its numerator, denominator and Wilson 95% interval; populations named once.
- A consistency gate checks that tables sum to their stated populations across tables and that every
  number in the text traces to `v2/results/`. Each check is shown to fail on a corrupted copy.
- Nothing is called "first" or "exact". Detectors are described with their measured disagreement.
