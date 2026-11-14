r"""Consistency gate for the v2 manuscript (row 28.2, SPE). Every check is a function of an inputs
dict, so 34_gate_mutation.py can corrupt one input at a time and show that each check fails.

Inputs: v2/results/analysis.json, v2/draft/numbers.tex, v2/draft/manuscript.tex (with the files it
\input{}s), v2/research/references.json, the built PDF's text.

    py v2/scripts/33_gate.py            exit 0 when every check passes
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABSTRACT_MAX, KEYWORDS_MAX = 250, 6

# Numbers allowed to appear as literals in the prose, each with where it comes from. Anything else
# that looks like a count or a percentage must come through a macro from numbers.tex.
ALLOWED = {
    "1,000": "Frame P size, a design constant",
    "3,000": "Li et al. sample size, cited",
    "55,138": "Peng et al., cited", "4,155": "Peng et al., cited",
    "20260828": "Frame U seed", "6": "6 MB cap / keyword count", "25.0": "packaging version",
    "1.9.2": "vermin version", "95": "95% intervals", "250": "abstract limit",
    "0": "Python 3.0 contexts", "2022": "Peng et al. data year", "1.2": "metadata version 1.2",
}


def load_inputs():
    tex = io.open(os.path.join(V2, "draft", "manuscript.tex"), encoding="utf-8").read()
    for m in re.finditer(r"\\input\{([^}]+)\}", tex):
        p = os.path.join(V2, "draft", m.group(1) + ("" if m.group(1).endswith(".tex") else ".tex"))
        if os.path.exists(p) and "numbers" not in m.group(1):
            tex = tex.replace(m.group(0), io.open(p, encoding="utf-8").read())
    pdf = os.path.join(V2, "draft", "manuscript.pdf")
    pdftext = ""
    if os.path.exists(pdf):
        import pymupdf
        pdftext = "\n".join(p.get_text() for p in pymupdf.open(pdf))
    return {"analysis": json.load(io.open(os.path.join(V2, "results", "analysis.json"), encoding="utf-8")),
            "numbers": io.open(os.path.join(V2, "draft", "numbers.tex"), encoding="utf-8").read(),
            "tex": tex,
            "refs": json.load(io.open(os.path.join(V2, "research", "references.json"), encoding="utf-8")),
            "pdf": pdftext}


def N(i):
    return i["analysis"]["numbers"]


def k(i, key):
    v = N(i)[key]
    return v["k"] if isinstance(v, dict) else v


def check_partitions(i):
    """Tables sum to the populations they name, in both frames."""
    bad = []
    for f in ("u", "p"):
        n = N(i)
        combos = sum(v for kk, v in n.items() if kk.startswith(f + "_combo_"))
        if combos != n[f + "_readable"]:
            bad.append("%s: combinations sum to %d, readable is %d" % (f, combos, n[f + "_readable"]))
        spec_yes = sum(v for kk, v in n.items() if kk.startswith(f + "_combo_y"))
        if spec_yes != k(i, f + "_spec"):
            bad.append("%s: specifier column %d != Table 1 %d" % (f, spec_yes, k(i, f + "_spec")))
        cls = sum(v for kk, v in n.items() if re.match(f + r"_combo_.y.$", kk))
        if cls != k(i, f + "_cls"):
            bad.append("%s: classifier column %d != Table 1 %d" % (f, cls, k(i, f + "_cls")))
        whl = sum(v for kk, v in n.items() if re.match(f + r"_combo_..y$", kk))
        if whl != k(i, f + "_whl"):
            bad.append("%s: wheel column %d != Table 1 %d" % (f, whl, k(i, f + "_whl")))
        if k(i, f + "_spec") + k(i, f + "_nospec") != n[f + "_readable"]:
            bad.append("%s: specifier + no specifier != readable" % f)
        if n[f + "_readable"] + n[f + "_unreadable"] != n[f + "_drawn"]:
            bad.append("%s: readable + unreadable != drawn" % f)
        st = sum(v for kk, v in n.items() if kk.startswith(f + "_status_"))
        if st != n[f + "_readable"]:
            bad.append("%s: statuses sum to %d, readable is %d" % (f, st, n[f + "_readable"]))
        if n[f + "_status_measured"] != n[f + "_measured"]:
            bad.append("%s: measured status != measured" % f)
        if n[f + "_decl"] + n[f + "_silent"] + n[f + "_nopy3_meas"] != n[f + "_measured"]:
            bad.append("%s: floor + silent + no-Python-3 != measured" % f)
        if sum(n.get(f + "_speckind_" + x, 0) for x in ("ok", "no_py3", "unparsable")) != \
                k(i, f + "_spec"):
            bad.append("%s: specifier kinds do not sum to specifiers" % f)
    return bad


def check_chain(i):
    """flagged = confirmed + artefact (none pending); confirmed = installable + blocked."""
    bad = []
    for f in ("u", "p"):
        n = N(i)
        fl, co, ar = k(i, f + "_flagged"), k(i, f + "_confirmed"), n[f + "_artefact"]
        if n[f + "_adj_pending"]:
            bad.append("%s: %d flagged cases not adjudicated" % (f, n[f + "_adj_pending"]))
        if fl != co + ar + n[f + "_adj_pending"]:
            bad.append("%s: flagged %d != confirmed %d + artefact %d" % (f, fl, co, ar))
        if co != k(i, f + "_installable") + n[f + "_blocked"]:
            bad.append("%s: confirmed != installable + blocked" % f)
        if not (n[f + "_flag_syntax"] <= fl and n[f + "_flag_stdlib"] <= fl
                and n[f + "_flag_syntax"] + n[f + "_flag_stdlib"] >= fl):
            bad.append("%s: syntax/stdlib split inconsistent with flagged" % f)
        if k(i, f + "_precision") != co or N(i)[f + "_precision"]["n"] != fl:
            bad.append("%s: precision is not confirmed over flagged" % f)
        lists = i["analysis"]["lists"][f.upper()]
        if len(lists["confirmed"]) != co or len(lists["flagged"]) != fl:
            bad.append("%s: project lists disagree with counts" % f)
        if N(i)[f + "_refused"]["k"] != len(lists["refused"]):
            bad.append("%s: refused list disagrees with count" % f)
    return bad


def macros(i):
    return dict(re.findall(r"\\newcommand\{\\(\w+)\}\{((?:[^{}]|\{,\})*)\}", i["numbers"]))


def check_percentages(i):
    """Every printed percentage and interval is recomputed from its own k and n."""
    bad = []
    from math import isclose
    mac = macros(i)
    for key, v in N(i).items():
        if not isinstance(v, dict):
            continue
        p = 100.0 * v["k"] / v["n"] if v["n"] else 0.0
        if round(p, 1) != v["pct"]:
            bad.append("%s: pct %s != %.1f" % (key, v["pct"], p))
    for name, val in mac.items():
        if name.endswith("Pct"):
            base = name[:-3]
            kk, nn = mac.get(base + "K"), mac.get(base + "N")
            if kk is None or nn is None:
                bad.append("%s has no K/N macros" % name)
                continue
            kk, nn = int(kk.replace("{,}", "")), int(nn.replace("{,}", ""))
            if nn and not isclose(float(val), round(100.0 * kk / nn, 1)):
                bad.append("%s = %s, but %d/%d = %.1f" % (name, val, kk, nn, 100.0 * kk / nn))
    return bad


def body(i):
    t = i["tex"]
    t = t[t.index("\\begin{document}"):]
    t = re.sub(r"(?m)%.*$", "", t)
    return t


def check_macros_defined(i):
    used = set(re.findall(r"\\(n[A-Z]\w*)\{\}", body(i)))
    have = set(macros(i))
    return ["macro \\%s used but not produced by the analysis" % m for m in sorted(used - have)]


def check_literals(i):
    """No count or percentage typed by hand: every number in the prose is a macro or allowed."""
    t = body(i)
    t = re.sub(r"\\(code|url|cite|ref|label|citep|citet|includegraphics|input|bibitem|href)\{[^}]*\}", " ", t)
    t = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", " ", t, flags=re.S)
    t = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", " ", t, flags=re.S)
    t = re.sub(r"\b(?:19|20)\d\d\b", " ", t)                       # years
    t = re.sub(r"\b\d{1,2}(?:\s|~)+(?:January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\b", " ", t)    # dates
    t = re.sub(r"\b\d+-day\b", " ", t)
    t = re.sub(r"\b\d+\.\d+\.\d+\b", " ", t)                        # tool versions (Vermin 1.9.2)
    t = re.sub(r"SHA-256|Opus \d+(?:\.\d+)?", " ", t)               # a hash name, model names
    t = re.sub(r"\b3\.\d{1,2}(?:\.\d+)?\b", " ", t)                  # Python versions
    t = re.sub(r"\b(?:RQ|PEP |Section~?|Table~?|Figure~?|Python )\s*\d+", " ", t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)              # commands
    t = re.sub(r"\d+(?:\.\d+)?\s*(?:mm|cm|pt|in|MB)\b", " ", t)
    bad = []
    for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])", t):
        num = m.group(1).rstrip(",.")
        if num in ALLOWED or (num.isdigit() and int(num) <= 12):
            continue
        ctx = t[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")
        bad.append("literal %s typed in prose: ...%s..." % (num, ctx))
    return bad


def check_refs(i):
    bad = []
    keys = set()
    for m in re.finditer(r"\\cite[pt]?\{([^}]*)\}", body(i)):
        keys |= {x.strip() for x in m.group(1).split(",")}
    known = set(i["refs"]["doi"]) | set(i["refs"]["web"])
    for x in sorted(keys - known):
        bad.append("cited key %s not in references.json" % x)
    for x in sorted(known - keys):
        bad.append("reference %s is never cited" % x)
    for x, r in i["refs"]["doi"].items():
        if r.get("second_index") != "agree":
            bad.append("reference %s: author list not confirmed by a second index" % x)
    items = re.findall(r"\\bibitem\{([^}]+)\}", i["tex"])
    if sorted(items) != sorted(keys):
        bad.append("bibliography items %d != cited keys %d" % (len(items), len(keys)))
    order = []
    for m in re.finditer(r"\\cite[pt]?\{([^}]*)\}", body(i)):
        for x in m.group(1).split(","):
            if x.strip() not in order:
                order.append(x.strip())
    if items != order:
        bad.append("bibliography is not numbered in order of first citation")
    return bad


def check_attribution(i):
    """Every 'Name et al.' or 'A and B' in the prose matches the authors of the work it cites."""
    import unicodedata

    def norm(s):
        s = unicodedata.normalize("NFKD", s)
        return re.sub(r"[^a-z]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())

    bad = []
    t = re.sub(r"\s+", " ", body(i))
    pats = [(r"([A-Z][\w\-]+) et al\.(?:\\ )?[^.]*?\\cite\{([^}]+)\}", 1),
            (r"([A-Z][a-z][\w\-]+) and ([A-Z][a-z][\w\-]+) (?:built|found|showed|measured|reported)[^.]*?\\cite\{([^}]+)\}", 2)]
    for pat, n in pats:
        for m in re.finditer(pat, t):
            names = [m.group(k) for k in range(1, n + 1)]
            for key in m.group(n + 1).split(","):
                r = i["refs"]["doi"].get(key.strip())
                if not r:
                    continue
                fam = [norm(f) for _, f in r["crossref_authors"]]
                if n == 1 and fam[:1] != [norm(names[0])]:
                    bad.append("'%s et al.' cites %s, whose first author is %s"
                               % (names[0], key, r["crossref_authors"][0][1]))
                if n == 2 and not all(norm(x) in fam for x in names):
                    bad.append("'%s and %s' cites %s by %s" % (names[0], names[1], key, fam))
    return bad


def check_cover(i):
    """The cover letter leaves the machine too: same claim, dash and macro rules as the manuscript."""
    p = os.path.join(V2, "draft", "cover_letter.tex")
    if not os.path.exists(p):
        return ["no cover letter"]
    t = i.get("cover") or io.open(p, encoding="utf-8").read()
    bad = []
    low = re.sub(r"\s+", " ", t.lower())
    for pat in (r"\bby hand\b", r"\bmanual(?:ly)?\b", r"author[s]? (?:has |have )?(?:read|reviewed|edited|revised)\b",
                r"\bthe first\b", r"\bnovel\b"):
        if re.search(pat, low):
            bad.append("cover letter: %r" % pat)
    if "\u2013" in t or "\u2014" in t or re.search(r"(?<![-!<>=~])--(?!-)", t):
        bad.append("cover letter has a dash")
    used = set(re.findall(r"\\(n[A-Z]\w*)\{\}", t))
    bad += ["cover letter uses undefined \\%s" % m for m in sorted(used - set(macros(i)))]
    return bad


def check_front(i):
    bad = []
    t = i["tex"]
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", t, re.S)
    if not m:
        return ["no abstract"]
    a = re.sub(r"\\n[A-Z]\w*\{\}", "N", m.group(1))
    a = re.sub(r"\\[a-zA-Z]+", " ", a)
    words = [w for w in re.split(r"\s+", re.sub(r"[{}]", "", a)) if re.search(r"\w", w)]
    if len(words) > ABSTRACT_MAX:
        bad.append("abstract is %d words (limit %d)" % (len(words), ABSTRACT_MAX))
    if "\\cite" in m.group(1):
        bad.append("abstract carries a citation")
    kw = re.search(r"\\textbf\{Keywords:\}(.*?)\n\n", t, re.S)
    if not kw or len([x for x in kw.group(1).split(";") if x.strip()]) > KEYWORDS_MAX:
        bad.append("keywords missing or more than %d" % KEYWORDS_MAX)
    if "\\includegraphics" not in t:
        bad.append("no data figure")
    return bad


def check_claims(i):
    """No novelty or exactness claims; no claim that the author read or edited AI text."""
    t = re.sub(r"\s+", " ", body(i).lower())
    bad = []
    for pat in (r"\bthe first\b(?! (?:final|release|file|row|column|time|of its|of the three))",
                r"\bfirst to\b", r"\bnovel\b", r"\bno false positives?\b", r"\bexact detectors?\b",
                r"\bcannot produce a false\b", r"\bunprecedented\b", r"\bnobody\b"):
        for m in re.finditer(pat, t):
            bad.append("claim pattern %r: ...%s..." % (pat, t[max(0, m.start() - 40):m.end() + 30]))
    for pat in (r"author[s]? (?:has |have )?(?:read|reviewed|edited|revised|checked|verified)\b",
                r"reviewed and edited by the author"):
        if re.search(pat, t):
            bad.append("the AI statement claims an author review that has not happened")
    if "generative ai" not in t and "claude" not in t:
        bad.append("no AI-use statement")
    if t.count("claude") < 2:
        bad.append("AI use must be stated both in Methods and in the Acknowledgements")
    return bad


def check_typography(i):
    bad = []
    for name, txt in (("tex", i["tex"]), ("numbers", i["numbers"]), ("pdf", i["pdf"])):
        for ch, label in (("\u2013", "en dash"), ("\u2014", "em dash"), ("\ufffd", "U+FFFD")):
            if ch in txt:
                bad.append("%s contains %s" % (name, label))
    t = re.sub(r"\\code\{[^}]*\}", "", body(i))
    t = re.sub(r"\\draw.*", "", t)
    if re.search(r"(?<![-!<>=~])--(?!-)", t) or "---" in t:
        bad.append("tex source has -- or --- that LaTeX turns into a dash")
    return bad


def check_pdf(i):
    """The built PDF carries every confirmed project, every DOI and no unresolved reference."""
    if not i["pdf"]:
        return ["no built PDF to read back"]
    txt = re.sub(r"\s+", "", i["pdf"].replace("\ufb01", "fi").replace("\ufb02", "fl")).lower()
    bad = []
    if "??" in i["pdf"]:
        bad.append("PDF has an unresolved reference (??)")
    for F in ("U", "P"):
        for p in i["analysis"]["lists"][F]["confirmed"]:
            if re.sub(r"\s+", "", p).lower() not in txt:
                bad.append("confirmed project %s missing from the PDF" % p)
    for x, r in i["refs"]["doi"].items():
        if r["doi"].lower() not in txt:
            bad.append("DOI %s missing from the PDF" % r["doi"])
    return bad


CHECKS = [check_partitions, check_chain, check_percentages, check_macros_defined, check_literals,
          check_refs, check_attribution, check_cover, check_front, check_claims, check_typography, check_pdf]


def run(i, quiet=False):
    failed = 0
    for c in CHECKS:
        bad = c(i)
        if not quiet:
            print("  %-4s %-22s %s" % ("ok" if not bad else "FAIL", c.__name__,
                                        "" if not bad else "; ".join(bad[:4])))
        failed += bool(bad)
    return failed


if __name__ == "__main__":
    f = run(load_inputs())
    print("GATE %s (%d of %d checks failed)" % ("PASS" if not f else "FAIL", f, len(CHECKS)))
    sys.exit(1 if f else 0)
