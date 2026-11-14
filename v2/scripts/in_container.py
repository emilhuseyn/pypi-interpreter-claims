# Runs INSIDE an official python:3.N-slim container (amendment A, C2 and C3). Python 3.4 syntax only.
# Compiles every stored file under /src without executing it, and records which standard-library
# modules this interpreter can find. Writes to /out. Never imports anything from /src.
#
#   docker run --rm --network none -v <src>:/src:ro -v <out>:/out -v <scripts>:/tools:ro \
#       python:3.N-slim python /tools/in_container.py <names-file>
import importlib
import importlib.util
import json
import os
import sys

VER = "%d.%d" % sys.version_info[:2]


def compile_all():
    out = open("/out/compile_%s.jsonl" % VER, "w")
    for frame in sorted(os.listdir("/src")):
        fdir = os.path.join("/src", frame)
        for idx in sorted(os.listdir(fdir), key=int):
            pdir = os.path.join(fdir, idx)
            res, errs = [], {}
            for fn in sorted(os.listdir(pdir)):
                with open(os.path.join(pdir, fn), "rb") as fh:
                    raw = fh.read()
                try:
                    compile(raw, fn, "exec", 0, True)
                    res.append(".")
                except SyntaxError as e:
                    res.append("S")
                    errs[fn] = [e.lineno, str(e.msg)[:80]]
                except Exception as e:
                    res.append("E")
                    errs[fn] = [None, type(e).__name__]
            out.write(json.dumps({"f": frame, "i": int(idx), "r": "".join(res), "e": errs}) + "\n")
    out.close()


def modules(names_file):
    names = [l.strip() for l in open(names_file) if l.strip()]
    have = {}
    for n in names:
        try:
            have[n] = importlib.util.find_spec(n) is not None
        except Exception:
            have[n] = False
    with open("/out/modules_%s.json" % VER, "w") as fh:
        json.dump(have, fh)
    if hasattr(sys, "stdlib_module_names"):
        with open("/out/stdlib_names_%s.json" % VER, "w") as fh:
            json.dump(sorted(sys.stdlib_module_names), fh)


if len(sys.argv) > 1 and sys.argv[1] == "--names-only":
    with open("/out/stdlib_names_%s.json" % VER, "w") as fh:
        json.dump(sorted(getattr(sys, "stdlib_module_names", [])), fh)
else:
    if len(sys.argv) > 1:
        modules(sys.argv[1])
    if os.path.isdir("/src") and os.listdir("/src"):
        compile_all()
print("done", VER)
