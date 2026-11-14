r"""Per-project measurement under plan amendment A (C1-C5, E1), for one frame.

Inputs: claims (U: data/claims.jsonl, P: v2/data/claims_P.jsonl), v2/data/dists_<F>.jsonl, the
container results in v2/data/out/ (compile_3.N.jsonl, modules_3.N.json), v2/data/releases.json.
No network. Writes v2/data/measure_<F>.jsonl and v2/results/stdlib_table.json.

    py v2/scripts/26_measure.py U|P
"""
import ast
import io
import json
import os
import sys

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(V2)
DATA = os.path.join(V2, "data")
OUT = os.path.join(DATA, "out")
FRAME = sys.argv[1]
SNAPSHOT = {"U": "2026-08-28", "P": "2026-11-14"}[FRAME]
IMAGES = list(range(4, 15))          # python:3.4-slim ... python:3.14-slim

# C3b. Import name -> distributions that install that import name. Existence on PyPI is checked by
# 27_backports_exist.py before any result is reported.
BACKPORT = {"dataclasses": ["dataclasses"], "contextvars": ["contextvars"],
            "graphlib": ["graphlib-backport"], "typing": ["typing"], "enum": ["enum34"],
            "pathlib": ["pathlib"], "asyncio": ["asyncio"], "statistics": ["statistics"],
            "secrets": ["python2-secrets"], "cgi": ["legacy-cgi"], "cgitb": ["legacy-cgi"]}
E1_EXCLUDED = {"distutils"}

REL = json.load(io.open(os.path.join(DATA, "releases.json"), encoding="utf-8"))
FINALS = [Version(r["version"]) for r in REL if r["date"] and r["date"] <= SNAPSHOT]
RELEASED_MINORS = sorted({v.minor for v in FINALS})


def admitted(spec):
    """C1. ('none'|'unparsable'|'no_py3'|'ok', set of admitted minors)."""
    if not spec or not spec.strip():
        return "none", set()
    try:
        ss = SpecifierSet(spec)
    except InvalidSpecifier:
        try:
            ss = SpecifierSet(spec.replace(" ", ""))
        except InvalidSpecifier:
            return "unparsable", set()
    mins = {v.minor for v in FINALS if ss.contains(v, prereleases=False)}
    return ("ok" if mins else "no_py3"), mins


def stdlib_table():
    names = [l.strip() for l in open(os.path.join(OUT, "names.txt")) if l.strip()]
    pres = {v: json.load(open(os.path.join(OUT, "modules_3.%d.json" % v))) for v in IMAGES}
    table, odd = {}, []
    for n in names:
        row = [bool(pres[v].get(n)) for v in IMAGES]
        if not any(row):
            continue
        first = row.index(True)
        last = len(row) - 1 - row[::-1].index(True)
        if not all(row[first:last + 1]):
            odd.append(n)                       # present, absent, present: a build artefact
            continue
        table[n] = {"intro": IMAGES[first] if first > 0 else None,      # None: 3.4 or earlier
                    "removed": IMAGES[last + 1] if last < len(row) - 1 else None}
    return table, odd


def file_floors(proj_idx):
    """Real-interpreter verdict per stored file, per image version."""
    return {v: COMPILE[v].get(proj_idx) for v in IMAGES}


def imports(tree):
    """[(name, guarded, module_level)] for absolute imports; from-imports also yield pkg.name."""
    out = []

    def walk(node, guarded, in_def):
        for ch in ast.iter_child_nodes(node):
            g = guarded or isinstance(node, (ast.Try, ast.If, ast.ExceptHandler)) or \
                (hasattr(ast, "TryStar") and isinstance(node, ast.TryStar))
            d = in_def or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if isinstance(ch, ast.Import):
                for a in ch.names:
                    out.append((a.name, g, not d))
            elif isinstance(ch, ast.ImportFrom) and ch.module and ch.level == 0:
                out.append((ch.module, g, not d))
                for a in ch.names:
                    out.append((ch.module + "." + a.name, g, not d))
            walk(ch, g, d)

    walk(tree, False, False)
    return out


def resolve(name, table):
    if name in table:
        return name
    top = name.split(".")[0]
    return top if top in table else None


