r"""Show that every gate check fails on corrupted input. Each mutation corrupts one input in memory
and names the check that must catch it; the run fails if any mutation passes unnoticed, or if the
uncorrupted inputs do not pass.

    py v2/scripts/34_gate_mutation.py
"""
import copy
import importlib.util
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gate", os.path.join(HERE, "33_gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def num(i, key, delta):
    v = i["analysis"]["numbers"][key]
    if isinstance(v, dict):
        v["k"] += delta
    else:
        i["analysis"]["numbers"][key] = v + delta


def sub_tex(pattern, repl, count=1):
    def f(i):
        new = re.sub(pattern, repl, i["tex"], count=count, flags=re.S)
        assert new != i["tex"], "mutation did not apply: %s" % pattern
        i["tex"] = new
    return f


def first_combo(i):
    return next(k for k in i["analysis"]["numbers"] if k.startswith("u_combo_"))


MUTATIONS = [
    ("one combination count +1 (Frame U)", "check_partitions",
     lambda i: num(i, first_combo(i), 1)),
    ("Table 1 specifier count +1 (Frame P)", "check_partitions", lambda i: num(i, "p_spec", 1)),
    ("a loss status dropped", "check_partitions",
     lambda i: i["analysis"]["numbers"].pop(next(k for k in i["analysis"]["numbers"]
                                                 if k.startswith("u_status_") and "measured" not in k))),
    ("measured population off by one", "check_partitions", lambda i: num(i, "p_decl", 1)),
    ("confirmed +1 without a verdict", "check_chain", lambda i: num(i, "u_confirmed", 1)),
    ("blocked +1", "check_chain", lambda i: num(i, "p_blocked", 1)),
    ("a confirmed project removed from the list", "check_chain",
     lambda i: i["analysis"]["lists"]["U"]["confirmed"].pop()),
    ("a percentage macro edited", "check_percentages",
     lambda i: i.__setitem__("numbers", re.sub(r"(\\newcommand\{\\nUSpecPct\}\{)([\d.]+)",
                                               lambda m: m.group(1) + "%.1f" % (float(m.group(2)) + 0.3),
                                               i["numbers"]))),
    ("a stored pct not matching k/n", "check_percentages",
     lambda i: i["analysis"]["numbers"]["u_spec"].__setitem__("pct", 1.0)),
    ("an undefined macro used", "check_macros_defined",
     sub_tex(r"(\\section\{Introduction\})", r"\1 \\nUNotAThing{} ")),
    ("a hand-typed percentage in the prose", "check_literals",
     sub_tex(r"(\\section\{Introduction\})", r"\1 About 42.7 percent of projects do this.")),
    ("an uncited reference", "check_refs",
     lambda i: i["refs"]["doi"].__setitem__("ghost2026", {"doi": "10.0/x", "second_index": "agree"})),
    ("an author list not confirmed by a second index", "check_refs",
     lambda i: i["refs"]["doi"]["peng2024"].__setitem__("second_index", "DISAGREE")),
    ("bibliography out of citation order", "check_refs",
     lambda i: i.__setitem__("tex", re.sub(r"(\\bibitem\{[^}]+\}.*?)(\\bibitem\{[^}]+\}.*?)(?=\\bibitem)",
                                           r"\2\1", i["tex"], count=1, flags=re.S))),
    ("a citation credited to the wrong first author", "check_attribution",
     sub_tex(r"Scalabrino et al\.", "He et al.")),
    ("the cover letter claims manual inspection", "check_cover",
     lambda i: i.__setitem__("cover", "every case was examined by hand")),
    ("abstract over the limit", "check_front",
     sub_tex(r"(\\begin\{abstract\})", r"\1 " + "word " * 260)),
    ("a citation in the abstract", "check_front",
     sub_tex(r"(\\begin\{abstract\})", r"\1 see\\cite{peng2024}")),
    ("a novelty claim", "check_claims",
     sub_tex(r"(\\section\{Introduction\})", r"\1 This is the first study of its kind.")),
    ("an unearned claim of author review", "check_claims",
     sub_tex(r"(\\section\*\{Acknowledgements\})", r"\1 The author reviewed and edited the text.")),
    ("an en dash in the source", "check_typography",
     sub_tex(r"(\\section\{Introduction\})", "\\1 3.7–3.9")),
    ("a double hyphen in the prose", "check_typography",
     sub_tex(r"(\\section\{Introduction\})", r"\1 pages 1--3")),
    ("a confirmed project missing from the PDF", "check_pdf",
     lambda i: i.__setitem__("pdf", re.sub(re.escape(i["analysis"]["lists"]["U"]["confirmed"][0]),
                                           "", i["pdf"]))),
    ("an unresolved reference in the PDF", "check_pdf",
     lambda i: i.__setitem__("pdf", i["pdf"] + " Section ?? ")),
]


def main():
    base = gate.load_inputs()
    if gate.run(base, quiet=True):
        print("the uncorrupted inputs do not pass the gate; mutation test is meaningless")
        gate.run(base)
        return 1
    caught = 0
    for name, check, mutate in MUTATIONS:
        i = copy.deepcopy(base)
        mutate(i)
        fn = getattr(gate, check)
        bad = fn(i)
        ok = bool(bad)
        caught += ok
        print("  %-7s %-46s by %-20s %s" % ("caught" if ok else "MISSED", name, check,
                                            (bad[0][:60] if bad else "")))
    print("MUTATIONS %d/%d caught" % (caught, len(MUTATIONS)))
    return 0 if caught == len(MUTATIONS) else 1


sys.exit(main())
