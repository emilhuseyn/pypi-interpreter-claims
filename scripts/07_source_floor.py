r"""What interpreter does the code actually need, against what the project says it needs?

Runs over the full 1,500 already harvested by 04_harvest_claims.py, which recorded every
distribution URL, so this stage costs downloads only and no second metadata pass.

TWO EXACT DETECTORS, both floors rather than estimates:

  SYNTAX   `ast.parse(src, feature_version=(3, n))` is CPython's own parser at CPython's own
           definition of that version's grammar. A file that fails cannot be parsed by 3.n at all,
           so touching the module raises SyntaxError. Measured before being relied on: it gates the
           walrus operator, positional-only parameters, `match`, `except*` and PEP 695 type
           parameters. It does NOT gate `int | str` annotations or a `dict | dict` expression, which
           are ordinary syntax that fails at run time.
  STDLIB   an UNCONDITIONAL top-level import of a module that did not exist at that version.
           Unconditional matters: an import inside `try/except ImportError` or under a
           `sys.version_info` test is the correct handling of this exact problem, and counting it as
           a defect would invert the finding. Guarded imports are counted separately.

Because both detectors are floors, a project found to violate its claim DEFINITELY breaks, and a
project found clean is NOT certified. That asymmetry is the conservative direction and it is stated
in every figure this produces.

THE TWO POPULATIONS ARE MEASURED SEPARATELY AND BOTH MATTER:

  DECLARES A FLOOR       does the source contradict it? A contradiction here is a package pip will
                         happily install on an interpreter it cannot run on, because pip checked the
                         claim and the claim was wrong.
  DECLARES NO FLOOR      pip's guard is inert for 34.8 percent of the index, so pip will install
                         these on anything. What is the LOWEST interpreter they actually work on?
                         Every version below that is an installation pip permits and the package
                         cannot survive.

WRITES INCREMENTALLY, one object per line, and resumes. A run that only writes at the end is a run
that loses everything it did.

    py 07_source_floor.py [limit]
"""
import ast
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "claims.jsonl")
OUT = os.path.join(ROOT, "data", "source_floor.jsonl")
UA = {"User-Agent": "requires-python-audit/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

SIZE_CAP = 6 * 1024 * 1024
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0

# Only entries this author is certain of. A wrong version here manufactures a violation, which is
# worse than missing one, so the table is short on purpose and every entry is a module whose
# introduction version is documented in the standard library's own changelog.
STDLIB_ADDED = {
    "tomllib": 11,
    "zoneinfo": 9, "graphlib": 9,
    "importlib.metadata": 8,
    "dataclasses": 7, "contextvars": 7, "importlib.resources": 7,
    "secrets": 6,
    "typing": 5, "zipapp": 5,
    "asyncio": 4, "pathlib": 4, "enum": 4, "statistics": 4,
    "selectors": 4, "tracemalloc": 4, "ensurepip": 4,
}

# The lowest feature_version ast.parse accepts is (3, 4); below that it raises ValueError rather
# than answering the question, so 4 is the floor of the search rather than 0.
LOW, HIGH = 4, 14


def get(url, timeout=45, binary=False):
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


def declared_floor(spec):
    """Lowest 3.x the specifier admits, or None if it cannot be read. Never guessed."""
    if not spec:
        return None
    best = None
    for clause in spec.split(","):
        m = re.match(r"\s*(>=|~=|==)\s*3\.(\d+)", clause)
        if m:
            best = int(m.group(2)) if best is None else max(best, int(m.group(2)))
            continue
        m = re.match(r"\s*>\s*3\.(\d+)", clause)
        if m:
            v = int(m.group(1)) + 1
            best = v if best is None else max(best, v)
    return best


def py_members(raw, name):
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


def guarded_imports(tree):
    """Import nodes sitting under a try/except or an if - the correct handling, not a defect.

    Returns a set of node objects. The first version of this cached by id(tree) in a module-level
    dict, which is a use-after-free waiting to happen: CPython reuses ids once a tree is collected,
    so a later file could read another file's guarded set. The set is returned and passed instead.
    """
    out = set()

    def walk(node, shielded):
        for child in ast.iter_child_nodes(node):
            s = shielded or isinstance(node, (ast.Try, ast.If, ast.ExceptHandler))
            if s and isinstance(child, (ast.Import, ast.ImportFrom)):
                out.add(child)
            walk(child, s)

    walk(tree, False)
    return out


def stdlib_needs(tree):
    """(unguarded, guarded) as {module: version}. What version each import forces."""
    g = guarded_imports(tree)
    bad, ok = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        else:
            continue
        for nm in names:
            need = STDLIB_ADDED.get(nm)
            if need is None:
                need = STDLIB_ADDED.get(nm.split(".")[0])
            if need is None:
                continue
            (ok if node in g else bad)[nm] = need
    return bad, ok


def analyse(raw, filename):
    """Return (files, detected_floor, syntax_need, stdlib_unguarded, stdlib_guarded, examples).

    detected_floor is the lowest 3.x at which every file parses AND no unguarded stdlib import is
    newer. It is a LOWER BOUND on what the package really needs.
    """
    files = 0
    syntax_need = LOW
    unguarded, guarded = {}, {}
    examples = []
    for path, src in py_members(raw, filename):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue            # broken on THIS interpreter too; says nothing about any floor
        except Exception:
            continue
        files += 1

        # Lowest version this file parses at. Walk up from LOW and stop at the first that works.
        need = LOW
        for v in range(LOW, HIGH + 1):
            try:
                ast.parse(src, feature_version=(3, v))
                need = v
                break
            except SyntaxError:
                need = v + 1
            except ValueError:
                need = v + 1
        if need > syntax_need:
            syntax_need = need
            if len(examples) < 4:
                examples.append({"file": path, "needs": "3.%d" % need})

        b, o = stdlib_needs(tree)
        for k, v in b.items():
            unguarded[k] = max(unguarded.get(k, 0), v)
        for k, v in o.items():
            guarded[k] = max(guarded.get(k, 0), v)

    detected = max([syntax_need] + list(unguarded.values() or [LOW]))
    return files, detected, syntax_need, unguarded, guarded, examples


def main():
    rows = []
    for line in io.open(SRC, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    rows = [r for r in rows if r.get("status") == "read"]
    print("%d projects with readable metadata" % len(rows))

    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8", errors="replace"):
            try:
                done.add(json.loads(line)["project"])
            except Exception:
                pass
        print("resuming: %d already measured" % len(done))

    fh = io.open(OUT, "a", encoding="utf-8")
    t0, n = time.time(), 0
    for i, r in enumerate(rows, 1):
        if r["project"] in done:
            continue
        if LIMIT and n >= LIMIT:
            break
        rec = {"project": r["project"], "requires_python": r.get("requires_python"),
               "classifiers_py3": r.get("classifiers_py3"),
               "declared_floor": declared_floor(r.get("requires_python"))}

        cand = [u for u in (r.get("wheels") or []) + (r.get("sdists") or [])
                if u.get("size") and u["size"] <= SIZE_CAP and u.get("url")]
        if not cand:
            rec["status"] = "no_distribution_under_cap"
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            continue
        pick = min(cand, key=lambda u: u["size"])
        raw, err = get(pick["url"], timeout=70, binary=True)
        if err:
            rec["status"] = "download_failed"
            rec["error"] = err
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            continue

        files, detected, syn, unguarded, guarded, ex = analyse(raw, pick["filename"])
        if not files:
            rec["status"] = "no_python_read"
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            continue

        rec.update({"status": "measured", "dist": pick["filename"], "files": files,
                    "detected_floor": detected, "syntax_floor": syn,
                    "stdlib_unguarded": unguarded, "stdlib_guarded": guarded,
                    "syntax_examples": ex})
        df = rec["declared_floor"]
        rec["contradicts"] = bool(df is not None and detected > df)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        n += 1
        if n % 50 == 0:
            print("   %4d measured this run, %4d/%d overall  %.0fs"
                  % (n, len(done) + n, len(rows), time.time() - t0))
    fh.close()
    print("done: %d measured this run in %.0fs -> %s" % (n, time.time() - t0, OUT))
    return 0


sys.exit(main())
