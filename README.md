# Replication package: three published claims about Python interpreter support

Measurement code and data for the study *Three Claims, One Artefact: Declared Python Interpreter
Support on PyPI Against the Code It Describes*.

**Emil Huseynov**, Center for Information Technologies, Baku State University
<emil.huseynov.zabil@bsu.edu.az>

## What the study measures

A package on the Python Package Index declares which interpreters it supports in up to three places
at once:

| claim | where it lives | who reads it | enforced? |
|---|---|---|---|
| trove classifiers | `Programming Language :: Python :: 3.9` | rendered on the project page; this is what a person checks | **no**, pip ignores them |
| `Requires-Python` | a PEP 440 specifier such as `>=3.9` | nothing displays it prominently | **yes**, pip refuses the distribution outside the range |
| wheel tags | `cp39-cp39-manylinux_x86_64` in the filename | nobody | **yes**, matched against the running interpreter |

Nothing keeps any two of them in agreement, and none of them is checked against the code. This
package contains everything needed to reproduce that measurement, or to re-run it against a fresh
sample.

## Reproducing the reported figures without re-harvesting

The harvested data is included, so every number in the paper can be re-derived offline:

```
py scripts/08_analyse.py
```

That reads `data/claims.jsonl` and `data/source_floor.jsonl` and writes `results/analysis.json`,
printing every rate beside the population it is computed over. No network access is required and
nothing is downloaded.

## Re-running the harvest

Both harvest stages are resumable and write one JSON object per line as they go, so an interrupted
run continues rather than starting over.

```
py scripts/04_harvest_claims.py 1500     # the three published claims, one request per project
py scripts/07_source_floor.py            # the source against the declared floor
py scripts/08_analyse.py                 # every figure the paper quotes
```

`data/frame.json` holds the index size, the random seed (`20260828`) and the drawn project list. If
that file is present, `04_harvest_claims.py` reuses the recorded sample rather than drawing a new
one. **The index is a living resource**, so deleting `frame.json` and re-running measures a
different sample, which answers a different question: change in the index rather than change in
these projects.

Requires Python 3.9 or later and the standard library only. No third-party dependencies, no API
key, no account. Both data sources are public: PyPI's simple index and JSON API, and the
distributions PyPI serves.

## The two detectors

Both are exact rather than heuristic, and both are **lower bounds by construction**. A project
reported as contradicting its claim definitely does; a project reported as clean is not certified.

**Syntax.** `ast.parse(source, feature_version=(3, n))` is CPython's own parser applied at CPython's
own definition of release 3.n's grammar. A file that fails cannot be read by that interpreter at
all. Measured before being relied on: it gates the walrus operator and positional-only parameters
(3.8), `match` (3.10), `except*` (3.11) and PEP 695 type parameters (3.12). It does **not** gate
`int | str` annotations or the dictionary merge operator, which are ordinary syntax at any version
and fail at run time.

**Standard library.** An *unconditional* top-level import of a module that did not exist at the
declared floor, against a short table of modules whose introduction release is documented and
unambiguous (`tomllib` 3.11, `zoneinfo` and `graphlib` 3.9, `importlib.metadata` 3.8, `dataclasses`
and `contextvars` 3.7, and older entries). The table is short on purpose: a wrong entry manufactures
a violation, which is worse than missing one.

**Unconditional is the operative word.** An import inside `try`/`except ImportError`, or beneath a
`sys.version_info` test, is the correct handling of this exact problem. Counting it as a defect
would invert the finding, so guarded imports are recorded separately and reported in their own
right. In the sample, 94 projects guard correctly against 19 that do not.

## A correction that is part of the record

`scripts/03_reanalyse_claims.py` exists because the first analysis of this data reported **84.3
percent disagreement** between the classifiers and the specifier, and that figure was an artefact of
the instrument rather than a finding. It compared the set of versions a specifier admits against the
set the classifiers name, over a universe running to 3.14. An open-ended `>=3.8` admits every
version in that universe while classifiers can only name versions that exist and that someone
remembered to add, so 382 of 458 projects were scored as disagreeing over the open end of a range.

The honest comparison is asymmetric. A classifier naming a released version the specifier excludes
is a contradiction with a victim: a reader is told their version works and pip refuses. A specifier
admitting a version no classifier names is how a maintainer writes "and later". The first is 2.2
percent; the second is 83.4 percent and is not a fault.

The script carries both the correction and an account of what it corrects, because a corrected
figure with no account of what it replaced is a figure a reader has to take on trust.

## Layout

```
scripts/
  01_feasibility.py        early probe, 400 projects, source against declared floor
  02_two_claims.py         classifiers against the specifier, metadata only
  03_reanalyse_claims.py   the correction described above, and its reasoning
  04_harvest_claims.py     all three claims in one pass, resumable, keeps every field
  06_three_claims.py       the three-way comparison
  07_source_floor.py       the two detectors over every measured project
  08_analyse.py            every figure the paper quotes, with Wilson intervals
  11_gate.py               recomputes every number in the manuscript and fails on disagreement
data/
  frame.json               index size, seed, and the drawn project list
  claims.jsonl             what each project publishes, one object per line
  source_floor.jsonl       what each project's own code requires
  *.log                    what the harvest runs actually did
results/
  analysis.json            the derived figures, with denominators and intervals
```

`scripts/11_gate.py` is included because the paper relies on it. It re-derives every quantity stated
in the manuscript from `results/analysis.json` and refuses the build on any disagreement. On its
first run it found that the manuscript reported a sample of 2,000 projects in five places when the
frame actually drawn was 1,500, along with four references built into the bibliography and never
cited. Reading the paper would not have caught either.

## Snapshot

The PyPI simple index carried 879,335 projects on 28 August 2026. 1,500 names were drawn uniformly
at random without replacement with seed 20260828.

## Licence

The code is released under the MIT licence. The harvested data consists of metadata published by
PyPI and by the projects themselves, and is redistributed here for replication.
