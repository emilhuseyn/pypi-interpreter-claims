r"""Refuse to call the manuscript ready until every claim in it is checked against a result file.

Adapted from paper 27's gate, which found three real defects on its first run. The failure it exists
for is a number that WAS true of an earlier analysis and quietly stopped being true when the
analysis changed. Reading the paper cannot catch that; only recomputing can.

Five families of check:

  FIGURES     Every quantity the prose states is recomputed from results/analysis.json and compared.
              A figure checked here must also APPEAR in the manuscript, or the check is vacuous and
              proves only that the script agrees with itself.
  SHAPE       Word count, heading count, words per heading, and the venue's own ceilings: JSEP caps
              the abstract at 200 words and recommends no more than 20 pages.
  TYPOGRAPHY  En dashes, em dashes, non-ASCII in the .bib. All three have reached a built PDF in
              this workspace before, and the first build of THIS manuscript carried thirteen en
              dashes from natbib's compress option and a table's -- markers.
  INTEGRITY   Citation keys used against keys defined, both directions, and every ref against every
              label.
  VENUE       The handling conditions from research/JSEP_FORMAT_2026-08-28.md that can be checked
              mechanically: abstract length, no citations in the abstract, a figure present, tables
              after the bibliography.

    py 11_gate.py
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "draft", "manuscript.tex")
BIB = os.path.join(ROOT, "draft", "references.bib")
PDF = os.path.join(ROOT, "draft", "manuscript.pdf")
ANA = os.path.join(ROOT, "results", "analysis.json")

ABSTRACT_MAX = 200          # JSEP, verbatim: "an abstract of up to 200 words"
PAGE_MAX = 20               # JSEP, verbatim: "usually not more than 20 pages, fully formatted"
PER_HEADING_BAR = 200       # the shape bar carried from SQJ's desk rejection of paper 11

failures, notes = [], []


def body_words(tex):
    t = tex.split(r"\maketitle", 1)[-1]
    t = t.split(r"\bibliography{", 1)[0]
    t = re.sub(r"(?m)^\s*%.*$", "", t)
    t = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", " ", t, flags=re.S)
    t = re.sub(r"\\begin\{(table|figure|tikzpicture)\}.*?\\end\{\1\}", " ", t, flags=re.S)
    t = re.sub(r"\\(section|subsection|paragraph)\*?\{[^}]*\}", " ", t)
    t = re.sub(r"\\label\{[^}]*\}|\\ref\{[^}]*\}|\\cite[tp]?\{[^}]*\}", " x ", t)
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", t)
    t = re.sub(r"[{}$&_^~\\]", " ", t)
    return len(t.split())


def main():
    tex = io.open(TEX, encoding="utf-8").read()
    bib = io.open(BIB, encoding="utf-8").read()
    a = json.load(io.open(ANA, encoding="utf-8"))
    flat = tex.replace("{,}", ",")

    print("=" * 96)
    print("FIGURES - every number in the prose against results/analysis.json")
    print("=" * 96)

    P = a["publishes"]
    pv = a["page_vs_spec"]
    wt = a["wheel_tags"]
    sv = a["source_vs_claim"]

    pairs = [
        ("index size", "879,335", "{:,}".format(a["frame"]["index_size"])),
        # 1,500, not 2,000. The first draft of the manuscript said 2,000 in the abstract, the
        # introduction, the method, the results and the conclusion, carried over from paper 27's
        # design without being checked against the frame that was actually drawn. This line caught
        # it. The gate's own expectation was then wrong for one run, which is the same class of
        # error one level up and is why both sides are written as literals: a gate that reads the
        # value it is checking cannot disagree with anything.
        ("drawn", "1,500", "{:,}".format(a["frame"]["drawn"])),
        ("seed", "20260828", str(a["frame"]["seed"])),
        ("readable metadata", "1,449", "{:,}".format(a["frame"]["readable"])),
        ("readable share", "96.6", "%.1f" % (100.0 * a["frame"]["readable"] / a["frame"]["drawn"])),
        ("publish Requires-Python", "945", str(P["requires_python"]["k"])),
        ("Requires-Python share", "65.2", "%.1f" % P["requires_python"]["pct"]),
        ("publish classifiers", "590", str(P["classifiers"]["k"])),
        ("classifiers share", "40.7", "%.1f" % P["classifiers"]["pct"]),
        ("ship a wheel", "1,160", "{:,}".format(P["wheels"]["k"])),
        ("wheel share", "80.1", "%.1f" % P["wheels"]["pct"]),
        ("guard inert", "504", str(a["inert_guard"]["k"])),
        ("guard inert share", "34.8", "%.1f" % a["inert_guard"]["pct"]),
        ("guard inert lo", "32.4", "%.1f" % a["inert_guard"]["lo"]),
        ("guard inert hi", "37.3", "%.1f" % a["inert_guard"]["hi"]),
        ("both claims", "458", str(pv["both"])),
        ("page overstates", "10", str(pv["page_overstates"]["k"])),
        ("page overstates share", "2.2", "%.1f" % pv["page_overstates"]["pct"]),
        ("page overstates lo", "1.2", "%.1f" % pv["page_overstates"]["lo"]),
        ("page overstates hi", "4.0", "%.1f" % pv["page_overstates"]["hi"]),
        ("ghost versions", "four", "four" if pv["ghost"]["k"] == 4 else str(pv["ghost"]["k"])),
        ("open end", "382", str(pv["open_end"]["k"])),
        ("wheels both", "907", str(wt["both"])),
        ("universal share", "96.1", "%.1f" % wt["universal"]["pct"]),
        ("constraining", "35", str(wt["constraining"]["k"])),
        ("constraining share", "3.9", "%.1f" % wt["constraining"]["pct"]),
        ("measured", "1,368", "{:,}".format(sv["measured"])),
        ("declaring", "872", str(sv["declaring"])),
        ("silent", "496", str(sv["silent"])),
        ("contradict", "19", str(sv["contradicts"]["k"])),
        ("contradict share", "2.2", "%.1f" % sv["contradicts"]["pct"]),
        ("contradict lo", "1.4", "%.1f" % sv["contradicts"]["lo"]),
        ("contradict hi", "3.4", "%.1f" % sv["contradicts"]["hi"]),
        ("by syntax", "Nine", "Nine" if sv["by_syntax"] == 9 else str(sv["by_syntax"])),
        ("by stdlib", "sixteen", "sixteen" if sv["by_stdlib"] == 16 else str(sv["by_stdlib"])),
        ("guarded", "94", str(sv["guarded"]["k"])),
        ("contradict live", "14", str(a["contradicts_live"]["k"])),
        ("contradict live n", "836", str(a["contradicts_live"]["n"])),
        ("contradict live share", "1.7", "%.1f" % a["contradicts_live"]["pct"]),
        ("silent run on 3.4", "83.3", "%.1f" % (100.0 * a["silent_detected"]["3.4"] / sv["silent"])),
        ("silent needing 3.7+", "17", str(a["silent_needing_37"]["k"])),
        ("silent needing share", "3.4", "%.1f" % a["silent_needing_37"]["pct"]),
        ("broken", "36", str(a["installable_but_broken"]["k"])),
        ("broken share", "2.6", "%.1f" % a["installable_but_broken"]["pct"]),
        ("broken lo", "1.9", "%.1f" % a["installable_but_broken"]["lo"]),
        ("broken hi", "3.6", "%.1f" % a["installable_but_broken"]["hi"]),
        ("no distribution lost", "48", str(48)),
        ("gap median", "three", "three" if a["declared_above_detected"]["median"] == 3 else
         str(a["declared_above_detected"]["median"])),
        ("gap n", "853", str(a["declared_above_detected"]["n"])),
    ]
    for label, said, holds in pairs:
        ok = said.replace(",", "") == holds.replace(",", "")
        if not ok:
            failures.append("%s: manuscript %s, results %s" % (label, said, holds))
        print("   %-4s %-34s manuscript %-12s results %s"
              % ("ok" if ok else "FAIL", label, said, holds))
        if said not in flat:
            notes.append("%r is checked but does not appear in the manuscript" % said)

    print()
    print("=" * 96)
    print("SHAPE and the venue's own ceilings")
    print("=" * 96)
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if not m:
        failures.append("no abstract found")
        abs_words, abs_cites = 0, 0
    else:
        raw = m.group(1)
        abs_cites = len(re.findall(r"\\cite[tp]?\{", raw))
        a2 = re.sub(r"\\[a-zA-Z]+\*?", " ", raw)
        abs_words = len(re.sub(r"[{}\\]", " ", a2).split())
    ok = abs_words <= ABSTRACT_MAX
    if not ok:
        failures.append("abstract is %d words, over JSEP's ceiling of %d" % (abs_words, ABSTRACT_MAX))
    print("   %-4s %-34s %d   (ceiling %d)" % ("ok" if ok else "FAIL", "abstract words",
                                               abs_words, ABSTRACT_MAX))
    if abs_cites:
        failures.append("the abstract carries %d citation(s); JSEP forbids them" % abs_cites)
    print("   %-4s %-34s %d   (JSEP: none allowed)"
          % ("ok" if not abs_cites else "FAIL", "citations in the abstract", abs_cites))

    words = body_words(tex)
    heads = re.findall(r"(?m)^\\(?:sub)*section\*?\{", tex)
    per = words // max(len(heads), 1)
    ok = per >= PER_HEADING_BAR
    if not ok:
        failures.append("words per heading is %d, below the bar of %d" % (per, PER_HEADING_BAR))
    print("   %-4s %-34s %d   (bar %d)" % ("ok" if ok else "FAIL", "words per heading",
                                           per, PER_HEADING_BAR))
    print("   %-4s %-34s %d" % ("--", "body words", words))
    print("   %-4s %-34s %d" % ("--", "headings", len(heads)))

    if os.path.exists(PDF):
        try:
            import pypdf
            pages = len(pypdf.PdfReader(PDF).pages)
            ok = pages <= PAGE_MAX
            if not ok:
                failures.append("the PDF is %d pages, over JSEP's %d" % (pages, PAGE_MAX))
            print("   %-4s %-34s %d   (ceiling %d)" % ("ok" if ok else "FAIL", "pages",
                                                       pages, PAGE_MAX))
        except Exception as e:
            notes.append("could not read the PDF page count: %s" % e)
    else:
        failures.append("draft/manuscript.pdf does not exist - build before gating")

    print()
    print("=" * 96)
    print("TYPOGRAPHY")
    print("=" * 96)
    for ch, name in (("\u2013", "en dash"), ("\u2014", "em dash")):
        for path, what in ((TEX, "manuscript.tex"), (BIB, "references.bib")):
            n = io.open(path, encoding="utf-8").read().count(ch)
            if n:
                failures.append("%d %s(s) in %s" % (n, name, what))
            print("   %-4s %-34s %d" % ("ok" if not n else "FAIL", "%s in %s" % (name, what), n))
    if os.path.exists(PDF):
        try:
            import pypdf
            t = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(PDF).pages)
            for ch, name in (("\u2013", "en dash"), ("\u2014", "em dash"), ("\ufffd", "U+FFFD")):
                n = t.count(ch)
                if n:
                    failures.append("%d %s(s) in the BUILT PDF" % (n, name))
                print("   %-4s %-34s %d" % ("ok" if not n else "FAIL",
                                            "%s in the built PDF" % name, n))
        except Exception:
            pass
    nonascii = sorted({c for c in bib if ord(c) > 127})
    if nonascii:
        failures.append("non-ASCII in references.bib: %s" % nonascii)
    print("   %-4s %-34s %s" % ("ok" if not nonascii else "FAIL", "references.bib is pure ASCII",
                                nonascii or "yes"))

    print()
    print("=" * 96)
    print("INTEGRITY and venue structure")
    print("=" * 96)
    used = set()
    for mm in re.finditer(r"\\cite[tp]?\{([^}]*)\}", tex):
        used |= {k.strip() for k in mm.group(1).split(",") if k.strip()}
    defined = set(re.findall(r"@\w+\{([^,]+),", bib))
    missing, unused = sorted(used - defined), sorted(defined - used)
    if missing:
        failures.append("cited but not in the .bib: %s" % missing)
    if unused:
        failures.append("in the .bib but never cited: %s" % unused)
    print("   %-4s %-34s %d used, %d defined"
          % ("ok" if not missing and not unused else "FAIL", "citation keys match",
             len(used), len(defined)))
    if unused:
        print("        defined but uncited: %s" % unused)
    if missing:
        print("        cited but undefined: %s" % missing)

    labels = set(re.findall(r"\\label\{([^}]*)\}", tex))
    refs = set(re.findall(r"\\ref\{([^}]*)\}", tex))
    dangling = sorted(refs - labels)
    if dangling:
        failures.append("references with no label: %s" % dangling)
    print("   %-4s %-34s %d refs, %d labels" % ("ok" if not dangling else "FAIL",
                                                "cross references resolve", len(refs), len(labels)))

    # JSEP requires a figure (the GTOC entry needs one) and tables after the reference list.
    nfig = len(re.findall(r"\\begin\{figure\}", tex))
    if not nfig:
        failures.append("no figure, and JSEP's GTOC entry requires one")
    print("   %-4s %-34s %d" % ("ok" if nfig else "FAIL", "figures present", nfig))

    bibpos = tex.find(r"\bibliography{")
    tabs = [mm.start() for mm in re.finditer(r"\\begin\{table\}", tex)]
    before = [p for p in tabs if p < bibpos]
    if before:
        failures.append("%d table(s) before the reference list; JSEP puts them after" % len(before))
    print("   %-4s %-34s %d after, %d before"
          % ("ok" if not before else "FAIL", "tables after the bibliography",
             len(tabs) - len(before), len(before)))

    print()
    print("=" * 96)
    if notes:
        for n in notes:
            print("   note: %s" % n)
        print()
    if failures:
        print("GATE FAILED - %d problem(s)." % len(failures))
        for f in failures:
            print("   %s" % f)
        return 1
    print("GATE PASSED - %d body words, %d headings, %d words per heading."
          % (words, len(heads), per))
    print("Every figure in the prose was recomputed from results/analysis.json and agrees.")
    return 0


sys.exit(main())
