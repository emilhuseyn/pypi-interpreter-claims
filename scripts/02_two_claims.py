r"""Two published claims about one artefact: the one pip enforces and the one the page shows.

Every PyPI project publishes interpreter support TWICE, in two places, in two formats, to two
audiences:

  Requires-Python     a version specifier, ">=3.8". MACHINE-ENFORCED. pip refuses to install the
                      distribution on an interpreter outside it and will silently pick an older
                      release instead. Not displayed prominently anywhere a human reads.
  Trove classifiers   "Programming Language :: Python :: 3.8", one line per version. RENDERED ON
                      THE PROJECT PAGE, in the sidebar, as the answer to "does this support my
                      Python". Completely ignored by pip.

Nothing requires them to agree. They are written in different files, in different syntaxes, and
neither tool nor registry validates one against the other. So a project can tell a reader on its own
page that it supports 3.7 while pip refuses to install it on 3.7, and a project can be installed by
pip on a version its page never claims.

This probe measures how often they disagree, and in which direction, over a uniform random sample of
the index. It needs metadata only - one request per project, no downloads - so it can cover a large
sample quickly and its cost to PyPI is one JSON fetch per project.

DIRECTIONS ARE NOT SYMMETRIC AND ARE COUNTED APART:

  PAGE CLAIMS MORE   a classifier names a version the specifier excludes. A reader is told a version
                     works and pip will not install it there. The reader's information is wrong.
  PAGE CLAIMS LESS   the specifier admits a version no classifier names. pip installs it somewhere
                     the project never said it supports.

    py 02_two_claims.py [n]        default 1500
"""
import collections
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "two_claims.json")
UA = {"User-Agent": "requires-python-audit/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
SEED = 20260828
# The interpreter versions a claim can be about. 3.0 to 3.3 are long dead but appear in classifiers,
# and excluding them would hide exactly the kind of stale claim this probe is looking for.
UNIVERSE = [(3, m) for m in range(0, 15)]

CLASSIFIER = re.compile(r"^Programming Language :: Python :: (\d+)\.(\d+)$")


def get(url, timeout=30):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            return None, "HTTP %s" % e.code
        except Exception as e:
            if attempt == 2:
                return None, str(e)[:60]
            time.sleep(2)
    return None, "unreachable"


def satisfies(spec, ver):
    """Does interpreter 3.ver satisfy this PEP 440 specifier? Conservative and explicit.

    Only the clause forms actually seen in Requires-Python are handled, and an unrecognised clause
    makes the whole specifier unreadable rather than being ignored. Ignoring a clause we cannot
    parse would silently widen the admitted set and manufacture disagreements.
    """
    v = (3, ver)
    for clause in spec.split(","):
        c = clause.strip()
        if not c:
            continue
        m = re.match(r"^(>=|<=|==|!=|~=|>|<)\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?\.?\*?$", c)
        if not m:
            return None
        op, maj, mi = m.group(1), int(m.group(2)), m.group(3)
        # A bound written without a minor - ">=3" or "<4" - constrains the major only.
        bound = (maj, int(mi)) if mi is not None else (maj, None)
        if bound[1] is None:
            ok = {">=": v[0] >= bound[0], ">": v[0] > bound[0], "<=": v[0] <= bound[0],
                  "<": v[0] < bound[0], "==": v[0] == bound[0], "!=": v[0] != bound[0],
                  "~=": v[0] >= bound[0]}[op]
        else:
            ok = {">=": v >= bound, ">": v > bound, "<=": v <= bound, "<": v < bound,
                  "==": v == bound, "!=": v != bound,
                  "~=": v >= bound and v[0] == bound[0]}[op]
        if not ok:
            return False
    return True


def admitted(spec):
    """The set of 3.x this specifier admits, or None if any clause could not be read."""
    out = set()
    for maj, mi in UNIVERSE:
        r = satisfies(spec, mi)
        if r is None:
            return None
        if r:
            out.add(mi)
    return out


def main():
    print("drawing the frame from PyPI's simple index")
    index, err = get("https://pypi.org/simple/", timeout=240)
    if err:
        print("STOP: could not read the index: %s" % err)
        return 2
    names = re.findall(r">([^<]+)</a>", index)
    print("index carries %d projects; drawing %d with seed %d" % (len(names), N, SEED))
    random.seed(SEED)
    sample = random.sample(names, min(N, len(names)))

    rows = []
    t0 = time.time()
    for i, name in enumerate(sample, 1):
        rec = {"project": name}
        raw, err = get("https://pypi.org/pypi/%s/json" % urllib.parse.quote(name))
        if err:
            rec["status"] = "metadata_failed"
            rows.append(rec)
            continue
        try:
            info = (json.loads(raw).get("info") or {})
        except Exception:
            rec["status"] = "metadata_unparsable"
            rows.append(rec)
            continue

        spec = info.get("requires_python")
        classifiers = set()
        for c in info.get("classifiers") or []:
            m = CLASSIFIER.match(c.strip())
            if m and int(m.group(1)) == 3:
                classifiers.add(int(m.group(2)))
        rec["requires_python"] = spec
        rec["classifiers"] = sorted(classifiers)

        if not spec and not classifiers:
            rec["status"] = "neither_claim"
        elif not spec:
            rec["status"] = "classifiers_only"
        elif not classifiers:
            rec["status"] = "specifier_only"
        else:
            adm = admitted(spec)
            if adm is None:
                rec["status"] = "specifier_unreadable"
            else:
                rec["status"] = "both_claims"
                rec["admitted"] = sorted(adm)
                rec["page_claims_more"] = sorted(classifiers - adm)
                rec["page_claims_less"] = sorted(adm - classifiers)
                rec["agree"] = not (classifiers - adm) and not (adm - classifiers)
        rows.append(rec)
        if i % 100 == 0:
            print("   %4d/%d  %.0fs" % (i, len(sample), time.time() - t0))

    status = collections.Counter(r.get("status") for r in rows)
    both = [r for r in rows if r.get("status") == "both_claims"]
    agree = [r for r in both if r["agree"]]
    more = [r for r in both if r["page_claims_more"]]
    less = [r for r in both if r["page_claims_less"]]

    def pct(a, b):
        return (100.0 * a / b) if b else 0.0

    print()
    print("=" * 94)
    print("WHAT THE INDEX PUBLISHES ABOUT ITS OWN INTERPRETER SUPPORT - %d drawn" % len(rows))
    print("=" * 94)
    for k, v in status.most_common():
        print("   %-24s %5d   %5.1f%% of drawn" % (k, v, pct(v, len(rows))))

    print()
    print("=" * 94)
    print("WHERE BOTH CLAIMS EXIST - %d projects" % len(both))
    print("=" * 94)
    print("   the two agree exactly           %5d   %5.1f%%" % (len(agree), pct(len(agree), len(both))))
    print("   THEY DISAGREE                   %5d   %5.1f%%"
          % (len(both) - len(agree), pct(len(both) - len(agree), len(both))))
    print("     page names a version pip refuses  %5d   %5.1f%%" % (len(more), pct(len(more), len(both))))
    print("     pip admits a version the page never claims %5d   %5.1f%%"
          % (len(less), pct(len(less), len(both))))

    print()
    print("   ten disagreements, for reading:")
    for r in (more + less)[:10]:
        print("     %-28s spec %-12s page %s"
              % (r["project"][:28], (r["requires_python"] or "")[:12],
                 ",".join("3.%d" % c for c in r["classifiers"])[:40]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(
        {"n": len(rows), "seed": SEED, "status": dict(status), "rows": rows},
        ensure_ascii=False, indent=1))
    print()
    print("written to results/two_claims.json")
    return 0


sys.exit(main())
