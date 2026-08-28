r"""Kill switch two: is there a rate to report, or is Requires-Python simply true?

A novelty gap is not a paper. If ninety-nine point nine percent of distributions parse cleanly at
the interpreter floor they declare, the honest outcome is a null result on a question nobody asked,
and it should be found now on sixty projects rather than after a full harvest.

WHAT IS MEASURED, and why each detector is exact rather than heuristic:

  SYNTAX      Every `.py` member is parsed with `ast.parse(src, feature_version=(3, floor))`, where
              `floor` is the minimum interpreter the distribution's own `Requires-Python` admits.
              This is CPython's own parser applied at CPython's own definition of that version's
              grammar. A file that fails cannot be parsed by that interpreter at all, so the failure
              is an ImportError the moment the module is touched. There is no judgement in it.

  STDLIB      An UNCONDITIONAL top-level import of a standard-library module that did not exist at
              the floor - `tomllib` at 3.8, `zoneinfo` at 3.8, `dataclasses` at 3.6. Unconditional
              matters: an import inside `try/except ImportError` or under a `sys.version_info` guard
              is the correct handling of exactly this problem, and counting it as a defect would
              punish the projects doing it right. Guarded imports are counted separately, because
              how many projects handle it correctly is itself worth knowing.

BOTH DETECTORS ARE FLOORS. `feature_version` does not gate everything: an `int | str` annotation is
valid syntax at any version and fails at runtime, and a `dict | dict` expression is an ordinary
BinOp. A package can also call a function that did not exist yet in a module that did. So a
violation found here is certain, and a package found clean is not certified - which is the
conservative direction and the one a reviewer cannot object to.

    py 01_feasibility.py [n]        default 60
"""
import ast
import io
import json
import os
import random
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "feasibility.json")
UA = {"User-Agent": "requires-python-audit/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
SEED = 20260828
SIZE_CAP = 6 * 1024 * 1024

# Standard-library modules and the version that introduced them. Only entries this author is certain
# of; a wrong entry here manufactures a violation, which is worse than missing one.
STDLIB_ADDED = {
    "tomllib": (3, 11),
    "zoneinfo": (3, 9), "graphlib": (3, 9),
    "importlib.metadata": (3, 8),
    "dataclasses": (3, 7), "contextvars": (3, 7), "importlib.resources": (3, 7),
    "secrets": (3, 6),
    "typing": (3, 5), "zipapp": (3, 5),
    "asyncio": (3, 4), "pathlib": (3, 4), "enum": (3, 4), "statistics": (3, 4),
    "selectors": (3, 4), "tracemalloc": (3, 4), "ensurepip": (3, 4),
}


def get(url, timeout=30, binary=False):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                raw = r.read()
            return (raw if binary else raw.decode("utf-8", "replace")), None
        except urllib.error.HTTPError as e:
            return None, "HTTP %s" % e.code
        except Exception as e:
            if attempt == 2:
                return None, str(e)[:60]
            time.sleep(2)
    return None, "unreachable"


def floor_version(spec):
    """The lowest 3.x an interpreter can be and still satisfy the declared specifier.

    Deliberately simple and deliberately conservative: only `>=` and `~=` clauses set a floor, and a
    specifier this cannot read returns None so the project is reported as unreadable rather than
    assigned a floor that was guessed. A guessed floor manufactures violations.
    """
    if not spec:
        return None
    best = None
    for clause in spec.split(","):
        m = re.match(r"\s*(>=|~=|==)\s*3\.(\d+)", clause)
        if m:
            minor = int(m.group(2))
            best = minor if best is None else max(best, minor)
        elif re.match(r"\s*>\s*3\.(\d+)", clause):
            best = int(re.match(r"\s*>\s*3\.(\d+)", clause).group(1)) + 1
    return (3, best) if best is not None else None


def py_members(raw, name):
    """Yield (path, source text) for every .py in a wheel or sdist, without writing to disk."""
    bio = io.BytesIO(raw)
    try:
        if name.endswith(".whl") or name.endswith(".zip"):
            with zipfile.ZipFile(bio) as z:
                for i in z.infolist():
                    if i.filename.endswith(".py") and i.file_size < 2_000_000:
                        yield i.filename, z.read(i).decode("utf-8", "replace")
        else:
            with tarfile.open(fileobj=bio, mode="r:*") as t:
                for m in t.getmembers():
                    if m.isfile() and m.name.endswith(".py") and m.size < 2_000_000:
                        f = t.extractfile(m)
                        if f:
                            yield m.name, f.read().decode("utf-8", "replace")
    except Exception:
        return


def guarded(tree, node):
    """Is this import inside a try/except or a version test? Walk once and record the guarded set."""
    return node in guarded.cache.get(id(tree), set())


guarded.cache = {}


def collect_guarded(tree):
    """Imports under try/except or under an `if` are handled, not defective."""
    out = set()

    def walk(n, shielded):
        for child in ast.iter_child_nodes(n):
            s = shielded or isinstance(n, (ast.Try, ast.If, ast.ExceptHandler))
            if isinstance(child, (ast.Import, ast.ImportFrom)) and s:
                out.add(child)
            walk(child, s)
    walk(tree, False)
    guarded.cache[id(tree)] = out
    return out


def stdlib_violations(tree, floor):
    """Unconditional imports of modules newer than the floor, and the guarded ones separately."""
    collect_guarded(tree)
    bad, handled = [], []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for nm in names:
            added = STDLIB_ADDED.get(nm) or STDLIB_ADDED.get(nm.split(".")[0])
            if nm in STDLIB_ADDED:
                added = STDLIB_ADDED[nm]
            if added and added > floor:
                (handled if guarded(tree, node) else bad).append(
                    "%s needs 3.%d" % (nm, added[1]))
    return sorted(set(bad)), sorted(set(handled))


def main():
    print("drawing the frame from PyPI's simple index")
    index, err = get("https://pypi.org/simple/", timeout=240)
    if err:
        print("STOP: could not read the index: %s" % err)
        return 2
    names = re.findall(r">([^<]+)</a>", index)
    print("index carries %d projects" % len(names))
    random.seed(SEED)
    sample = random.sample(names, min(N, len(names)))

    rows = []
    t0 = time.time()
    for i, name in enumerate(sample, 1):
        rec = {"project": name, "status": None}
        meta, err = get("https://pypi.org/pypi/%s/json" % urllib.parse.quote(name))
        if err:
            rec["status"] = "metadata_failed"
            rows.append(rec)
            continue
        try:
            d = json.loads(meta)
        except Exception:
            rec["status"] = "metadata_unparsable"
            rows.append(rec)
            continue

        spec = (d.get("info") or {}).get("requires_python")
        rec["requires_python"] = spec
        if not spec:
            rec["status"] = "no_requires_python"
            rows.append(rec)
            continue
        floor = floor_version(spec)
        if floor is None:
            rec["status"] = "floor_unreadable"
            rows.append(rec)
            continue
        rec["floor"] = "3.%d" % floor[1]

        urls = [u for u in (d.get("urls") or [])
                if u.get("size") and u["size"] <= SIZE_CAP
                and (u.get("filename", "").endswith(".whl")
                     or u.get("filename", "").endswith(".tar.gz"))]
        if not urls:
            rec["status"] = "no_distribution_under_cap"
            rows.append(rec)
            continue
        pick = min(urls, key=lambda u: u["size"])
        raw, err = get(pick["url"], timeout=60, binary=True)
        if err:
            rec["status"] = "download_failed"
            rows.append(rec)
            continue

        files = syn = 0
        syn_examples, std_bad, std_ok = [], [], []
        for path, src in py_members(raw, pick["filename"]):
            files += 1
            try:
                ast.parse(src, feature_version=floor)
            except SyntaxError:
                # Does it parse AT ALL on this interpreter? If not, the file is broken for every
                # version and says nothing about the declared floor.
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                syn += 1
                if len(syn_examples) < 3:
                    syn_examples.append(path)
                b, h = stdlib_violations(tree, floor)
                std_bad += b
                std_ok += h
                continue
            except Exception:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            b, h = stdlib_violations(tree, floor)
            std_bad += b
            std_ok += h

        rec.update({"status": "measured", "files": files, "dist": pick["filename"],
                    "syntax_violations": syn, "syntax_examples": syn_examples,
                    "stdlib_violations": sorted(set(std_bad)),
                    "stdlib_guarded": sorted(set(std_ok))})
        rows.append(rec)
        if i % 10 == 0:
            print("   %3d/%d  %.0fs" % (i, len(sample), time.time() - t0))

    measured = [r for r in rows if r["status"] == "measured"]
    viol = [r for r in measured if r["syntax_violations"] or r["stdlib_violations"]]
    syn_only = [r for r in measured if r["syntax_violations"]]
    std_only = [r for r in measured if r["stdlib_violations"]]
    guard = [r for r in measured if r["stdlib_guarded"]]

    print()
    print("=" * 92)
    print("WHAT THE PROBE SAW - %d drawn" % len(rows))
    print("=" * 92)
    from collections import Counter
    for k, v in Counter(r["status"] for r in rows).most_common():
        print("   %-30s %4d" % (k, v))

    print()
    print("=" * 92)
    print("IS THERE A RATE TO REPORT - over the %d measured" % len(measured))
    print("=" * 92)
    if measured:
        p = lambda a: (100.0 * a / len(measured))
        print("   declared floor contradicted        %4d   %5.1f%%" % (len(viol), p(len(viol))))
        print("      by syntax the floor cannot parse %4d   %5.1f%%" % (len(syn_only), p(len(syn_only))))
        print("      by an unguarded stdlib import    %4d   %5.1f%%" % (len(std_only), p(len(std_only))))
        print("   handled it correctly (guarded)     %4d   %5.1f%%" % (len(guard), p(len(guard))))
        print()
        for r in viol[:14]:
            print("   %-30s floor %-5s syntax %2d  stdlib %s"
                  % (r["project"][:30], r["floor"], r["syntax_violations"],
                     ", ".join(r["stdlib_violations"])[:44]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(
        {"n": len(rows), "seed": SEED, "rows": rows}, ensure_ascii=False, indent=1))
    print()
    print("written to results/feasibility.json")
    return 0


import urllib.parse  # noqa: E402  (used in main, imported late to keep the header readable)
sys.exit(main())
