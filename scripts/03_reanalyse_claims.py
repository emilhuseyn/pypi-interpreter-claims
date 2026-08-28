r"""Re-analyse the two-claims sample after finding that 84.3 percent of it was the probe's own fault.

WHAT WENT WRONG, recorded here rather than quietly corrected. 02_two_claims.py compared the set of
interpreter versions a Requires-Python specifier admits against the set the trove classifiers name,
over a universe running to 3.14. An open-ended specifier such as ">=3.8" admits every version in
that universe, while classifiers can only name versions that exist and that the maintainer has got
round to adding. So ">=3.8" against classifiers listing 3.8 to 3.13 was scored as a disagreement on
3.14, and 382 of 458 projects were counted as disagreeing for that reason alone. The probe reported
84.3 percent disagreement. The real disagreement rate is a fifth of that and it is in the other
direction.

That number would have been the headline of a paper and it was an artefact of a range bound. It is
recorded here because a corrected figure with no account of what it corrects is a figure a reader
has to take on trust.

WHAT THE HONEST COMPARISON IS. The two claims are not symmetric and must not be scored as if they
were:

  PAGE NAMES A VERSION PIP REFUSES     A classifier names 3.7 and the specifier excludes 3.7. A
                                       reader on 3.7 is told the package supports them, and pip
                                       refuses to install it. This is a contradiction with a victim
                                       and it is counted as one.
  SPECIFIER ADMITS A VERSION THE PAGE  ">=3.8" admits 3.14 and no classifier says 3.14. This is
  DOES NOT NAME                        normal and expected: an open-ended range is how a maintainer
                                       says "and later", and classifiers are a list of versions
                                       tested. Counted and reported, never called a disagreement.

Reads results/two_claims.json. No network.

    py 03_reanalyse_claims.py
"""
import collections
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "results", "two_claims.json")
OUT = os.path.join(ROOT, "results", "claims_corrected.json")

# Python 3 minor versions RELEASED as of the snapshot, 28.08.2026. 3.14 shipped in October 2025;
# 3.15 has not. A classifier naming 3.15 is naming a version that does not exist, which is its own
# small finding and is counted rather than silently dropped.
RELEASED = set(range(0, 15))          # 3.0 through 3.14
LATEST = 14


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    d = json.load(io.open(SRC, encoding="utf-8"))
    rows = d["rows"]

    both = [r for r in rows if r.get("status") == "both_claims"]

    hard, silent, unreleased = [], [], []
    for r in both:
        adm = set(r.get("admitted") or [])
        cls = set(r.get("classifiers") or [])
        # A classifier naming a version that does not exist is not a claim about pip at all.
        ghost = cls - RELEASED
        real_cls = cls & RELEASED
        if ghost:
            unreleased.append((r["project"], sorted(ghost)))
        refused = sorted(real_cls - adm)
        if refused:
            hard.append({"project": r["project"], "spec": r["requires_python"],
                         "classifiers": sorted(cls), "refused": refused})
        quiet = sorted((adm & RELEASED) - cls)
        if quiet:
            silent.append({"project": r["project"], "spec": r["requires_python"],
                           "not_named": quiet})

    status = collections.Counter(r.get("status") for r in rows)
    n = len(rows)
    readable = n - status.get("metadata_failed", 0) - status.get("metadata_unparsable", 0)
    neither = status.get("neither_claim", 0)
    cls_only = status.get("classifiers_only", 0)
    spec_only = status.get("specifier_only", 0)

    print("=" * 96)
    print("HOW A PROJECT PUBLISHES ITS INTERPRETER SUPPORT - %d drawn, %d with readable metadata"
          % (n, readable))
    print("=" * 96)
    for k, v in status.most_common():
        print("   %-24s %5d   %5.1f%% of drawn" % (k, v, pct(v, n)))

    # THE HEADLINE THAT SURVIVES. pip enforces Requires-Python and nothing else. A project that does
    # not publish one is a project pip will install on any interpreter it is asked to.
    inert = neither + cls_only
    print()
    print("=" * 96)
    print("WHERE PIP'S VERSION GUARD IS INERT")
    print("=" * 96)
    print("   publish no Requires-Python at all      %5d   %5.1f%% of readable"
          % (inert, pct(inert, readable)))
    print("      publish neither claim               %5d   %5.1f%%" % (neither, pct(neither, readable)))
    print("      publish classifiers only            %5d   %5.1f%%" % (cls_only, pct(cls_only, readable)))
    print("   (classifiers are rendered on the project page and pip does not read them, so a")
    print("    project in the second group names versions to a human while pip installs it anywhere)")
    print()
    print("   publish Requires-Python                %5d   %5.1f%% of readable"
          % (spec_only + len(both), pct(spec_only + len(both), readable)))
    print("      and no classifiers, so the page is silent  %5d   %5.1f%%"
          % (spec_only, pct(spec_only, readable)))

    print()
    print("=" * 96)
    print("WHERE BOTH CLAIMS EXIST - %d projects, compared honestly" % len(both))
    print("=" * 96)
    print("   PAGE NAMES A VERSION PIP REFUSES      %5d   %5.1f%%   <- the contradiction"
          % (len(hard), pct(len(hard), len(both))))
    print("   specifier admits a version the page")
    print("      does not name (normal, not a fault) %5d   %5.1f%%"
          % (len(silent), pct(len(silent), len(both))))
    print("   classifiers naming an unreleased version %3d   %5.1f%%"
          % (len(unreleased), pct(len(unreleased), len(both))))

    if hard:
        print()
        print("   every contradiction found, because there are few enough to print in full:")
        for h in sorted(hard, key=lambda x: x["project"]):
            print("     %-30s spec %-14s page %s"
                  % (h["project"][:30], (h["spec"] or "")[:14],
                     ",".join("3.%d" % c for c in h["classifiers"])[:44]))
            print("     %-30s pip refuses the page's %s"
                  % ("", ", ".join("3.%d" % c for c in h["refused"])))

    if unreleased:
        print()
        print("   classifiers naming a version that does not exist:")
        for p, g in unreleased[:8]:
            print("     %-30s names %s" % (p[:30], ", ".join("3.%d" % x for x in g)))

    out = {"n": n, "readable": readable, "status": dict(status),
           "inert_guard": {"count": inert, "pct": round(pct(inert, readable), 2),
                           "neither": neither, "classifiers_only": cls_only},
           "both_claims": len(both),
           "contradiction": {"count": len(hard), "pct": round(pct(len(hard), len(both)), 2),
                             "rows": hard},
           "page_silent": {"count": len(silent), "pct": round(pct(len(silent), len(both)), 2)},
           "unreleased_classifiers": [{"project": p, "versions": g} for p, g in unreleased]}
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print()
    print("written to results/claims_corrected.json")
    return 0


sys.exit(main())
