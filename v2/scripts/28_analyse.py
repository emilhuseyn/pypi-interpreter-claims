r"""Every number the v2 manuscript may print, from the measurement files, plus the LaTeX macros that
carry them into the text (v2/draft/numbers.tex). No network.

Inputs: v2/data/measure_{U,P}.jsonl, v2/data/validate_{U,P}.jsonl, v2/data/out/compile_3.N.jsonl,
v2/research/adjudication.csv (hand verdicts, V3), v2/results/deps_guard.json (D1),
data/source_floor.jsonl (the 28.08 analysis, for the old-to-new comparison).
Outputs: v2/results/analysis.json, v2/draft/numbers.tex, v2/results/figure_data.json.

    py v2/scripts/28_analyse.py
"""
import collections
import csv
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(V2)
DATA = os.path.join(V2, "data")
RES = os.path.join(V2, "results")
NUM = {}
MACROS = []


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (100 * (c - h), 100 * (c + h))


DIGITS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]


def macro_name(key):
    """u_v1_fp -> \nUVOneFp. LaTeX macro names are letters only, so digits become words."""
    out, up = "", True
    for ch in key:
        if ch.isalpha():
            out += ch.upper() if up else ch
            up = False
        elif ch.isdigit():
            out += DIGITS[int(ch)]
            up = True
        else:
            up = True
    return "n" + out


def put(key, value):
    """Record a count. A macro \\n<Key> prints it with a thousands comma."""
    NUM[key] = value
    s = "{:,}".format(value) if isinstance(value, int) else str(value)
    MACROS.append("\\newcommand{\\%s}{%s}" % (macro_name(key), s.replace(",", "{,}")))
    return value


def rate(key, k, n):
    """Record k of n with a percentage (one decimal) and a Wilson interval."""
    lo, hi = wilson(k, n)
    p = 100.0 * k / n if n else 0.0
    NUM[key] = {"k": k, "n": n, "pct": round(p, 1), "lo": round(lo, 1), "hi": round(hi, 1)}
    put(key + "_k", k)
    put(key + "_n", n)
    MACROS.append("\\newcommand{\\%s}{%.1f}" % (macro_name(key + "_pct"), p))
    MACROS.append("\\newcommand{\\%s}{%.1f, %.1f}" % (macro_name(key + "_ci"), lo, hi))
    return NUM[key]


def load(path):
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]


def _approx_rejects(approx, dist, fail, rec):
    """Would ast.parse(feature_version=floor) under 3.13 have rejected this failing file?
    None when the floor is outside 3.5-3.13 or the file was not parsed by 3.13."""
    f = rec["floor"]
    if f is None or not 5 <= max(f, 4) <= 13:
        return None
    a = approx.get(fail["stored"])
    if a is None:
        return None
    return a[max(f, 5) - 5] != "."


def tex(s):
    s = s.replace("\\", "\x00")
    for a in "_&%#{}":
        s = s.replace(a, "\\" + a)
    return s.replace("~", "\\textasciitilde{}").replace("\x00", "\\textbackslash{}")


def write_tables(out, adj):
    """Tables listing projects are generated, so they cannot drift from the result files."""
    d = os.path.join(V2, "draft")
    rows = []
    for F in ("U", "P"):
        for x in sorted(out[F]["refused"], key=lambda x: x["project"].lower()):
            rows.append("%s & \\code{%s} & \\code{%s} & %s \\\\" % (
                F, tex(x["project"]), tex(x["spec"]), ", ".join("3.%d" % v for v in x["refused"])))
    io.open(os.path.join(d, "tab_refused.tex"), "w", encoding="utf-8").write("\n".join(rows) + "\n")
    rows = []
    for F in ("U", "P"):
        for p in sorted(out[F]["confirmed"], key=str.lower):
            a = adj[(F, p, "floor")]
            spec = out[F]["spec_of"][p]
            rows.append("%s & \\code{%s} & \\code{%s} & %s \\\\" % (
                F, tex(p), tex(spec), tex(a["cause"])))
    io.open(os.path.join(d, "tab_confirmed.tex"), "w", encoding="utf-8").write("\n".join(rows) + "\n")


def adjudication():
    p = os.path.join(V2, "research", "adjudication.csv")
    if not os.path.exists(p):
        return {}
    with io.open(p, encoding="utf-8") as fh:
        return {(r["frame"], r["project"], r["kind"]): r for r in csv.DictReader(fh)}


