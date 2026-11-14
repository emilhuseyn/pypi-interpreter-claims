r"""Build and package row 28.2 for Software: Practice and Experience. Refuses to package unless the
gate passes on the freshly built PDF and every gate mutation is caught.

Writes v2/final_spe/:
  SPE_28_manuscript.pdf            the single Main Document (Free Format: figures and tables embedded)
  SPE_28_manuscript_source.zip     LaTeX source, numbers.tex, figure
  SPE_28_cover_letter.pdf
  SPE_28_replication_package.zip   scripts, metadata-level data, results, adjudication (no third-party
                                   source code: the scripts re-download each file by URL and SHA-256)
and re-runs the analysis from the unpacked replication package offline, comparing the result.

    py v2/scripts/35_package.py
"""
import filecmp
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(V2)
TECTONIC = os.path.join(os.path.dirname(ROOT), "_shared", "tools", "tectonic.exe")
FINAL = os.path.join(V2, "final_spe")
PY = sys.executable


def run(args, cwd=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return p.returncode, p.stdout + p.stderr


def build(texdir, name):
    rc, out = run([TECTONIC, "-X", "compile", "--keep-logs", name + ".tex"], cwd=texdir)
    if rc:
        raise SystemExit("tectonic failed on %s:\n%s" % (name, out[-1500:]))
    return os.path.join(texdir, name + ".pdf")


def main():
    draft = os.path.join(V2, "draft")
    build(draft, "manuscript")
    rc, out = run([PY, os.path.join(V2, "scripts", "33_gate.py")])
    print(out.strip())
    if rc:
        raise SystemExit("gate failed; nothing packaged")
    rc, out = run([PY, os.path.join(V2, "scripts", "34_gate_mutation.py")])
    print(out.strip().splitlines()[-1])
    if rc:
        raise SystemExit("a mutation went uncaught; nothing packaged")
    os.makedirs(FINAL, exist_ok=True)
    shutil.copy(os.path.join(draft, "manuscript.pdf"), os.path.join(FINAL, "SPE_28_manuscript.pdf"))
    with zipfile.ZipFile(os.path.join(FINAL, "SPE_28_manuscript_source.zip"), "w",
                         zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(draft)):
            if (f.endswith(".tex") and not f.startswith("cover_letter")) or f in ("fig_floors.pdf",
                                                                                "references.bib"):
                z.write(os.path.join(draft, f), f)
    build(draft, "cover_letter")
    shutil.copy(os.path.join(draft, "cover_letter.pdf"), os.path.join(FINAL, "SPE_28_cover_letter.pdf"))

    # replication package
    rp = os.path.join(FINAL, "SPE_28_replication_package.zip")
    members = []
    for d, keep in (("v2/scripts", None), ("v2/tools", None), ("v2/results", None),
                    ("v2/research", (".md", ".csv", ".json", ".txt")), ("scripts", (".py",))):
        for fn in sorted(os.listdir(os.path.join(ROOT, d))):
            p = os.path.join(ROOT, d, fn)
            # venue choice and the JSEP cover letter are submission planning, not replication material
            internal = "venue" in fn.lower() or fn == "13_cover_letter.py"
            if os.path.isfile(p) and (keep is None or fn.endswith(keep)) and not fn.endswith(".pyc") \
                    and not internal:
                members.append((p, d + "/" + fn))
    for fn in ("claims.jsonl", "frame.json", "source_floor.jsonl"):
        members.append((os.path.join(ROOT, "data", fn), "data/" + fn))
    for fn in sorted(os.listdir(os.path.join(V2, "data"))):
        if fn.endswith((".jsonl", ".json")) and not fn.startswith("validate_"):
            members.append((os.path.join(V2, "data", fn), "v2/data/" + fn))
        elif fn.startswith("validate_"):
            members.append((os.path.join(V2, "data", fn), "v2/data/" + fn))
    for fn in sorted(os.listdir(os.path.join(V2, "data", "out"))):
        members.append((os.path.join(V2, "data", "out", fn), "v2/data/out/" + fn))
    members.append((os.path.join(V2, "README_replication.md"), "README.md"))
    with zipfile.ZipFile(rp, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in members:
            z.write(src, arc)
    # offline re-run from the package: the analysis must reproduce analysis.json exactly
    tmp = tempfile.mkdtemp(prefix="rp28_")
    with zipfile.ZipFile(rp) as z:
        z.extractall(tmp)
    os.makedirs(os.path.join(tmp, "v2", "draft"), exist_ok=True)
    rc, out = run([PY, "-I", os.path.join(tmp, "v2", "scripts", "28_analyse.py")], cwd=tmp)
    same = rc == 0 and json.load(io.open(os.path.join(tmp, "v2", "results", "analysis.json"),
                                         encoding="utf-8")) == json.load(
        io.open(os.path.join(V2, "results", "analysis.json"), encoding="utf-8"))
    shutil.rmtree(tmp, ignore_errors=True)
    if not same:
        raise SystemExit("the replication package does not reproduce analysis.json offline:\n" + out[-800:])
    size = os.path.getsize(rp) / 1e6
    print("packaged in %s; replication package %.1f MB reproduces analysis.json offline" % (FINAL, size))
    for fn in sorted(os.listdir(FINAL)):
        print("   %-40s %8d bytes" % (fn, os.path.getsize(os.path.join(FINAL, fn))))


main()
