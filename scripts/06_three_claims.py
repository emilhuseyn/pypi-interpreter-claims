r"""How often do the three published interpreter claims agree, and where do they part company?

Reads data/claims.jsonl. No network.

THE THREE CLAIMS, and the asymmetry between them, which is the whole point:

  CLASSIFIERS      rendered on the project page. A human reads this one. pip ignores it entirely.
  REQUIRES-PYTHON  a PEP 440 specifier. pip ENFORCES it. Nothing displays it prominently.
  WHEEL TAGS       in every wheel's filename. pip ENFORCES these too. Nobody reads them.

COMPARISONS ARE MADE ONLY WHERE THEY MEAN SOMETHING. The first version of this analysis compared the
set of versions a specifier admits against the set the classifiers name, over a universe running to
3.14, and reported 84.3 percent disagreement. That was an artefact: ">=3.8" admits 3.14 and no
maintainer lists a version before they have tested it, so 382 of 458 projects were scored as
disagreeing over the open end of a range. The honest comparisons are the ones with a victim:

  PAGE OVERSTATES   a classifier names a released version the specifier excludes. A reader on that
                    version is told the package supports them; pip refuses to install it. Counted.
  TAGS OVERSTATE    every wheel is tagged for a version the specifier excludes. Counted.
  TAGS UNDERSTATE   the specifier admits versions no wheel is built for, and no sdist exists to fall
                    back to. pip says yes and then has nothing to install. Counted.
  OPEN END          the specifier admits versions the page does not name. NOT counted as a fault -
                    that is how "and later" is written. Reported separately so the reader can see
                    the size of what was excluded and why.

    py 06_three_claims.py
"""
import collections
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "claims.jsonl")
OUT = os.path.join(ROOT, "results", "three_claims.json")

RELEASED = set(range(0, 15))          # 3.0 through 3.14, as of 28.08.2026. 3.15 does not exist.


def satisfies(spec, minor):
    """Does 3.minor satisfy this specifier? None if any clause is unreadable - never ignored."""
    v = (3, minor)
    for clause in spec.split(","):
        c = clause.strip()
        if not c:
            continue
        m = re.match(r"^(>=|<=|==|!=|~=|>|<)\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?\.?\*?$", c)
        if not m:
            return None
        op, maj, mi = m.group(1), int(m.group(2)), m.group(3)
        if mi is None:
            ok = {">=": 3 >= maj, ">": 3 > maj, "<=": 3 <= maj, "<": 3 < maj,
                  "==": 3 == maj, "!=": 3 != maj, "~=": 3 >= maj}[op]
        else:
            b = (maj, int(mi))
            ok = {">=": v >= b, ">": v > b, "<=": v <= b, "<": v < b,
                  "==": v == b, "!=": v != b, "~=": v >= b and maj == 3}[op]
        if not ok:
            return False
    return True


