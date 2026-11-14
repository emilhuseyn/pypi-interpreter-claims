r"""Print the evidence for every flagged case (V3 hand adjudication): the offending line of source,
the file's archive path, the declared floor and the declared dependencies. The verdicts themselves
are written by hand into v2/research/adjudication.csv.

    py v2/scripts/32_evidence.py U|P [floor|e1]
"""
import ast
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(V2, "data")
F = sys.argv[1]
KIND = sys.argv[2] if len(sys.argv) > 2 else "floor"
dists = {json.loads(l)["project"]: json.loads(l)
         for l in io.open(os.path.join(DATA, "dists_%s.jsonl" % F), encoding="utf-8")}


def line_of(idx, stored, lineno):
    try:
        src = open(os.path.join(DATA, "src", F, str(idx), stored), "rb").read().decode(
            "utf-8", "replace").splitlines()
        return src[lineno - 1].strip()[:150] if lineno else ""
    except Exception:
        return "?"


def import_line(idx, stored_by_path, path, module):
    st = stored_by_path.get(path)
    if not st:
        return "?"
    src = open(os.path.join(DATA, "src", F, str(idx), st), "rb").read()
    try:
        tree = ast.parse(src)
    except Exception:
        return "?"
    lines = src.decode("utf-8", "replace").splitlines()
    top = module.split(".")[0]
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            if any(x == module or x.split(".")[0] == top for x in names):
                return "L%d: %s" % (n.lineno, lines[n.lineno - 1].strip()[:120])
    return "?"


for l in io.open(os.path.join(DATA, "measure_%s.jsonl" % F), encoding="utf-8"):
    r = json.loads(l)
    if KIND == "floor" and not r.get("contradicts_floor"):
        continue
    if KIND == "e1" and not r.get("e1_removed"):
        continue
    d = dists[r["project"]]
    byp = {v: k for k, v in d["stored"].items()}
    print("=" * 110)
    print("%s  spec %r  floor 3.%s  dist %s  files %d" % (r["project"], r["spec"], r["floor"],
                                                          r["dist"], r["n_files"]))
    print("   deps (%s): %s" % (r.get("deps_source"), (r.get("requires_dist") or [])[:12]))
    print("   top-level names in dist: %s" % (r.get("top_names") or [])[:10])
    if KIND == "floor":
        for x in r["syntax_fail"][:4]:
            print("   SYNTAX %-10s %s  floor-of-file %s  err %s" % (x["kind"], x["file"],
                                                                    x["file_floor"], x["error"]))
            if x["error"] and x["error"][0]:
                print("        > %s" % line_of(d["idx"], x["stored"], x["error"][0]))
        seen = set()
        for x in r["stdlib_fail"]:
            if (x["module"], x["file"]) in seen:
                continue
            seen.add((x["module"], x["file"]))
            print("   STDLIB %s in %s   %s" % (x["module"], x["file"],
                                               import_line(d["idx"], byp, x["file"], x["module"])))
        for x in {(e["why"], e["module"], e["file"]): e for e in r["stdlib_excused"]}.values():
            print("   (excused %s: %s in %s)" % (x["why"], x["module"], x["file"]))
    else:
        for x in r["e1_removed"]:
            print("   REMOVED %s (gone in %s, admits %s) in %s   %s" % (
                x["module"], x["removed"], x["admits"], x["file"],
                import_line(d["idx"], byp, x["file"], x["module"])))
