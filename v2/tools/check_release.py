r"""Release-time check of a Python distribution's declared interpreter support.

Given a wheel or source distribution, reports:
  1. classifiers naming a released Python 3 version that Requires-Python excludes;
  2. classifiers naming a version that is not released yet;
  3. unguarded module-level imports of standard-library modules introduced after the declared floor
     (from a module table read from real CPython releases, results/stdlib_table.json);
  4. with --python PATH, files that the given interpreter (ideally the declared floor release)
     cannot compile. Files are compiled, never executed.

Exit status 1 when anything is reported. Needs `packaging`.

    python check_release.py dist/pkg-1.0-py3-none-any.whl [--python /path/to/python3.9]
"""
import argparse
import ast
import email.parser
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from packaging.specifiers import SpecifierSet
from packaging.version import Version

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "..", "results", "stdlib_table.json")
RELEASES = os.path.join(HERE, "..", "data", "releases.json")
SKIP = {"tests", "test", "testing", "docs", "doc", "examples", "example", "benchmarks", "benchmark"}


def members(path):
    if path.endswith(".whl") or path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if not n.endswith("/"):
                    yield n, z.read(n)
    else:
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if m.isfile():
                    yield m.name, t.extractfile(m).read()


def guarded_imports(tree):
    out = []

    def walk(node, guarded, in_def):
        for ch in ast.iter_child_nodes(node):
            g = guarded or isinstance(node, (ast.Try, ast.If, ast.ExceptHandler))
            d = in_def or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if isinstance(ch, ast.Import):
                out.extend((a.name, g, d, ch.lineno) for a in ch.names)
            elif isinstance(ch, ast.ImportFrom) and ch.module and ch.level == 0:
                out.append((ch.module, g, d, ch.lineno))
                out.extend((ch.module + "." + a.name, g, d, ch.lineno) for a in ch.names)
            walk(ch, g, d)

    walk(tree, False, False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("--python", help="interpreter to compile with, e.g. the declared floor release")
    a = ap.parse_args()
    files = dict(members(a.dist))
    meta = next((files[n] for n in files if n.endswith(".dist-info/METADATA")
                 or (n.count("/") <= 1 and n.endswith("PKG-INFO"))), b"")
    msg = email.parser.Parser().parsestr(meta.decode("utf-8", "replace"))
    spec = msg.get("Requires-Python") or ""
    cls = sorted({int(c.split("::")[-1].strip().split(".")[1]) for c in msg.get_all("Classifier") or []
                  if c.startswith("Programming Language :: Python :: 3.")
                  and c.split("::")[-1].strip().count(".") == 1})
    rel = [Version(r["version"]) for r in json.load(open(RELEASES))]
    released = sorted({v.minor for v in rel})
    ss = SpecifierSet(spec) if spec else SpecifierSet()
    admitted = sorted({v.minor for v in rel if ss.contains(v)})
    floor = admitted[0] if admitted else None
    problems = []
    if not spec:
        problems.append("no Requires-Python: pip applies no version check")
    for c in cls:
        if c in released and c not in admitted:
            problems.append("classifier 3.%d is excluded by Requires-Python %r" % (c, spec))
        if c not in released:
            problems.append("classifier 3.%d names an unreleased version" % c)
    table = json.load(open(TABLE))["table"]
    py = {n: b for n, b in files.items() if n.endswith(".py")
          and not SKIP & {p.lower() for p in n.split("/")[:-1]} and not n.endswith("setup.py")}
    for n, src in sorted(py.items()):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for mod, g, d, line in guarded_imports(tree):
            m = mod if mod in table else mod.split(".")[0]
            t = table.get(m)
            if t and t["intro"] and floor is not None and floor < t["intro"] and not g and not d:
                problems.append("%s:%d imports %s (3.%d) unguarded; declared floor is 3.%d"
                                % (n, line, m, t["intro"], floor))
    if a.python:
        with tempfile.TemporaryDirectory() as tmp:
            for i, (n, src) in enumerate(sorted(py.items())):
                with open(os.path.join(tmp, "f%05d.py" % i), "wb") as fh:
                    fh.write(src)
            code = ("import os,sys\nfor f in sorted(os.listdir(sys.argv[1])):\n"
                    "    try: compile(open(os.path.join(sys.argv[1],f),'rb').read(),f,'exec',0,True)\n"
                    "    except SyntaxError as e: print(f, e.lineno, e.msg)\n")
            out = subprocess.run([a.python, "-c", code, tmp], capture_output=True, text=True).stdout
            names = sorted(py)
            for line in out.splitlines():
                f, ln, m = line.split(" ", 2)
                problems.append("%s:%s does not compile on %s: %s" % (names[int(f[1:6])], ln, a.python, m))
    print("Requires-Python %r, declared floor %s, classifiers %s"
          % (spec, "3.%d" % floor if floor is not None else "none", ["3.%d" % c for c in cls]))
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


sys.exit(main())
