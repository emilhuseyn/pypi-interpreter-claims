r"""Every number the manuscript is allowed to quote, produced in one place from both data files.

Joins data/claims.jsonl (what each project PUBLISHES about its interpreter support) with
data/source_floor.jsonl (what its own source actually REQUIRES). No network.

The paper's whole argument is that a claim without its basis is not a measurement, so this script
carries a denominator beside every rate and refuses to print a percentage whose population it has
not just named. Every population is defined once, here, and the manuscript uses these names:

  DRAWN         the 1,500 sampled uniformly from the index
  READABLE      those whose PyPI metadata could be read
  DECLARING     readable projects that publish a Requires-Python specifier
  BOTH CLAIMS   declaring projects that also publish trove classifiers
  MEASURED      projects whose own distribution could be read and parsed
  EFFECTIVE     measured projects that declare a floor, so the claim can be tested against the code

COMPARISONS ARE ASYMMETRIC AND ARE MADE THAT WAY. A classifier naming a released version the
specifier excludes is a contradiction with a victim. A specifier admitting a version no classifier
names is how "and later" is written and is not a fault. The first analysis of this data conflated
them and reported 84.3 percent disagreement, which was an artefact of a range bound.

    py 08_analyse.py
"""
import collections
import io
import json
import os
import re
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIMS = os.path.join(ROOT, "data", "claims.jsonl")
FLOOR = os.path.join(ROOT, "data", "source_floor.jsonl")
FRAME = os.path.join(ROOT, "data", "frame.json")
OUT = os.path.join(ROOT, "results", "analysis.json")