def main():
    adj = adjudication()
    dg = json.load(io.open(os.path.join(RES, "deps_guard.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(RES, "deps_guard.json")) else {}
    fig = {}
    out = {}
    for F in ("U", "P"):
        f = F.lower()
        rows = load(os.path.join(DATA, "measure_%s.jsonl" % F))
        claims = load(os.path.join(ROOT, "data", "claims.jsonl")) if F == "U" else \
            load(os.path.join(DATA, "claims_P.jsonl"))
        put(f + "_drawn", len(claims))
        readable = [c for c in claims if c.get("status") == "read"]
        put(f + "_readable", len(readable))
        put(f + "_unreadable", len(claims) - len(readable))
        byp = {r["project"]: r for r in rows}
        assert len(byp) == len(readable), (F, len(byp), len(readable))

        # RQ1: which claims are published, over readable
        spec = [r for r in rows if r["spec_kind"] != "none"]
        rate(f + "_spec", len(spec), len(readable))
        rate(f + "_nospec", len(readable) - len(spec), len(readable))
        for kind in ("ok", "no_py3", "unparsable"):
            put(f + "_speckind_" + kind, sum(1 for r in rows if r["spec_kind"] == kind))
        rate(f + "_cls", sum(1 for r in rows if r["classifiers"]), len(readable))
        rate(f + "_whl", sum(1 for r in rows if r["wheel_tags"]), len(readable))
        combo = collections.Counter((r["spec_kind"] != "none", bool(r["classifiers"]),
                                     bool(r["wheel_tags"])) for r in rows)
        for k in [(a, b, c) for a in (True, False) for b in (True, False) for c in (True, False)]:
            put("%s_combo_%s%s%s" % (f, *("y" if x else "n" for x in k)), combo.get(k, 0))
            rate("%s_combopct_%s%s%s" % (f, *("y" if x else "n" for x in k)), combo.get(k, 0),
                 len(readable))
        rate(f + "_both", sum(v for k, v in combo.items() if k[0] and k[1]), len(readable))
        rate(f + "_specnocls", sum(v for k, v in combo.items() if k[0] and not k[1]),
             len(readable))
        rate(f + "_clsnospec", sum(v for k, v in combo.items() if not k[0] and k[1]),
             len(readable))
        rate(f + "_none", combo.get((False, False, False), 0), len(readable))

        # RQ2: classifiers against the specifier; wheel tags
        both = [r for r in rows if r["spec_kind"] == "ok" and r["classifiers"]]
        refused = [r for r in both if r["page_refused"]]
        rate(f + "_refused", len(refused), len(both))
        put(f + "_unreleased", sum(1 for r in rows if r["page_unreleased"]))
        put(f + "_openend", sum(1 for r in both if set(r["admitted"]) - set(r["classifiers"])))
        sw = [r for r in rows if r["spec_kind"] != "none" and r["wheel_tags"]]
        constr = [r for r in sw if "3.*" not in r["wheel_tags"]
                  and any(t.startswith("3.") for t in r["wheel_tags"])]
        rate(f + "_tagconstr", len(constr), len(sw))
        rate(f + "_taguniv", len(sw) - len(constr), len(sw))

        # what could be measured against the code
        st = collections.Counter(r["status"] for r in rows)
        for k, v in st.items():
            put(f + "_status_" + k, v)
        meas = [r for r in rows if r["status"] == "measured"]
        put(f + "_measured", len(meas))
        put(f + "_files", sum(r["n_files"] for r in meas))
        put(f + "_files_nevercompile", sum(r["n_never_compile"] for r in meas))
        decl = [r for r in meas if r["floor"] is not None]
        put(f + "_decl", len(decl))
        put(f + "_silent", sum(1 for r in meas if r["spec_kind"] == "none"))
        put(f + "_nopy3_meas", sum(1 for r in meas if r["spec_kind"] in ("no_py3", "unparsable")))

        # RQ3: the code against the declared floor (flagged -> adjudicated -> D1)
        flagged = [r for r in decl if r["contradicts_floor"]]
        rate(f + "_flagged", len(flagged), len(decl))
        put(f + "_flag_syntax", sum(1 for r in flagged
                                    if any(x["kind"] == "needs-newer" for x in r["syntax_fail"])))
        put(f + "_flag_stdlib", sum(1 for r in flagged if r["stdlib_fail"]))
        conf = [r for r in flagged
                if (adj.get((F, r["project"], "floor")) or {}).get("verdict") == "confirmed"]
        art = [r for r in flagged
               if (adj.get((F, r["project"], "floor")) or {}).get("verdict") == "artefact"]
        put(f + "_adj_pending", len(flagged) - len(conf) - len(art))
        rate(f + "_confirmed", len(conf), len(decl))
        put(f + "_artefact", len(art))
        rate(f + "_precision", len(conf), len(flagged))
        blocked = [r for r in conf if (dg.get(F, {}).get(r["project"]) or {}).get("blocked")]
        put(f + "_blocked", len(blocked))
        put(f + "_conf_floor_le35", sum(1 for r in conf if r["floor"] <= 5))
        put(f + "_conf_syntax", sum(1 for r in conf
                                    if any(x["kind"] == "needs-newer" for x in r["syntax_fail"])))
        put(f + "_conf_stdlib_only", sum(1 for r in conf
                                         if not any(x["kind"] == "needs-newer" for x in r["syntax_fail"])))
        put(f + "_deps_unread", sum(1 for r in conf
                                    if "<non-literal install_requires>" in (r["requires_dist"] or [])))
        rate(f + "_installable", len(conf) - len(blocked), len(decl))
        put(f + "_excused", sum(1 for r in decl if r["stdlib_excused"]))
        put(f + "_excused_backport", sum(1 for r in decl if any(
            e["why"].startswith("backport") for e in r["stdlib_excused"])))
        put(f + "_anydepth_only", sum(1 for r in decl if r["stdlib_fail_any_depth"]
                                      and not r["stdlib_fail"] and not r["contradicts_floor"]))
        put(f + "_tooold", sum(1 for r in decl if any(x["kind"] == "too-old"
                                                      for x in r["syntax_fail"])))
        # guarded against unguarded, same situation
        put(f + "_guarded_same", sum(1 for r in meas if r["guarded_same"]))
        put(f + "_unguarded_same", sum(1 for r in meas if r["unguarded_same_any"]))
        # silent projects: what the code needs
        sil = [r for r in meas if r["spec_kind"] == "none"]
        put(f + "_silent_need37", sum(1 for r in sil if r["detected_floor"] >= 7))
        put(f + "_silent_need310", sum(1 for r in sil if r["detected_floor"] >= 10))
        # E1, exploratory
        e1 = [r for r in meas if r["e1_removed"]]
        rate(f + "_e1", len(e1), len(decl))
        e1c = [r for r in e1 if (adj.get((F, r["project"], "e1")) or {}).get("verdict") == "confirmed"]
        put(f + "_e1_confirmed", len(e1c))
        out[F] = {"spec_of": {r["project"]: r["spec"] for r in flagged},
                  "flagged": [r["project"] for r in flagged],
                  "confirmed": [r["project"] for r in conf],
                  "artefact": [r["project"] for r in art],
                  "blocked": [r["project"] for r in blocked],
                  "refused": [{"project": r["project"], "spec": r["spec"],
                               "refused": r["page_refused"]} for r in refused],
                  "unreleased": [{"project": r["project"], "v": r["page_unreleased"]}
                                 for r in rows if r["page_unreleased"]],
                  "e1": [{"project": r["project"], "e1": r["e1_removed"]} for r in e1]}
        # figure: declared floor against detected floor, measured projects with a floor
        fig[F] = collections.Counter("%d,%d" % (r["floor"], r["detected_floor"]) for r in decl)
        fig[F + "_confirmed"] = sorted("%d,%d" % (r["floor"], r["detected_floor"]) for r in conf)

        # V1: real against approximate parser, file level, v = 3.5 ... 3.13
        val = {r["project"]: r for r in load(os.path.join(DATA, "validate_%s.jsonl" % F))}
        comp = {}
        for v in range(5, 14):
            for l in io.open(os.path.join(DATA, "out", "compile_3.%d.jsonl" % v), encoding="utf-8"):
                x = json.loads(l)
                if x["f"] == F:
                    comp[(v, x["i"])] = x["r"]
        dists = {d["project"]: d for d in load(os.path.join(DATA, "dists_%s.jsonl" % F))}
        t = collections.Counter()
        per_v = collections.Counter()
        files_missed = set()
        for r in meas:
            d = dists[r["project"]]
            ap = val[r["project"]]["approx"]
            for k, fn in enumerate(sorted(d["stored"])):
                a = ap.get(fn)
                if a is None:
                    continue
                for j, v in enumerate(range(5, 14)):
                    real = comp[(v, d["idx"])][k] == "."
                    appr = a[j] == "."
                    t[(real, appr)] += 1
                    if not real and appr:
                        per_v[v] += 1
                        files_missed.add((r["project"], fn))
        put(f + "_v1_cells", sum(t.values()))
        put(f + "_v1_agree", t[(True, True)] + t[(False, False)])
        put(f + "_v1_fp", t[(True, False)])        # approximate rejects, real accepts
        put(f + "_v1_fn", t[(False, True)])        # real rejects, approximate accepts
        put(f + "_v1_fn_files", len(files_missed))
        for v in range(5, 14):
            put(f + "_v1_fn_at_%d" % v, per_v[v])
        put(f + "_flag_syntax_only_testable", sum(
            1 for r in decl if r["contradicts_floor"] and not r["stdlib_fail"] and 5 <= r["floor"] <= 13))
        # V1 consequence: floor contradictions the approximate parser alone would have missed
        put(f + "_v1_missed_flags", sum(
            1 for r in decl if r["contradicts_floor"] and not r["stdlib_fail"]
            and all(_approx_rejects(val[r["project"]]["approx"], dists[r["project"]], x, r)
                    is False for x in r["syntax_fail"] if x["kind"] == "needs-newer")))
        # V2: vermin against our detected floor, project level
        cmpv = collections.Counter()
        vflag = []
        for r in meas:
            vm = val[r["project"]]["vermin"].get("_total")
            if not isinstance(vm, int):
                cmpv["vermin undecided"] += 1
                continue
            ours = r["detected_floor"]
            vm_eff = max(vm, 4)
            cmpv["equal" if vm_eff == ours else ("ours higher" if ours > vm_eff else "vermin higher")] += 1
            if r["floor"] is not None and vm > r["floor"]:
                vflag.append(r["project"])
        for k, v in cmpv.items():
            put(f + "_v2_" + k.replace(" ", ""), v)
        put(f + "_v2_flag", len(vflag))
        put(f + "_v2_flag_overlap", len(set(vflag) & set(out[F]["flagged"])))
        out[F]["vermin_flagged"] = vflag
        out[F]["vermin_only"] = sorted(set(vflag) - set(out[F]["flagged"]))

    # V2 sample: vermin-only projects, 20 drawn at random and inspected one by one
    vs = list(csv.DictReader(io.open(os.path.join(V2, "research", "v2_sample_adjudication.csv"),
                                     encoding="utf-8")))
    put("vo_pool", len(out["U"]["vermin_only"]) + len(out["P"]["vermin_only"]))
    put("vo_sample", len(vs))
    put("vo_real", sum(1 for x in vs if x["verdict"] == "real"))
    put("vo_real_import", sum(1 for x in vs if x["verdict"] == "real" and x["where"] == "import"))
    put("vo_real_function", sum(1 for x in vs if x["verdict"] == "real" and x["where"] == "function"))
    put("vo_guarded", sum(1 for x in vs if x["verdict"] == "guarded"))
    # deviation D-1: Python 2 files that only 3.14 compiles
    put("u_pep758_projects", sum(1 for r in load(os.path.join(DATA, "measure_U.jsonl"))
                                 if r.get("n_pep758_py2")))
    put("p_pep758_projects", sum(1 for r in load(os.path.join(DATA, "measure_P.jsonl"))
                                 if r.get("n_pep758_py2")))

    # the 28.08 analysis against this one, Frame U
    old = [json.loads(l) for l in io.open(os.path.join(ROOT, "data", "source_floor.jsonl"),
                                          encoding="utf-8")]
    oldc = [r["project"] for r in old if r.get("contradicts")]
    put("old_flagged", len(oldc))
    put("old_misfiled", sum(1 for r in old if r.get("status") == "measured"
                            and r.get("requires_python") and r.get("declared_floor") is None))
    put("old_still_flagged", len(set(oldc) & set(out["U"]["flagged"])))
    put("old_still_confirmed", len(set(oldc) & set(out["U"]["confirmed"])))
    put("u_index", json.load(io.open(os.path.join(ROOT, "data", "frame.json"),
                                     encoding="utf-8"))["index_size"])
    out["old_vs_new"] = {p: {"new_flagged": p in out["U"]["flagged"],
                             "new_confirmed": p in out["U"]["confirmed"]} for p in oldc}

    write_tables(out, adj)
    os.makedirs(RES, exist_ok=True)
    json.dump({"numbers": NUM, "lists": out}, io.open(os.path.join(RES, "analysis.json"), "w",
                                                      encoding="utf-8"), ensure_ascii=False,
              indent=1)
    json.dump({k: dict(v) if isinstance(v, collections.Counter) else v for k, v in fig.items()},
              io.open(os.path.join(RES, "figure_data.json"), "w", encoding="utf-8"), indent=1)
    io.open(os.path.join(V2, "draft", "numbers.tex"), "w", encoding="utf-8").write(
        "%% generated by v2/scripts/28_analyse.py; do not edit\n" + "\n".join(MACROS) + "\n")
    for k, v in NUM.items():
        if isinstance(v, dict):
            print("  %-28s %5d / %-5d = %5.1f%%  [%s, %s]" % (k, v["k"], v["n"], v["pct"], v["lo"],
                                                            v["hi"]))
        elif not (k.endswith("_k") or k.endswith("_n")):
            print("  %-28s %s" % (k, v))


main()
