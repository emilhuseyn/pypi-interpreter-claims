r"""Kill switch one, second instrument: DBLP with SHORT queries and generous pacing.

WHY THE FIRST SCREEN'S RESULTS WERE THROWN AWAY. 00_novelty.py leaned on Crossref's
query.bibliographic with long natural-language strings, and Crossref matched on individual words:
"type annotation coverage published packages claim" returned R packages for single-cell RNA
annotation, and "PEP 561 stub packages empirical" returned a paper on metallic via stubs. That is
not a thin result, it is a wrong instrument, and reading twenty-five such titles and concluding the
space is empty would be a novelty claim built on noise. Paper 27's screen learned exactly this and
changed instrument for the same reason.

DBLP indexes computer science venues and matches title words. It wants SHORT queries - three or four
words that would plausibly appear in a title - and it returns nothing useful for a sentence. It also
rate-limits, and it closed the connection on us after two runs in quick succession, so the pacing
here is deliberate and slow. This screen is not in a hurry.

Every query reports success or failure and the script refuses a verdict if any query failed. A zero
from a query that did not run is not a zero.

    py 00b_novelty_dblp.py
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
OUT = os.path.join(ROOT, "research", "novelty_dblp.json")
UA = {"User-Agent": "novelty-screen/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

PACE = 5.0          # seconds between queries; DBLP closed the connection at a faster rate

# Short and title-shaped. Ordered kill first.
QUERIES = [
    ("KILL", "py.typed"),
    ("KILL", "PEP 561"),
    ("KILL", "type annotation coverage"),
    ("KILL", "typed packages Python"),
    ("KILL", "annotation completeness"),
    ("near", "type annotations Python"),
    ("near", "Python type annotation empirical"),
    ("near", "gradual typing empirical"),
    ("near", "type stubs"),
    ("near", "DefinitelyTyped"),
    ("near", "TypeScript declaration files"),
    ("near", "type checker Python"),
    ("near", "types in the wild"),
    ("method", "mining PyPI"),
    ("method", "PyPI empirical study"),
    ("context", "software supply chain metadata"),
    ("context", "badge attestation"),
]


def dblp(q):
    url = "https://dblp.org/search/publ/api?q=%s&h=30&format=json" % urllib.parse.quote(q)
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
                hits = (d.get("result", {}).get("hits", {}) or {}).get("hit", []) or []
                out = []
                for h in hits:
                    i = h.get("info", {})
                    out.append({"title": (i.get("title") or "").strip().rstrip("."),
                                "year": i.get("year", ""), "venue": i.get("venue", ""),
                                "doi": i.get("doi", ""), "type": i.get("type", "")})
                return out, None
        except Exception as e:
            last = str(e)
            time.sleep(8 * (attempt + 1))       # 8, 16, 24, 32 - DBLP wants to be left alone
    return None, last


def main():
    results, failures = [], []
    for kind, q in QUERIES:
        hits, err = dblp(q)
        if err:
            failures.append("%r: %s" % (q, err))
            print("  FAILED %-34s %s" % (q, err[:44]))
        else:
            results.append({"kind": kind, "query": q, "hits": hits})
            print("  ok     %-34s %2d hit(s)" % (q, len(hits)))
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
        print()
        print("written to research/novelty_dblp.json")
        return 1

    print("ALL %d QUERIES RETURNED. Read the titles; do not count them." % len(QUERIES))
    print("=" * 100)
    for row in results:
        if not row["hits"]:
            print()
            print("%-8s %-30s  nothing indexed under this" % (row["kind"], row["query"]))
            continue
        print()
        print("%-8s %s" % (row["kind"], row["query"]))
        for h in row["hits"][:14]:
            print("   %-5s %-58s %s" % (h["year"], h["title"][:58], (h["venue"] or "")[:28]))
    print()
    print("written to research/novelty_dblp.json")
    return 0


sys.exit(main())
