r"""Run in_container.py in every official python:3.N-slim image (amendment A, C2 and C3).

Bind mounts hang on this machine (Docker Desktop, 14.11.2026), so nothing is mounted: the stored
files go in as a tar stream on stdin and the results come back as a tar stream on stdout. Each
container runs with --network none. Nothing from a package is ever executed: in_container.py only
compiles bytes and calls importlib.util.find_spec on standard-library names.

First pass (--names): collect sys.stdlib_module_names from 3.11, 3.13 and 3.14.
Second pass: compile every stored file and probe every name, in 3.4 ... 3.14.

    py v2/scripts/25_run_containers.py --names
    py v2/scripts/25_run_containers.py
"""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(V2, "data")
OUT = os.path.join(DATA, "out")
TOOL = os.path.join(V2, "scripts", "in_container.py")
VERSIONS = ["3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]
EXTRA = ["importlib.metadata", "importlib.resources", "importlib.abc", "importlib.util",
         "importlib.machinery", "importlib.readers", "importlib.simple", "concurrent.futures",
         "concurrent.interpreters", "compression.zstd", "string.templatelib", "unittest.mock",
         "email.policy", "urllib.request", "xml.etree.ElementTree", "asyncio.taskgroups"]


def run(version, payload, cmd):
    p = subprocess.run(["docker", "run", "-i", "--rm", "--network", "none",
                        "python:%s-slim" % version, "sh", "-c",
                        "mkdir -p /out /w && tar xf - -C /w && ln -s /w/src /src 2>/dev/null; "
                        "cd /w && %s >&2 && tar cf - -C /out ." % cmd],
                       input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise SystemExit("%s failed: %s" % (version, p.stderr.decode()[-400:]))
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as t:
        for m in t.getmembers():
            if m.isfile():
                with open(os.path.join(OUT, os.path.basename(m.name)), "wb") as fh:
                    fh.write(t.extractfile(m).read())
    print("  %s  %s" % (version, p.stderr.decode().strip().splitlines()[-1]))


def tar_of(paths):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for arc, src in paths:
            t.add(src, arcname=arc)
    return buf.getvalue()


os.makedirs(OUT, exist_ok=True)
if "--names" in sys.argv:
    payload = tar_of([("in_container.py", TOOL)])
    for v in ("3.11", "3.13", "3.14"):
        run(v, payload, "python in_container.py --names-only")
    names = set(EXTRA)
    for v in ("3.11", "3.13", "3.14"):
        names |= {n for n in json.load(open(os.path.join(OUT, "stdlib_names_%s.json" % v)))
                  if not n.startswith("_")}
    with open(os.path.join(OUT, "names.txt"), "w") as fh:
        fh.write("\n".join(sorted(names)))
    print("names:", len(names))
else:
    entries = [("in_container.py", TOOL), ("names.txt", os.path.join(OUT, "names.txt"))]
    src = os.path.join(DATA, "src")
    for frame in sorted(os.listdir(src)):
        entries.append(("src/%s" % frame, os.path.join(src, frame)))
    payload = tar_of(entries)
    print("payload %.1f MB" % (len(payload) / 1e6))
    for v in VERSIONS:
        run(v, payload, "python in_container.py names.txt")
