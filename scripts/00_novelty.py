r"""Kill switch one: has anyone already measured what the py.typed marker actually certifies?

THE IDEA UNDER TEST. PEP 561 lets a Python package ship an empty file named `py.typed`. It is a
machine-readable published assurance and every downstream type checker acts on it: with the marker,
mypy and pyright read the package's inline annotations and check calls into it; without it, they
ignore the package entirely. The marker is binary. It says the package is typed. It says nothing
about HOW MUCH of the package is typed, and an unannotated function inside a py.typed package does
not fail - it silently returns `Any`, which propagates into the consumer's own code and disables
checking there too. So a published assurance licenses an inference it does not support, and the
failure is silent by design.

WHAT WOULD KILL THIS. The field has an established literature on Python type annotation ADOPTION -
how many annotations exist, how they evolve, whether checkers agree. That literature is adjacent and
must be cited, and it does not occupy this. What occupies it is a study that measures, across a
sample of packages, whether the py.typed CLAIM corresponds to annotation coverage, or that measures
the downstream consequence of the gap. If one exists, this dies today rather than after a manuscript
is written.

INSTRUMENTS. DBLP first, then Crossref. Both are free and unmetered. Semantic Scholar is not used:
it returned 429 on nine of twelve queries during paper 27's screen even with backoff to 90 seconds,
and an instrument that loses three quarters of its queries cannot support a novelty claim. OpenAlex
is metered and is not used either.

A ZERO FROM A FAILED QUERY IS NOT A ZERO. Every query reports whether it succeeded, and the summary
refuses to state a verdict if any query failed.

    py 00_novelty.py
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
OUT = os.path.join(ROOT, "research", "novelty.json")
UA = {"User-Agent": "novelty-screen/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

# Ordered from the query that would kill the idea outright to the ones that map the neighbourhood.
QUERIES = [
    ("KILL", "py.typed marker PEP 561 completeness"),
    ("KILL", "type annotation coverage published packages claim"),
    ("KILL", "gradual typing Any propagation empirical study packages"),
    ("KILL", "PEP 561 stub packages empirical"),
    ("near", "Python type annotations empirical study"),
    ("near", "evolution of type annotations Python"),
    ("near", "Python 3 types in the wild type systems"),
    ("near", "type checker disagreement Python mypy pytype"),
    ("near", "gradual type system unsoundness dynamic languages"),
    ("near", "TypeScript type declaration files quality empirical"),
    ("near", "DefinitelyTyped type definitions correctness"),
    ("method", "mining PyPI packages empirical study"),
    ("method", "static analysis abstract syntax tree large scale Python"),
    ("context", "software supply chain published assurance metadata"),
    ("context", "machine readable claim software artefact trust"),
]


def get(url, timeout=45):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            if attempt == 3:
                return None, str(e)
            time.sleep(3)
    return None, "unreachable"


def dblp(q):
    url = "https://dblp.org/search/publ/api?q=%s&h=25&format=json" % urllib.parse.quote(q)
    d, err = get(url)
    if err:
        return None, err
    hits = (d.get("result", {}).get("hits", {}) or {}).get("hit", []) or []
    out = []
    for h in hits:
        i = h.get("info", {})
        out.append({"title": i.get("title", ""), "year": i.get("year", ""),
                    "venue": i.get("venue", ""), "doi": i.get("doi", ""),
                    "url": i.get("ee", "")})
    return out, None


def crossref(q):
    url = ("https://api.crossref.org/works?rows=25&select=title,DOI,issued,container-title,type"
           "&query.bibliographic=%s" % urllib.parse.quote(q))
    d, err = get(url)
    if err:
        return None, err
    out = []
    for it in d.get("message", {}).get("items", []):
        out.append({"title": (it.get("title") or [""])[0],
                    "year": ((it.get("issued", {}).get("date-parts") or [[None]])[0] or [None])[0],
                    "venue": (it.get("container-title") or [""])[0],
                    "doi": it.get("DOI", ""), "url": ""})
    return out, None


def main():
    results, failures = [], []
    for kind, q in QUERIES:
        row = {"kind": kind, "query": q, "dblp": None, "crossref": None}
        d, err = dblp(q)
        if err:
            failures.append("dblp %r: %s" % (q, err))
            print("  FAILED dblp     %-52s %s" % (q[:52], err[:30]))
        else:
            row["dblp"] = d
            print("  ok     dblp     %-52s %d hit(s)" % (q[:52], len(d)))
        time.sleep(0.4)

        c, err = crossref(q)
        if err:
            failures.append("crossref %r: %s" % (q, err))
            print("  FAILED crossref %-52s %s" % (q[:52], err[:30]))
        else:
            row["crossref"] = c
            print("  ok     crossref %-52s %d hit(s)" % (q[:52], len(c)))
        time.sleep(0.4)
        results.append(row)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps({"queries": results, "failures": failures}, ensure_ascii=False, indent=1))

    print()
    print("=" * 94)
    if failures:
        # A screen that lost queries cannot say the space is empty. It says it could not look.
        print("NO VERDICT. %d query/queries failed, so an absence here is not evidence of absence."
              % len(failures))
        for f in failures:
            print("   %s" % f)
        print()
        print("written to research/novelty.json - rerun before drawing any conclusion")
        return 1

    print("ALL %d QUERIES RETURNED. The titles below are for reading, not for counting."
          % (len(QUERIES) * 2))
    print("=" * 94)
    for row in results:
        if row["kind"] != "KILL":
            continue
        print()
        print("KILL QUERY: %s" % row["query"])
        seen = set()
        for src in ("dblp", "crossref"):
            for h in row[src] or []:
                t = (h["title"] or "").strip().rstrip(".")
                k = t.lower()
                if k in seen or not t:
                    continue
                seen.add(k)
                print("   %-4s %-88s" % (h["year"] or "", t[:88]))
    print()
    print("written to research/novelty.json")
    print()
    print("READ THE TITLES. Paper 27's screen recorded the lesson: three of four agent")
    print("recommendations did not survive reading the titles they were based on.")
    return 0


sys.exit(main())
