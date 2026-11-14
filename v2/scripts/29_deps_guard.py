r"""D1 (plan amendment A): would pip refuse a flagged project at its declared floor anyway, because a
direct dependency has nothing installable there?

For each flagged project (both frames) at interpreter 3.f, f its declared floor: every declared
dependency whose marker holds at 3.f (no extras) is looked up on PyPI. The dependency blocks the
installation if no release that satisfies the requirement has a non-yanked file, uploaded on or
before the frame's snapshot date, that admits 3.f: an sdist, or a wheel whose Python tag fits 3.f
(py3, py3N with N <= f, cp3f, or cp3N-abi3 with N <= f), with a Requires-Python admitting a final
3.f release. Platform tags are not considered. Writes v2/results/deps_guard.json.

    py v2/scripts/29_deps_guard.py
"""
import functools
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from packaging.requirements import Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(V2, "data")
SNAP = {"U": "2026-08-28", "P": "2026-11-14"}
UA = {"User-Agent": "requires-python-audit/2.0"}
REL = json.load(io.open(os.path.join(DATA, "releases.json"), encoding="utf-8"))
CACHE = {}


def pypi(name):
    if name in CACHE:
        return CACHE[name]
    url = "https://pypi.org/pypi/%s/json" % urllib.parse.quote(name)
    d = None
    for a in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            time.sleep(3)
        except Exception:
            time.sleep(3)
    CACHE[name] = d
    time.sleep(0.2)
    return d


def wheel_fits(fn, f):
    parts = fn[:-4].split("-")
    if len(parts) < 5:
        return False
    py, abi = parts[-3], parts[-2]
    for t in py.split("."):
        m = re.match(r"^(py|cp)(\d)(\d*)$", t)
        if not m or m.group(2) != "3":
            continue
        n = int(m.group(3)) if m.group(3) else None
        if m.group(1) == "py" and (n is None or n <= f):
            return True
        if m.group(1) == "cp" and n is not None and (n == f or (abi == "abi3" and n <= f)):
            return True
    return False


@functools.lru_cache(maxsize=None)
def admits(rp, f, snap):
    if not rp:
        return True
    try:
        ss = SpecifierSet(rp)
    except InvalidSpecifier:
        return True
    return any(ss.contains(Version(r["version"])) for r in REL
               if r["version"].startswith("3.%d." % f) and r["date"] <= snap)


def blocks(req, f, snap):
    d = pypi(canonicalize_name(req.name))
    if d is None:
        return None                                   # unknown: never counted as blocking
    for ver, files in (d.get("releases") or {}).items():
        try:
            v = Version(ver)
        except InvalidVersion:
            continue
        if v.is_prerelease and not req.specifier.prereleases:
            continue
        if req.specifier and not req.specifier.contains(v, prereleases=True):
            continue
        for fl in files:
            if fl.get("yanked") or (fl.get("upload_time_iso_8601") or "")[:10] > snap:
                continue
            fn = fl.get("filename", "")
            usable = (not fn.endswith(".whl")) or wheel_fits(fn, f)
            if usable and admits(fl.get("requires_python"), f, snap):
                return False
    return True


def main():
    out = {}
    for F in ("U", "P"):
        out[F] = {}
        for l in io.open(os.path.join(DATA, "measure_%s.jsonl" % F), encoding="utf-8"):
            r = json.loads(l)
            if not r.get("contradicts_floor"):
                continue
            f = r["floor"]
            env = {"python_version": "3.%d" % f, "python_full_version": "3.%d.0" % f, "extra": ""}
            res = {"floor": "3.%d" % f, "deps": [], "blocked": False}
            for s in r.get("requires_dist") or []:
                try:
                    q = Requirement(s)
                    if q.marker is not None and not q.marker.evaluate(env):
                        continue
                except Exception:
                    continue
                b = blocks(q, f, SNAP[F])
                res["deps"].append({"req": s, "blocks": b})
                if b:
                    res["blocked"] = True
            out[F][r["project"]] = res
            print("%s %-34s 3.%-3d deps %2d  %s" % (F, r["project"], f, len(res["deps"]),
                                                   "BLOCKED by " + ", ".join(
                                                       x["req"] for x in res["deps"] if x["blocks"])
                                                   if res["blocked"] else "installable"), flush=True)
    json.dump(out, io.open(os.path.join(V2, "results", "deps_guard.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


main()
