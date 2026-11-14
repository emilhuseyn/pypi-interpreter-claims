r"""Validation inputs under plan amendment A, for one frame.

V1  ast.parse(feature_version=(3, v)) under the host's 3.13, v = 3.5 ... 3.13, for every stored
    file the 3.13 parser accepts. Compared later with the real interpreters' verdicts.
V2  vermin (version pinned in the output) with --no-tips, run on each project's stored files
    (parsable format), giving vermin's minimum Python 3 version per file and per project.

The vermin executable is passed as the second argument; it lives in a venv outside the repo.

    py v2/scripts/27_validate.py U|P <path-to-vermin.exe>
"""
import ast
import collections
import io
import json
import os
import re
import subprocess
import sys
import warnings

sys.stdout.reconfigure(encoding="utf-8")
warnings.simplefilter("ignore")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(V2, "data")
FRAME, VERMIN = sys.argv[1], sys.argv[2]
VS = list(range(5, 14))


def approx(src):
    try:
        ast.parse(src)
    except Exception:
        return None
    out = ""
    for v in VS:
        try:
            ast.parse(src, feature_version=(3, v))
            out += "."
        except SyntaxError:
            out += "S"
        except Exception:
            out += "E"
    return out


def vmin(text):
    """Per-file minimum Python 3 minor from vermin's parsable output; None when undecided."""
    per = {}
    for line in text.splitlines():
        # final per-file line: <path>:::<py2>:<py3>:  (empty line/col/feature fields)
        m = re.match(r"^(.*?):(\d*):(\d*):([^:]*):([^:]*):(.*)$", line)
        if not m or m.group(2) or m.group(3) or m.group(6):
            continue
        # "3.6" a minimum, "~3" no constraint found, "!3" incompatible with Python 3
        p3 = m.group(5)
        fn = os.path.basename(m.group(1)) or "_total"
        mm = re.match(r"^3\.(\d+)$", p3)
        per[fn] = int(mm.group(1)) if mm else (0 if p3.startswith("~") else p3)
    return per


def main():
    ver = subprocess.run([VERMIN, "--version"], capture_output=True, text=True).stdout.strip()
    dists = [json.loads(l) for l in io.open(os.path.join(DATA, "dists_%s.jsonl" % FRAME),
                                             encoding="utf-8")]
    fdir = os.path.join(DATA, "src", FRAME)
    # one vermin run over the whole frame (per-project calls cost ~3 s of process start each);
    # per-file minima are mapped back to projects by the numbered directory in each path
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([VERMIN, "--no-tips", "-f", "parsable", "-p=8", fdir], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    per = collections.defaultdict(dict)
    for line in p.stdout.splitlines():
        m = re.match(r"^(.*?):(\d*):(\d*):([^:]*):([^:]*):(.*)$", line)
        if not m or m.group(2) or m.group(3) or m.group(6) or not m.group(1):
            continue
        parts = re.split(r"[\\/]", m.group(1))
        idx, fn = parts[-2], parts[-1]
        p3 = m.group(5)
        mm = re.match(r"^3\.(\d+)$", p3)
        per[idx][fn] = int(mm.group(1)) if mm else (0 if p3.startswith("~") else p3)
    out = io.open(os.path.join(DATA, "validate_%s.jsonl" % FRAME), "w", encoding="utf-8")
    for n, d in enumerate(dists):
        if d["status"] != "measured":
            continue
        pdir = os.path.join(fdir, str(d["idx"]))
        ap = {fn: approx(open(os.path.join(pdir, fn), "rb").read()) for fn in sorted(os.listdir(pdir))}
        vm = per.get(str(d["idx"]), {})
        ints = [v for v in vm.values() if isinstance(v, int)]
        vm["_total"] = max(ints) if ints and len(ints) == len(vm) else (
            max(ints) if ints else None)
        vm["_undecided_files"] = sum(1 for v in vm.values() if not isinstance(v, int))
        out.write(json.dumps({"project": d["project"], "idx": d["idx"], "approx": ap,
                              "vermin": vm, "vermin_version": ver}) + "\n")
    out.close()
    print("done", FRAME, "vermin", ver, "files with a vermin verdict",
          sum(len(v) for v in per.values()), "rc", p.returncode)


main()