def admitted(spec):
    out = set()
    for m in sorted(RELEASED):
        r = satisfies(spec, m)
        if r is None:
            return None
        if r:
            out.add(m)
    return out


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    rows = []
    for line in io.open(SRC, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    status = collections.Counter(r.get("status") for r in rows)
    read = [r for r in rows if r.get("status") == "read"]

    has_spec = [r for r in read if r.get("requires_python")]
    has_cls = [r for r in read if r.get("classifiers_py3")]
    has_whl = [r for r in read if r.get("wheel_tags")]

    print("=" * 98)
    print("WHAT THE INDEX PUBLISHES - %d drawn, %d with readable metadata" % (len(rows), len(read)))
    print("=" * 98)
    for k, v in status.most_common():
        print("   %-24s %5d   %5.1f%% of drawn" % (k, v, pct(v, len(rows))))
    print()
    print("   publish Requires-Python (pip enforces)   %5d   %5.1f%% of readable"
          % (len(has_spec), pct(len(has_spec), len(read))))
    print("   publish classifiers (the page shows)     %5d   %5.1f%%"
          % (len(has_cls), pct(len(has_cls), len(read))))
    print("   ship at least one wheel (pip enforces)   %5d   %5.1f%%"
          % (len(has_whl), pct(len(has_whl), len(read))))

    # HOW MANY OF THE THREE DOES A PROJECT PUBLISH AT ALL. The headline is about absence before it
    # is about disagreement: a claim nobody made cannot disagree with anything, and pip's guard has
    # nothing to enforce.
    combo = collections.Counter()
    for r in read:
        k = (bool(r.get("requires_python")), bool(r.get("classifiers_py3")), bool(r.get("wheel_tags")))
        combo[k] += 1
    print()
    print("=" * 98)
    print("HOW MANY OF THE THREE A PROJECT PUBLISHES")
    print("=" * 98)
    print("   %-14s %-14s %-12s %6s %8s" % ("Requires-Python", "classifiers", "wheel tags",
                                            "count", "share"))
    for k, v in sorted(combo.items(), key=lambda kv: -kv[1]):
        print("   %-14s %-14s %-12s %6d %7.1f%%"
              % ("yes" if k[0] else "-", "yes" if k[1] else "-", "yes" if k[2] else "-",
                 v, pct(v, len(read))))
    inert = sum(v for k, v in combo.items() if not k[0])
    print()
    print("   pip's version guard is INERT for          %5d   %5.1f%% of readable projects"
          % (inert, pct(inert, len(read))))
    print("   (no Requires-Python, so no interpreter is excluded and pip will install")
    print("    the project on anything it is asked to)")

    # ---- comparison 1: page against the specifier
    both = [r for r in read if r.get("requires_python") and r.get("classifiers_py3")]
    page_over, ghost, open_end = [], [], 0
    for r in both:
        adm = admitted(r["requires_python"])
        if adm is None:
            continue
        cls = set(r["classifiers_py3"])
        refused = sorted((cls & RELEASED) - adm)
        if refused:
            page_over.append({"project": r["project"], "spec": r["requires_python"],
                              "classifiers": sorted(cls), "refused": refused})
        if cls - RELEASED:
            ghost.append({"project": r["project"], "versions": sorted(cls - RELEASED)})
        if adm - cls:
            open_end += 1

    print()
    print("=" * 98)
    print("THE PAGE AGAINST THE SPECIFIER - %d projects publish both" % len(both))
    print("=" * 98)
    print("   PAGE NAMES A RELEASED VERSION PIP REFUSES  %5d   %5.1f%%"
          % (len(page_over), pct(len(page_over), len(both))))
    print("   page names a version that does not exist   %5d   %5.1f%%"
          % (len(ghost), pct(len(ghost), len(both))))
    print("   specifier admits versions the page omits   %5d   %5.1f%%   (not a fault - see header)"
          % (open_end, pct(open_end, len(both))))

    # ---- comparison 2: the wheels against the specifier
    spec_and_wheels = [r for r in read if r.get("requires_python") and r.get("wheel_tags")]
    tags_over, tags_under = [], []
    for r in spec_and_wheels:
        adm = admitted(r["requires_python"])
        if adm is None:
            continue
        tags = r["wheel_tags"]
        if "3.*" in tags or any(t.startswith("?") or t.startswith("py") for t in tags):
            continue                      # a universal or unparsable tag constrains nothing
        vers = {int(t.split(".")[1]) for t in tags if t.startswith("3.") and t != "3.*"}
        if not vers:
            continue
        if not (vers & adm):
            tags_over.append({"project": r["project"], "spec": r["requires_python"],
                              "tags": tags})
        missing = sorted(adm - vers)
        if missing and not r.get("n_sdists"):
            tags_under.append({"project": r["project"], "spec": r["requires_python"],
                               "tags": tags, "no_wheel_for": missing})

    # THE UNIVERSAL TAG IS THE FINDING HERE, not the disagreement count. Most wheels are
    # `py3-none-any`, which claims every Python 3 and therefore constrains nothing, so the second
    # machine-enforced claim is vacuous for almost every project that makes it. Report how many were
    # excluded for that reason rather than printing a small number with an arithmetic label that
    # does not describe it - the first version of this line said "6 after dropping universal tags",
    # which was the count of flagged cases and not the size of the population they came from.
    constraining = 0
    for r in spec_and_wheels:
        tags = r["wheel_tags"]
        if "3.*" in tags or any(t.startswith("?") for t in tags):
            continue
        if {t for t in tags if t.startswith("3.") and t != "3.*"}:
            constraining += 1

    print()
    print("=" * 98)
    print("THE WHEELS AGAINST THE SPECIFIER - %d projects publish both" % len(spec_and_wheels))
    print("=" * 98)
    print("   wheels carry a tag that CONSTRAINS a version %5d   %5.1f%%"
          % (constraining, pct(constraining, len(spec_and_wheels))))
    print("   the rest are universal (py3-none-any) and so")
    print("      say nothing about which version is supported %5d   %5.1f%%"
          % (len(spec_and_wheels) - constraining,
             pct(len(spec_and_wheels) - constraining, len(spec_and_wheels))))
    print()
    print("   of the %d constraining ones:" % constraining)
    print("      no wheel tagged for any admitted version   %5d" % len(tags_over))
    print("      an admitted version with no wheel and no")
    print("         sdist to fall back to                   %5d" % len(tags_under))

    if page_over:
        print()
        print("   every page-overstates case, printed in full:")
        for h in sorted(page_over, key=lambda x: x["project"])[:24]:
            print("     %-30s spec %-16s refuses the page's %s"
                  % (h["project"][:30], (h["spec"] or "")[:16],
                     ", ".join("3.%d" % c for c in h["refused"])))

    out = {"drawn": len(rows), "readable": len(read), "status": dict(status),
           "publishes": {"requires_python": len(has_spec), "classifiers": len(has_cls),
                         "wheels": len(has_whl)},
           "combinations": {"spec=%s,cls=%s,whl=%s" % k: v for k, v in combo.items()},
           "inert_guard": {"count": inert, "pct": round(pct(inert, len(read)), 2)},
           "page_vs_spec": {"both": len(both), "page_overstates": page_over,
                            "ghost_versions": ghost, "open_end": open_end},
           "wheels_vs_spec": {"both": len(spec_and_wheels), "constraining": constraining, "tags_overstate": tags_over,
                              "tags_understate": tags_under}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print()
    print("written to results/three_claims.json")
    return 0


sys.exit(main())