def deps_installing(reqs, py_minor):
    """Canonical names of declared dependencies installed on 3.<py_minor> by default."""
    env = {"python_version": "3.%d" % py_minor, "python_full_version": "3.%d.0" % py_minor,
           "extra": ""}
    out = set()
    for r in reqs or []:
        try:
            q = Requirement(r)
        except Exception:
            continue
        try:
            if q.marker is not None and not q.marker.evaluate(env):
                continue
        except Exception:
            continue
        out.add(canonicalize_name(q.name))
    return out


def excused(mod, minor, rec):
    top = mod.split(".")[0]
    if top in set(rec.get("top_names") or []):
        return "self-provided"
    have = deps_installing(rec.get("requires_dist"), minor)
    for dist in BACKPORT.get(top, []):
        if canonicalize_name(dist) in have:
            return "backport:" + dist
    if canonicalize_name("standard-" + top) in have:
        return "backport:standard-" + top
    return None


def main():
    global COMPILE
    table, odd = stdlib_table()
    os.makedirs(os.path.join(V2, "results"), exist_ok=True)
    json.dump({"table": table, "inconsistent": odd, "images": ["3.%d" % v for v in IMAGES]},
              io.open(os.path.join(V2, "results", "stdlib_table.json"), "w", encoding="utf-8"),
              indent=0, sort_keys=True)
    COMPILE = {}
    for v in IMAGES:
        COMPILE[v] = {}
        for l in io.open(os.path.join(OUT, "compile_3.%d.jsonl" % v), encoding="utf-8"):
            r = json.loads(l)
            if r["f"] == FRAME:
                COMPILE[v][r["i"]] = r
    cpath = os.path.join(ROOT, "data", "claims.jsonl") if FRAME == "U" else \
        os.path.join(DATA, "claims_P.jsonl")
    claims = {json.loads(l)["project"]: json.loads(l) for l in io.open(cpath, encoding="utf-8")}
    dists = [json.loads(l) for l in io.open(os.path.join(DATA, "dists_%s.jsonl" % FRAME),
                                             encoding="utf-8")]
    fh = io.open(os.path.join(DATA, "measure_%s.jsonl" % FRAME), "w", encoding="utf-8")
    for d in dists:
        c = claims[d["project"]]
        kind, adm = admitted(c.get("requires_python"))
        floor = min(adm) if adm else None
        rec = {"project": d["project"], "frame": FRAME, "status": d["status"],
               "spec": c.get("requires_python"), "spec_kind": kind,
               "admitted": sorted(adm), "floor": floor,
               "classifiers": c.get("classifiers_py3") or [], "wheel_tags": c.get("wheel_tags"),
               "dist": d.get("dist"), "requires_dist": d.get("requires_dist"),
               "deps_source": d.get("deps_source"), "top_names": d.get("top_names")}
        # classifiers against specifier
        cls = set(rec["classifiers"])
        rec["page_refused"] = sorted((cls & set(RELEASED_MINORS)) - adm) if kind == "ok" else []
        rec["page_unreleased"] = sorted(cls - set(RELEASED_MINORS))
        if d["status"] != "measured":
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            continue
        stored = sorted(d["stored"])
        comp = file_floors(d["idx"])
        if any(comp[v] is None for v in IMAGES):
            rec["status"] = "not_compiled"
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            continue
        verdict = {fn: "".join(comp[v]["r"][k] for v in IMAGES) for k, fn in enumerate(stored)}
        # Deviation D-1 (found in the V2 inspection, 14.11.2026): Python 3.14 accepts
        # `except A, B:` (PEP 758), so Python 2 code written `except Error, e:` compiles on 3.14 and
        # nowhere else, with a different meaning. A file that only 3.14 accepts, rejected by 3.13 with
        # the PEP 758 message, counts as compiling nowhere unless the project declares 3.14 or later.
        pep758 = {fn for fn, s in verdict.items()
                  if s == "S" * (len(IMAGES) - 1) + "."
                  and "multiple exception types must be parenthesized" in
                  str((comp[13]["e"].get(fn) or [None, ""])[1])}
        if floor is None or floor < 14:
            for fn in pep758:
                verdict[fn] = "S" * len(IMAGES)
        rec["n_pep758_py2"] = len(pep758) if (floor is None or floor < 14) else 0
        ok_files = {fn: s for fn, s in verdict.items() if "." in s}
        rec["n_files"] = len(stored)
        rec["n_never_compile"] = len(stored) - len(ok_files)
        ffloor = {fn: IMAGES[s.index(".")] for fn, s in ok_files.items()}
        rec["syntax_floor"] = max(ffloor.values()) if ffloor else None
        # syntax against the declared floor: test at 3.f, or at 3.4 below the oldest image
        syn_fail = []
        if floor is not None and ok_files:
            tv = max(floor, IMAGES[0])
            k = IMAGES.index(tv) if tv in IMAGES else None
            if k is not None:
                for fn, s in ok_files.items():
                    if s[k] != ".":
                        later = "." in s[k + 1:]
                        err = comp[tv]["e"].get(fn)
                        syn_fail.append({"file": d["stored"][fn], "stored": fn,
                                         "kind": "needs-newer" if later else "too-old",
                                         "error": err, "file_floor": "3.%d" % ffloor[fn]})
            rec["syntax_tested_at"] = "3.%d" % tv if k is not None else None
        rec["syntax_fail"] = syn_fail
        # imports, parsed by the host's 3.13
        imp, unparsed = [], 0
        for fn in ok_files:
            try:
                src = open(os.path.join(DATA, "src", FRAME, str(d["idx"]), fn), "rb").read()
                tree = ast.parse(src)
            except Exception:
                unparsed += 1
                continue
            for name, g, top in imports(tree):
                m = resolve(name, table)
                if m:
                    imp.append({"module": m, "guarded": g, "module_level": top,
                                "file": d["stored"][fn]})
        rec["n_unparsed_by_313"] = unparsed
        rec["imports"] = imp
        # stdlib against the declared floor (primary: module level, secondary: any depth)
        lo = floor if floor is not None else 0
        st_primary, st_any, st_excused, guarded_same = [], [], [], set()
        for i in imp:
            m = i["module"]
            if table[m]["intro"] is None or lo >= table[m]["intro"]:
                continue                        # present at the floor (removals are E1's matter)
            if i["guarded"]:
                guarded_same.add(m)
                continue
            ex = excused(m, max(lo, 0), rec)
            if ex:
                st_excused.append({"module": m, "why": ex, "file": i["file"]})
                continue
            if floor is None:
                continue
            st_any.append(i)
            if i["module_level"]:
                st_primary.append(i)
        rec["stdlib_fail"] = st_primary
        rec["stdlib_fail_any_depth"] = st_any
        rec["stdlib_excused"] = st_excused
        rec["guarded_same"] = sorted(guarded_same)
        rec["unguarded_same_any"] = sorted({i["module"] for i in imp
                                            if not i["guarded"] and table[i["module"]]["intro"]
                                            and lo < table[i["module"]]["intro"]
                                            and not excused(i["module"], max(lo, 0), rec)})
        # detected floor: syntax floor and the newest unguarded module-level stdlib import
        intro = [table[i["module"]]["intro"] or 4 for i in imp
                 if not i["guarded"] and i["module_level"] and table[i["module"]]["intro"]
                 and not excused(i["module"], table[i["module"]]["intro"] - 1, rec)]
        rec["detected_floor"] = max([rec["syntax_floor"] or 4] + intro)
        rec["contradicts_floor"] = bool(
            floor is not None and (st_primary or any(f["kind"] == "needs-newer" for f in syn_fail)))
        # E1: a module removed at r, imported unguarded at module level, in a range admitting r+
        e1 = []
        for i in imp:
            m = i["module"]
            r = table[m]["removed"]
            if (r is None or m.split(".")[0] in E1_EXCLUDED or i["guarded"]
                    or not i["module_level"]):
                continue
            hit = sorted(v for v in adm if v >= r) if kind == "ok" else []
            if hit and not excused(m, r, rec):
                e1.append({"module": m, "removed": "3.%d" % r, "admits": "3.%d" % hit[0],
                           "file": i["file"]})
        rec["e1_removed"] = e1
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.close()
    print("frame %s: %d records; stdlib table %d modules, %d inconsistent across images"
          % (FRAME, len(dists), len(table), len(odd)))


COMPILE = {}
main()
