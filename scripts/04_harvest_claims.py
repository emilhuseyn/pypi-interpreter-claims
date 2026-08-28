r"""Harvest all three published interpreter claims in one pass, and keep everything.

THREE CLAIMS ABOUT ONE PROPERTY, all obtainable from a single metadata request per project:

  CLASSIFIERS       "Programming Language :: Python :: 3.8", one per version. Rendered in the
                    sidebar of the project page as the answer a human reads. pip ignores them
                    entirely.
  REQUIRES-PYTHON   a PEP 440 specifier. pip ENFORCES it: outside the range the distribution is not
                    a candidate, and pip silently falls back to an older release or fails.
  WHEEL TAGS        encoded in every wheel's filename. `py3-none-any` claims any Python 3;
                    `cp38-cp38-manylinux_x86_64` claims CPython 3.8 on that platform. pip ENFORCES
                    these too, by matching them against the running interpreter's tag set.

Nothing keeps any two of the three in agreement. They live in different fields, are written at
different times by different tooling, and no validator compares them.

WRITES EVERY FIELD IT READS, one JSON object per line, so that a question thought of later does not
need 1,500 more requests. The previous probe discarded the distribution list and the wheel-tag
question then cost a full re-fetch. Incremental, resumable, and it never overwrites.

    py 04_harvest_claims.py [n]        default 1500
"""
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "claims.jsonl")
FRAME = os.path.join(DATA, "frame.json")
UA = {"User-Agent": "requires-python-audit/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
SEED = 20260828

CLASSIFIER = re.compile(r"^Programming Language :: Python :: (\d+)\.(\d+)$")
# cp38, cp310, py3, py38, pp39. The interpreter part of a wheel tag triple.
PYTAG = re.compile(r"^(cp|py|pp|ip|jy)(\d)(\d*)$")


def get(url, timeout=30):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            return None, "HTTP %s" % e.code
        except Exception as e:
            if attempt == 2:
                return None, str(e)[:60]
            time.sleep(2)
    return None, "unreachable"


def wheel_pytags(filename):
    """The interpreter versions a wheel filename claims.

    A wheel is name-version(-build)-python-abi-platform.whl and the python field may hold several
    tags joined by dots. `py3` means any Python 3 and is returned as the marker `3.*`; `cp38` means
    3.8 exactly. Anything unparsable is returned as-is so it can be counted rather than dropped.
    """
    if not filename.endswith(".whl"):
        return None
    parts = filename[:-4].split("-")
    if len(parts) < 3:
        return None
    pyfield = parts[-3]
    out = set()
    for tag in pyfield.split("."):
        m = PYTAG.match(tag)
        if not m:
            out.add("?" + tag)
            continue
        maj, minor = m.group(2), m.group(3)
        if maj != "3":
            out.add("py%s" % maj)
        elif minor == "":
            out.add("3.*")
        else:
            out.add("3.%d" % int(minor))
    return sorted(out)


def main():
    os.makedirs(DATA, exist_ok=True)

    if os.path.exists(FRAME):
        frame = json.load(io.open(FRAME, encoding="utf-8"))
        print("frame reused: %d names, seed %d" % (len(frame["sample"]), frame["seed"]))
    else:
        print("drawing the frame from PyPI's simple index")
        index, err = get("https://pypi.org/simple/", timeout=240)
        if err:
            print("STOP: could not read the index: %s" % err)
            return 2
        names = re.findall(r">([^<]+)</a>", index)
        random.seed(SEED)
        frame = {"seed": SEED, "index_size": len(names),
                 "sample": random.sample(names, min(N, len(names)))}
        io.open(FRAME, "w", encoding="utf-8").write(json.dumps(frame, ensure_ascii=False))
        print("index carries %d projects; sampled %d with seed %d"
              % (len(names), len(frame["sample"]), SEED))

    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8", errors="replace"):
            try:
                done.add(json.loads(line)["project"])
            except Exception:
                pass
        print("resuming: %d already recorded" % len(done))

    fh = io.open(OUT, "a", encoding="utf-8")
    t0 = time.time()
    for i, name in enumerate(frame["sample"], 1):
        if name in done:
            continue
        rec = {"project": name}
        raw, err = get("https://pypi.org/pypi/%s/json" % urllib.parse.quote(name))
        if err:
            rec["status"] = "metadata_failed"
            rec["error"] = err
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            continue
        try:
            d = json.loads(raw)
        except Exception:
            rec["status"] = "metadata_unparsable"
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            continue

        info = d.get("info") or {}
        cls = sorted({int(m.group(2)) for c in (info.get("classifiers") or [])
                      for m in [CLASSIFIER.match(c.strip())] if m and m.group(1) == "3"})

        wheels, sdists, tags = [], [], set()
        for u in d.get("urls") or []:
            fn = u.get("filename", "")
            entry = {"filename": fn, "size": u.get("size"), "url": u.get("url"),
                     "requires_python": u.get("requires_python"),
                     "packagetype": u.get("packagetype")}
            if fn.endswith(".whl"):
                t = wheel_pytags(fn)
                entry["pytags"] = t
                tags.update(t or [])
                wheels.append(entry)
            else:
                sdists.append(entry)

        rec.update({
            "status": "read",
            "requires_python": info.get("requires_python"),
            "classifiers_py3": cls,
            "version": info.get("version"),
            "wheel_tags": sorted(tags),
            "n_wheels": len(wheels), "n_sdists": len(sdists),
            "wheels": wheels[:12], "sdists": sdists[:4],
            # Kept for the source-floor stage so it does not need its own metadata pass.
            "home_page": info.get("home_page"),
            "project_urls": info.get("project_urls"),
        })
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        if i % 100 == 0:
            print("   %4d/%d  %.0fs" % (i, len(frame["sample"]), time.time() - t0))
    fh.close()
    print("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


sys.exit(main())
