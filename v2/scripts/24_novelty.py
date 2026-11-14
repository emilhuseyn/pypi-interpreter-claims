r"""Novelty re-run for the retarget (14.11.2026): short title-shaped queries, paced.

DBLP answered every request on 14.11.2026 with an anti-bot challenge page (HTTP 202, "Making sure
you're not a bot"), which this script does not try to get past. The same queries therefore go to
Semantic Scholar's public search API (2015 onwards) and Crossref's title search.

Prints every hit (year, venue, title, DOI) so the titles are read, not counted. A control query
that must return results ("PyPI") and one that must return none on this topic are included; a run
where the positive control is empty is a dead instrument, not an empty literature.

    py v2/scripts/24_novelty_dblp.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(V2, "research", "novelty_2026-11-14.json")
UA = {"User-Agent": "novelty-screen/2.0"}
Q = ["Requires-Python", "python_requires", "Python version compatibility",
     "minimum Python version", "Python interpreter version", "Python version support",
     "trove classifiers", "PyPI metadata", "package metadata quality", "Python 3 transition",
     "Python 2 to Python 3", "environment dependency inference Python", "Python language features",
     "compatibility issues Python", "Python syntax evolution", "Python version upgrade",
     "PyPI empirical", "PyPI ecosystem", "Python dependency", "language version compatibility",
     "declared compatibility", "version constraints package", "deprecated Python",
     "Python standard library", "build backend Python", "wheel Python packaging",
     # controls
     "PyPI", "zebrafish cardiac"]
Q = [q for q in Q if not q.startswith("#")]


def fetch(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(10 * (a + 1))
    return None


def s2(q):
    d = fetch("https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        {"query": q, "limit": 60, "year": "2015-2026",
         "fields": "title,year,venue,externalIds,authors"}), tries=3)
    if d is None:                       # public pool answers 429 under load; recorded, not hidden
        S2_FAILED.append(q)
        return []
    return [{"year": h.get("year"), "venue": h.get("venue"), "title": h.get("title"),
             "doi": (h.get("externalIds") or {}).get("DOI"),
             "authors": [a.get("name") for a in h.get("authors") or []], "src": "s2"}
            for h in d.get("data") or []]


def crossref(q):
    d = fetch("https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.title": q, "rows": 40, "filter": "from-pub-date:2015-01-01",
         "select": "DOI,title,issued,container-title,author"}))
    return [{"year": (h.get("issued", {}).get("date-parts") or [[None]])[0][0],
             "venue": (h.get("container-title") or [""])[0], "title": " ".join(h.get("title") or []),
             "doi": h["DOI"], "authors": ["%s %s" % (a.get("given", ""), a.get("family", ""))
                                          for a in h.get("author") or []], "src": "crossref"}
            for h in d["message"]["items"]] if d else []


S2_FAILED = []
out = {}
for q in Q:
    hits = s2(q)
    time.sleep(4)
    hits += crossref(q)
    out[q] = hits
    print("== %-40s %3d" % (q, len(hits)))
    for h in sorted(out[q], key=lambda x: -(int(x["year"] or 0))):
        print("   %s %-8s %-28s %s" % (h["year"], h["src"], str(h["venue"])[:28],
                                         (h["title"] or "")[:110]))
    time.sleep(5)
out["_s2_failed"] = S2_FAILED
print("Semantic Scholar unavailable (429) for %d of %d queries" % (len(S2_FAILED), len(Q)))
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("written", OUT)
