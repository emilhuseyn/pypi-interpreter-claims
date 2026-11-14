r"""Kill switch, second idea: does a package's declared Requires-Python hold against its own source?

THE IDEA UNDER TEST. Every PyPI distribution may declare `Requires-Python`, a machine-readable
claim - ">=3.8" - about which interpreters it supports. It is not documentation. pip ENFORCES it in
both directions: it refuses the distribution on an interpreter below the floor, and it selects the
distribution on an interpreter at or above it. So the claim decides what gets installed.

Whether the claim is true is checkable statically and exactly, using CPython's own parser. `ast.parse`
takes a `feature_version`, and parsing a file at (3, 8) fails if it uses syntax introduced later - a
`match` statement, `except*`, PEP 695 type parameters. A package declaring `>=3.8` whose own source
does not parse at 3.8 has published a claim its artefact contradicts, and the consumer finds out at
import time on an interpreter pip told them was supported.

Syntax is a LOWER BOUND on incompatibility and the paper would say so plainly: a package can parse
under an old interpreter and still call a standard-library function that does not exist there. That
makes any figure a floor, which is the conservative direction and the defensible one.

WHAT WOULD KILL THIS. A study that measures whether declared Python version support corresponds to
actual compatibility across a registry. Work on version incompatibility DETECTION, on dependency
conflict resolution, or on porting between Python 2 and 3 is adjacent and must be cited; work that
has already measured the declared-versus-actual gap on PyPI occupies it.

Same instrument discipline as the previous screen: DBLP, short title-shaped queries, five seconds
apart, and no verdict at all if any query failed.

    py 00c_novelty_requires_python.py
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "novelty_requires_python.json")
UA = {"User-Agent": "novelty-screen/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}
PACE = 5.0

QUERIES = [
    ("KILL", "Requires-Python"),
    ("KILL", "declared Python version compatibility"),
    ("KILL", "Python version constraint packages"),
    ("KILL", "package metadata accuracy PyPI"),
    ("KILL", "compatibility claim empirical packages"),
    ("near", "Python version incompatibility"),
    ("near", "version compatibility issues Python"),
    ("near", "dependency conflict Python"),
    ("near", "Python 2 to 3 migration empirical"),
    ("near", "backward compatibility library"),
    ("near", "breaking changes semantic versioning"),
    ("near", "API compatibility empirical study"),
    ("method", "abstract syntax tree parsing large scale"),
    ("method", "PyPI packages mining"),
    ("context", "metadata quality software registry"),
    ("context", "manifest declaration mismatch"),
]


def dblp(q):
    url = "https://dblp.org/search/publ/api?q=%s&h=30&format=json" % urllib.parse.quote(q)
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
                hits = (d.get("result", {}).get("hits", {}) or {}).get("hit", []) or []
                return [{"title": (h.get("info", {}).get("title") or "").strip().rstrip("."),
                         "year": h.get("info", {}).get("year", ""),
                         "venue": h.get("info", {}).get("venue", ""),
                         "doi": h.get("info", {}).get("doi", "")} for h in hits], None
        except Exception as e:
            last = str(e)
            time.sleep(8 * (attempt + 1))
    return None, last


def main():
    results, failures = [], []
    for kind, q in QUERIES:
        hits, err = dblp(q)
        if err:
            failures.append("%r: %s" % (q, err))
            print("  FAILED %-38s %s" % (q, err[:40]))
        else:
            results.append({"kind": kind, "query": q, "hits": hits})
            print("  ok     %-38s %2d hit(s)" % (q, len(hits)))
        time.sleep(PACE)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps({"queries": results, "failures": failures}, ensure_ascii=False, indent=1))

    print()
    print("=" * 100)
    if failures:
        print("NO VERDICT. %d query/queries failed; absence here is not evidence of absence."
              % len(failures))
        for f in failures:
            print("   %s" % f)
        return 1

    print("ALL %d QUERIES RETURNED. Read the titles." % len(QUERIES))
    print("=" * 100)
    for row in results:
        print()
        if not row["hits"]:
            print("%-8s %-34s  nothing indexed under this" % (row["kind"], row["query"]))
            continue
        print("%-8s %s" % (row["kind"], row["query"]))
        for h in row["hits"][:12]:
            print("   %-5s %-60s %s" % (h["year"], h["title"][:60], (h["venue"] or "")[:26]))
    print()
    print("written to research/novelty_requires_python.json")
    return 0


sys.exit(main())
