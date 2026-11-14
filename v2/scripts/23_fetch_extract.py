r"""Download each measured project's distribution and extract the files that count (amendment A, C4),
plus the declared dependencies the backport rule needs (C3b). Both frames. Resumable.

Frame U uses the SAME file the 28.08 run measured (data/source_floor.jsonl names it); Frame P picks
the smallest distribution not over 6 MB by the same rule.

Writes v2/data/src/<frame>/<idx>/...  (extracted counted files, read-only input for the containers)
       v2/data/dists_<frame>.jsonl  (one record per project: file, sha256, counted files, deps)

    py v2/scripts/23_fetch_extract.py U|P
"""
import ast
import configparser
import email.parser
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(V2)
DATA = os.path.join(V2, "data")
UA = {"User-Agent": "requires-python-audit/2.0"}
CAP = 6 * 1024 * 1024
EXCL = {"tests", "test", "testing", "docs", "doc", "examples", "example", "benchmarks", "benchmark"}
FRAME = sys.argv[1]


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read(), None
        except urllib.error.HTTPError as e:
            return None, "HTTP %s" % e.code
        except Exception as e:
            if attempt == 2:
                return None, str(e)[:60]
            time.sleep(3)


def members(raw, fn):
    """(path, bytes) for every regular file under 2 MB."""
    bio = io.BytesIO(raw)
    if fn.endswith((".whl", ".zip", ".egg")):
        with zipfile.ZipFile(bio) as z:
            for i in z.infolist():
                if not i.is_dir() and i.file_size < 2_000_000:
                    yield i.filename, z.read(i)
    else:
        with tarfile.open(fileobj=bio, mode="r:*") as t:
            for m in t.getmembers():
                if m.isfile() and m.size < 2_000_000:
                    f = t.extractfile(m)
                    if f:
                        yield m.name, f.read()


def counted(paths, is_wheel):
    """C4: installed, importable .py files. Returns {path: role} for counted files."""
    py = [p for p in paths if p.endswith(".py")]
    out = {}
    if is_wheel:
        for p in py:
            parts = p.split("/")
            if parts[0].endswith(".data") or EXCL & set(x.lower() for x in parts[:-1]):
                continue
            out[p] = "wheel"
        return out
    # sdist: strip the single top directory, then an optional src/
    dirs_with_init = {p.rsplit("/", 1)[0] for p in py if p.endswith("/__init__.py")}
    for p in py:
        parts = p.split("/")
        rel = parts[1:] if len(parts) > 1 else parts
        if rel and rel[0] == "src":
            rel = rel[1:]
        if not rel or EXCL & set(x.lower() for x in rel[:-1]):
            continue
        base = rel[-1]
        if base in ("setup.py", "conftest.py"):
            continue
        d = p.rsplit("/", 1)[0] if "/" in p else ""
        if d in dirs_with_init:
            out[p] = "package"
        elif len(rel) == 1:
            out[p] = "top-module"
    return out


