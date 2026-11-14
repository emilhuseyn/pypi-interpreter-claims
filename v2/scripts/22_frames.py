r"""CPython release list, and Frame P (the 1,000 most-downloaded projects) harvested with the same
record format as Frame U's data/claims.jsonl (scripts/04_harvest_claims.py), plan amendment A.

Writes v2/data/releases.json, v2/data/top_ranking.json, v2/data/claims_P.jsonl. Resumable.

    py v2/scripts/22_frames.py
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(V2, "data")
UA = {"User-Agent": "requires-python-audit/2.0"}
CLASSIFIER = re.compile(r"^Programming Language :: Python :: (\d+)\.(\d+)$")
PYTAG = re.compile(r"^(cp|py|pp|ip|jy)(\d)(\d*)$")
N_TOP = 1000


def get(url, timeout=40):
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
    parts = filename[:-4].split("-")
    if len(parts) < 3:
        return None
    out = set()
    for tag in parts[-3].split("."):
        m = PYTAG.match(tag)
        if not m:
            out.add("?" + tag)
        elif m.group(2) != "3":
            out.add("py%s" % m.group(2))
        elif m.group(3) == "":
            out.add("3.*")
        else:
            out.add("3.%d" % int(m.group(3)))
    return sorted(out)


def releases():
    out = os.path.join(DATA, "releases.json")
    raw, err = get("https://www.python.org/api/v2/downloads/release/?is_published=true", 90)
    if err:
        raise SystemExit("python.org release API: %s" % err)
    rel = []
    for r in json.loads(raw):
        m = re.match(r"^Python (3)\.(\d+)\.(\d+)$", r.get("name", ""))
        if m and not r.get("pre_release"):
            rel.append({"version": "3.%s.%s" % (m.group(2), m.group(3)),
                        "date": (r.get("release_date") or "")[:10]})
    rel.sort(key=lambda x: tuple(int(p) for p in x["version"].split(".")))
    json.dump(rel, io.open(out, "w", encoding="utf-8"), indent=0)
    minors = sorted({int(x["version"].split(".")[1]) for x in rel})
    print("CPython 3.x final releases: %d, minors %s..%s; latest %s on %s"
          % (len(rel), minors[0], minors[-1], rel[-1]["version"], rel[-1]["date"]))
    for mi in minors:
        first = min((x for x in rel if x["version"].startswith("3.%d." % mi)),
                    key=lambda x: int(x["version"].split(".")[2]))
        print("   3.%-3d first final %s on %s" % (mi, first["version"], first["date"]))


def frame_p():
    rk = os.path.join(DATA, "top_ranking.json")
    if not os.path.exists(rk):
        raw, err = get("https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json", 90)
        if err:
            raise SystemExit("ranking unavailable: %s (Frame P is dropped per amendment A)" % err)
        io.open(rk, "w", encoding="utf-8").write(raw)
    d = json.load(io.open(rk, encoding="utf-8"))
    rows = d["rows"][:N_TOP]
    print("ranking last_update %s, %d rows, taking top %d" % (d.get("last_update"), len(d["rows"]),
                                                               len(rows)))
    out = os.path.join(DATA, "claims_P.jsonl")
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["project"] for l in io.open(out, encoding="utf-8") if l.strip()}
    fh = io.open(out, "a", encoding="utf-8")
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        name = row["project"]
        if name in done:
            continue
        rec = {"project": name, "rank": i, "downloads": row.get("download_count")}
        raw, err = get("https://pypi.org/pypi/%s/json" % urllib.parse.quote(name))
        if err:
            rec.update({"status": "metadata_failed", "error": err})
        else:
            info = (json.loads(raw).get("info") or {})
            d2 = json.loads(raw)
            cls = sorted({int(m.group(2)) for c in (info.get("classifiers") or [])
                          for m in [CLASSIFIER.match(c.strip())] if m and m.group(1) == "3"})
            wheels, sdists, tags = [], [], set()
            for u in d2.get("urls") or []:
                fn = u.get("filename", "")
                e = {"filename": fn, "size": u.get("size"), "url": u.get("url"),
                     "requires_python": u.get("requires_python"),
                     "packagetype": u.get("packagetype"),
                     "sha256": (u.get("digests") or {}).get("sha256")}
                if fn.endswith(".whl"):
                    e["pytags"] = wheel_pytags(fn)
                    tags.update(e["pytags"] or [])
                    wheels.append(e)
                else:
                    sdists.append(e)
            # All wheels are kept here (Frame U kept the first 12); the smallest-file rule needs
            # them all, and the difference is stated in the paper.
            rec.update({"status": "read", "requires_python": info.get("requires_python"),
                        "classifiers_py3": cls, "version": info.get("version"),
                        "wheel_tags": sorted(tags), "n_wheels": len(wheels),
                        "n_sdists": len(sdists), "wheels": wheels, "sdists": sdists})
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        time.sleep(0.15)
        if i % 200 == 0:
            print("   %d/%d %.0fs" % (i, len(rows), time.time() - t0))
    fh.close()
    print("Frame P harvested -> %s" % out)


os.makedirs(DATA, exist_ok=True)
releases()
frame_p()