RELEASED = set(range(0, 15))          # 3.0 through 3.14 as of 28.08.2026; 3.15 does not exist


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def wilson(k, n, z=1.96):
    """Wilson rather than the normal approximation: at n=872 and p near 0.02 the normal interval
    runs below zero and is not usable."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (100 * (c - h), 100 * (c + h))


def rate(label, k, n, note=""):
    lo, hi = wilson(k, n)
    print("   %-46s %5d of %-5d = %5.1f%%  [%.1f, %.1f]%s"
          % (label, k, n, pct(k, n), lo, hi, ("  " + note) if note else ""))
    return {"k": k, "n": n, "pct": round(pct(k, n), 4),
            "lo": round(lo, 4), "hi": round(hi, 4)}


def satisfies(spec, minor):
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


def load(path):
    rows = []
    for line in io.open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def main():
    frame = json.load(io.open(FRAME, encoding="utf-8"))
    claims = load(CLAIMS)
    floors = {r["project"]: r for r in load(FLOOR)}

    drawn = len(claims)
    readable = [r for r in claims if r.get("status") == "read"]
    out = {"frame": {"index_size": frame["index_size"], "seed": frame["seed"],
                     "drawn": drawn, "readable": len(readable)}}

    print("=" * 104)
    print("THE FRAME - PyPI simple index, %d projects, %d drawn uniformly with seed %d"
          % (frame["index_size"], drawn, frame["seed"]))
    print("=" * 104)
    status = collections.Counter(r.get("status") for r in claims)
    for k, v in status.most_common():
        print("   %-30s %5d   %5.1f%% of drawn" % (k, v, pct(v, drawn)))
    out["status"] = dict(status)

    # ---- what each project publishes
    print()
    print("=" * 104)
    print("THREE CLAIMS ABOUT ONE PROPERTY - over the %d readable" % len(readable))
    print("=" * 104)
    has_spec = [r for r in readable if r.get("requires_python")]
    has_cls = [r for r in readable if r.get("classifiers_py3")]
    has_whl = [r for r in readable if r.get("wheel_tags")]
    out["publishes"] = {
        "requires_python": rate("Requires-Python, which pip ENFORCES", len(has_spec), len(readable)),
        "classifiers": rate("trove classifiers, which the PAGE SHOWS", len(has_cls), len(readable)),
        "wheels": rate("a wheel, whose tags pip ENFORCES", len(has_whl), len(readable)),
    }

    combo = collections.Counter()
    for r in readable:
        combo[(bool(r.get("requires_python")), bool(r.get("classifiers_py3")),
               bool(r.get("wheel_tags")))] += 1
    print()
    print("   %-16s %-13s %-11s %6s %8s" % ("Requires-Python", "classifiers", "wheel tags",
                                            "count", "share"))
    for k, v in sorted(combo.items(), key=lambda kv: -kv[1]):
        print("   %-16s %-13s %-11s %6d %7.1f%%"
              % ("yes" if k[0] else "-", "yes" if k[1] else "-", "yes" if k[2] else "-",
                 v, pct(v, len(readable))))
    out["combinations"] = {"spec=%s|cls=%s|whl=%s" % k: v for k, v in combo.items()}

    inert = sum(v for k, v in combo.items() if not k[0])
    print()
    out["inert_guard"] = rate("pip's version guard is INERT (no specifier)", inert, len(readable))
    print("      pip excludes no interpreter for these, so it will install them on anything")

    # ---- the page against the specifier
    both = [r for r in readable if r.get("requires_python") and r.get("classifiers_py3")]
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
    print("=" * 104)
    print("THE PAGE AGAINST THE SPECIFIER - %d projects publish both" % len(both))
    print("=" * 104)
    out["page_vs_spec"] = {
        "both": len(both),
        "page_overstates": rate("page names a RELEASED version pip refuses",
                                len(page_over), len(both)),
        "ghost": rate("page names a version that does not exist", len(ghost), len(both)),
        "open_end": rate("specifier admits a version the page omits", open_end, len(both),
                         "NOT a fault"),
        "rows": page_over, "ghost_rows": ghost,
    }

    # ---- the wheels against the specifier
    sw = [r for r in readable if r.get("requires_python") and r.get("wheel_tags")]
    constraining = 0
    for r in sw:
        tags = r["wheel_tags"]
        if "3.*" in tags or any(t.startswith("?") for t in tags):
            continue
        if {t for t in tags if t.startswith("3.") and t != "3.*"}:
            constraining += 1
    print()
    print("=" * 104)
    print("THE WHEEL TAGS - %d projects publish a specifier and at least one wheel" % len(sw))
    print("=" * 104)
    out["wheel_tags"] = {
        "both": len(sw),
        "constraining": rate("wheels carry a tag that constrains a version", constraining, len(sw)),
        "universal": rate("universal py3-none-any, so the tag says nothing",
                          len(sw) - constraining, len(sw)),
    }
    print("      of the two claims pip enforces, one is vacuous for almost every project making it")

    # ---- the source against the declared floor
    measured = [r for r in floors.values() if r.get("status") == "measured"]
    declaring = [r for r in measured if r.get("declared_floor") is not None]
    silent = [r for r in measured if r.get("declared_floor") is None]
    contra = [r for r in declaring if r.get("contradicts")]
    by_syntax = [r for r in contra if r["syntax_floor"] > r["declared_floor"]]
    by_stdlib = [r for r in contra if r.get("stdlib_unguarded")]
    guarded = [r for r in measured if r.get("stdlib_guarded")]

    print()
    print("=" * 104)
    print("THE SOURCE AGAINST THE DECLARED FLOOR - %d projects measured against their own code"
          % len(measured))
    print("=" * 104)
    print("   declare a floor, so the claim is testable  %5d" % len(declaring))
    print("   declare nothing, so pip's guard is inert   %5d" % len(silent))
    print()
    out["source_vs_claim"] = {
        "measured": len(measured), "declaring": len(declaring), "silent": len(silent),
        "contradicts": rate("CONTRADICT their own declared floor", len(contra), len(declaring)),
        "by_syntax": len(by_syntax), "by_stdlib": len(by_stdlib),
        "guarded": rate("guard the import correctly instead", len(guarded), len(measured)),
        "rows": [{"project": r["project"], "declared": "3.%d" % r["declared_floor"],
                  "detected": "3.%d" % r["detected_floor"],
                  "syntax": "3.%d" % r["syntax_floor"],
                  "stdlib": r.get("stdlib_unguarded")} for r in contra],
    }
    print("      by syntax the declared floor cannot parse  %5d" % len(by_syntax))
    print("      by an unguarded stdlib import              %5d" % len(by_stdlib))

    # A CONTRADICTION ABOUT AN INTERPRETER NOBODY RUNS IS NOT THE SAME AS ONE ABOUT A LIVE ONE, and
    # reading the nineteen showed both kinds. Three of them declare >=3.0 or >=3.1 and need 3.4;
    # that is formally a false claim and practically nothing, because no one installs on Python 3.1.
    # Two more concern 3.5. The rest are about versions in real use, and psychopy-visionscience
    # declaring 3.7 while importing importlib.metadata, or tag-publish declaring 3.10 while
    # importing tomllib, are live breakages in packages people install today. Report both rates:
    # the formal one, and the one that can actually bite. This is the same separation paper 27 made
    # between a declared exclusion and an effective one.
    LIVE_FLOOR = 6          # 3.5 and below reached end of life years before the snapshot
    live_declaring = [r for r in declaring if r["declared_floor"] >= LIVE_FLOOR]
    live_contra = [r for r in contra if r["declared_floor"] >= LIVE_FLOOR]
    print()
    out["contradicts_live"] = rate(
        "CONTRADICT, counting only floors of 3.6 or later", len(live_contra), len(live_declaring))
    print("      %d of the %d contradictions concern 3.5 or earlier, which nothing still runs"
          % (len(contra) - len(live_contra), len(contra)))

    # THE HONEST HEADLINE. "A third of the index is unguarded" would be true and misleading: most of
    # those projects run on 3.4 anyway and pip's silence costs them nothing. The number that means
    # something is how many projects pip will install onto an interpreter that cannot run them.
    silent_needing = [r for r in silent if r["detected_floor"] > 4]
    silent_modern = [r for r in silent if r["detected_floor"] >= 7]
    print()
    print("   of the %d that declare nothing, what their source actually needs:" % len(silent))
    c = collections.Counter(r["detected_floor"] for r in silent)
    for k in sorted(c):
        print("      3.%-3d %5d   %5.1f%%" % (k, c[k], pct(c[k], len(silent))))
    out["silent_detected"] = {"3.%d" % k: v for k, v in sorted(c.items())}
    print()
    out["silent_needing_37"] = rate("declare nothing AND need 3.7 or later",
                                    len(silent_modern), len(silent))

    broken = len(contra) + len(silent_modern)
    print()
    print("=" * 104)
    print("WHERE PIP PERMITS AN INSTALLATION THAT CANNOT WORK")
    print("=" * 104)
    out["installable_but_broken"] = rate(
        "wrong floor declared, or none declared and 3.7+ needed", broken, len(measured))
    print("      %d contradict a declared floor, %d declare nothing and need 3.7 or later"
          % (len(contra), len(silent_modern)))
    print("      Both detectors are FLOORS, so this is a lower bound in both directions:")
    print("      a violation found is certain, a project found clean is not certified.")

    # ---- how far above its evidence a declared floor sits (not a fault; context)
    gaps = [r["declared_floor"] - r["detected_floor"] for r in declaring
            if r["declared_floor"] >= r["detected_floor"]]
    if gaps:
        print()
        print("   declared floor minus detected floor, over the %d that do not contradict:"
              % len(gaps))
        print("      median %.0f minor versions, mean %.2f, max %d"
              % (st.median(gaps), st.fmean(gaps), max(gaps)))
        print("      (NOT a defect - the detectors are lower bounds, so a higher declared floor may")
        print("       be justified by a runtime dependency this study cannot see)")
        out["declared_above_detected"] = {"n": len(gaps), "median": st.median(gaps),
                                          "mean": round(st.fmean(gaps), 3), "max": max(gaps)}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print()
    print("written to results/analysis.json")
    return 0


sys.exit(main())