def deps(files, fn):
    """Declared dependencies, first source that exists: METADATA/PKG-INFO Requires-Dist,
    pyproject [project] dependencies, setup.cfg install_requires, setup.py install_requires literal."""
    def top(name):
        return [p for p in files if p.count("/") <= 1 and p.endswith(name)]
    meta = [p for p in files if p.endswith(".dist-info/METADATA")] + top("PKG-INFO")
    for p in meta:
        msg = email.parser.Parser().parsestr(files[p].decode("utf-8", "replace"))
        rd = msg.get_all("Requires-Dist") or []
        if rd:
            return rd, p
    for p in top("pyproject.toml"):
        try:
            d = tomllib.loads(files[p].decode("utf-8", "replace"))
            rd = (d.get("project") or {}).get("dependencies") or []
            if rd:
                return list(rd), p
            poetry = ((d.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            if poetry:
                return ["%s %s" % (k, v if isinstance(v, str) else json.dumps(v))
                        for k, v in poetry.items() if k.lower() != "python"], p + " (poetry)"
        except Exception:
            pass
    for p in top("setup.cfg"):
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read_string(files[p].decode("utf-8", "replace"))
            v = cp.get("options", "install_requires", fallback="")
            rd = [x.strip() for x in v.splitlines() if x.strip()]
            if rd:
                return rd, p
        except Exception:
            pass
    for p in top("setup.py"):
        try:
            tree = ast.parse(files[p].decode("utf-8", "replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "install_requires":
                try:
                    return list(ast.literal_eval(node.value)), p
                except Exception:
                    return ["<non-literal install_requires>"], p
    return [], None


def plan():
    if FRAME == "U":
        claims = {json.loads(l)["project"]: json.loads(l)
                  for l in io.open(os.path.join(ROOT, "data", "claims.jsonl"), encoding="utf-8")}
        old = [json.loads(l) for l in io.open(os.path.join(ROOT, "data", "source_floor.jsonl"),
                                               encoding="utf-8")]
        out = []
        for r in old:
            c = claims[r["project"]]
            pick = None
            if r.get("dist"):
                pick = next(u for u in (c.get("wheels") or []) + (c.get("sdists") or [])
                            if u["filename"] == r["dist"])
            out.append((r["project"], pick, r["status"]))
        return out
    rows = [json.loads(l) for l in io.open(os.path.join(DATA, "claims_P.jsonl"), encoding="utf-8")]
    out = []
    for c in rows:
        if c.get("status") != "read":
            continue
        cand = [u for u in (c.get("wheels") or []) + (c.get("sdists") or [])
                if u.get("size") and u["size"] <= CAP and u.get("url")]
        out.append((c["project"], min(cand, key=lambda u: u["size"]) if cand else None,
                    "measured" if cand else "no_distribution_under_cap"))
    return out


def main():
    outp = os.path.join(DATA, "dists_%s.jsonl" % FRAME)
    done = set()
    if os.path.exists(outp):
        done = {json.loads(l)["project"] for l in io.open(outp, encoding="utf-8") if l.strip()}
    fh = io.open(outp, "a", encoding="utf-8")
    t0 = time.time()
    for idx, (proj, pick, status) in enumerate(plan()):
        if proj in done:
            continue
        rec = {"project": proj, "idx": idx}
        if pick is None:
            rec["status"] = status
        else:
            raw, err = get(pick["url"])
            if err:
                rec.update({"status": "download_failed", "error": err})
            else:
                rec.update({"dist": pick["filename"], "sha256": hashlib.sha256(raw).hexdigest(),
                            "size": len(raw)})
                try:
                    files = dict(members(raw, pick["filename"]))
                except Exception as e:
                    files = {}
                    rec["error"] = "unreadable archive: %s" % str(e)[:60]
                cnt = counted(list(files), pick["filename"].endswith(".whl"))
                d, src = deps(files, pick["filename"])
                tops = sorted({p.split("/")[0] if pick["filename"].endswith(".whl") else
                               ("/".join(p.split("/")[1:]).removeprefix("src/").split("/")[0])
                               for p in cnt})
                rec.update({"n_py": sum(1 for p in files if p.endswith(".py")), "counted": cnt,
                            "requires_dist": d, "deps_source": src,
                            "top_names": [t.removesuffix(".py") for t in tops if t]})
                base = os.path.join(DATA, "src", FRAME, str(idx))
                unsafe = [p for p in cnt if p.startswith("/") or ".." in p.split("/") or ":" in p]
                for p in unsafe:
                    cnt.pop(p)
                written = {}
                for k, p in enumerate(sorted(cnt)):
                    # stored under a flat numbered name: no archive path ever becomes a disk path,
                    # and Windows case-folding or length limits cannot merge two files
                    dst = os.path.join(base, "f%05d.py" % k)
                    os.makedirs(base, exist_ok=True)
                    with open(dst, "wb") as f:
                        f.write(files[p])
                    written["f%05d.py" % k] = p
                rec["stored"] = written
                rec["unsafe_paths_skipped"] = len(unsafe)
                rec["status"] = "measured" if cnt else "no_counted_python"
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        if (idx + 1) % 100 == 0:
            print("   %d  %.0fs" % (idx + 1, time.time() - t0))
    fh.close()
    print("done", outp)


main()
