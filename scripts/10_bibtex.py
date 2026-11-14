r"""Write references.bib from the resolved records, with the author lists Crossref actually holds.

The keys are the ones already written into the manuscript prose, so the reference list and the
citations cannot drift apart; 05_resolve_refs.py assigned them and checked every returned title
against the one asked for.

NO PAGES FIELD. Numbered styles render a page range with an en dash, and this workspace
forbids en and em dashes anywhere in a submission - a rule paid for on paper 25, where ACM's style
did the same thing and neither a plain hyphen nor a braced range survived it. Every entry carries a
DOI instead, which is what a reader needs to find the work.

Crossref returns markup in titles - <scp>, &amp; - and escaping before stripping turns an entity
into a literal backslash-ampersand-amp. Tags first, then entities, then LaTeX escaping.

    py 06_bibtex.py
"""
import html
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "research", "references.json")
DEST = os.path.join(ROOT, "draft", "references.bib")
UA = {"User-Agent": "bib-build/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

UNMAPPED = set()

TYPE_MAP = {"journal-article": "article", "proceedings-article": "inproceedings",
            "book-chapter": "incollection", "posted-content": "misc", "report": "techreport"}


# ACCENTED AUTHOR NAMES MUST SURVIVE, AND THEY DID NOT AT FIRST. The anchor paper's authors are
# Hungarian - Horvath, Beszedes Arpad, Balogh Gergo, Gyimothy Tibor - and Crossref returns some of
# those characters DECOMPOSED: "Gergo" plus U+030B, a combining double acute, rather than the
# precomposed letter. pdflatex could not render the combining mark and emitted U+FFFD into the
# printed reference list. Mangling a cited author's name is a real error, not a cosmetic one, so
# the text is normalised to its composed form and then mapped to LaTeX accent macros, which the
# class renders whatever font is in use.
ACCENTS = {
    "á": r"\'a", "é": r"\'e", "í": r"\'i", "ó": r"\'o", "ú": r"\'u", "ý": r"\'y",
    "Á": r"\'A", "É": r"\'E", "Í": r"\'I", "Ó": r"\'O", "Ú": r"\'U",
    "à": r"\`a", "è": r"\`e", "ì": r"\`i", "ò": r"\`o", "ù": r"\`u",
    "À": r"\`A", "È": r"\`E", "Ò": r"\`O",
    "â": r"\^a", "ê": r"\^e", "î": r"\^i", "ô": r"\^o", "û": r"\^u",
    "ä": r'\"a', "ë": r'\"e', "ï": r'\"i', "ö": r'\"o', "ü": r'\"u',
    "Ä": r'\"A', "Ö": r'\"O', "Ü": r'\"U',
    "ő": r"\H{o}", "ű": r"\H{u}", "Ő": r"\H{O}", "Ű": r"\H{U}",
    "ñ": r"\~n", "Ñ": r"\~N", "ç": r"\c{c}", "Ç": r"\c{C}",
    "å": r"\aa{}", "Å": r"\AA{}", "ø": r"\o{}", "Ø": r"\O{}",
    "æ": r"\ae{}", "Æ": r"\AE{}", "ß": r"\ss{}",
    "š": r"\v{s}", "č": r"\v{c}", "ž": r"\v{z}", "ř": r"\v{r}",
    "Š": r"\v{S}", "Č": r"\v{C}", "Ž": r"\v{Z}",
    "ł": r"\l{}", "Ł": r"\L{}", "ą": r"\k{a}", "ę": r"\k{e}",
    "ń": r"\'n", "ś": r"\'s", "ź": r"\'z", "ż": r"\.z",
    # Found by the guard below on the second run rather than anticipated: a non-breaking space in a
    # journal name, a Turkish dotless i in an author's name, and a U+2010 hyphen that is not the
    # ASCII one and does not render.
    " ": " ", "ı": r"\i{}", "İ": r"\.I", "‐": "-", "‑": "-", "−": "-",
}


def esc(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = html.unescape(s)
    s = unicodedata.normalize("NFC", s)          # recompose before mapping, or o + U+030B survives
    s = s.replace("\\", " ")
    s = s.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")
    s = (s.replace("–", "-").replace("—", "-").replace("’", "'")
          .replace("“", '"').replace("”", '"'))
    s = "".join(ACCENTS.get(c, c) for c in s)
    # Anything still outside ASCII was not in the table; report it rather than print a box.
    leftover = sorted({c for c in s if ord(c) > 127})
    if leftover:
        UNMAPPED.update(leftover)
    s = re.sub(r"\s+([:;,.])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def get(doi):
    url = "https://api.crossref.org/works/" + urllib.request.quote(doi)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))["message"]
        except Exception as e:
            if attempt == 3:
                return {"__error__": str(e)}
            time.sleep(3)
    return {"__error__": "unreachable"}


data = json.load(io.open(SRC, encoding="utf-8"))
entries, failures = [], []

for rec in data["resolved"]:
    m = get(rec["doi"])
    if "__error__" in m:
        failures.append("%s (%s): %s" % (rec["key"], rec["doi"], m["__error__"]))
        continue
    authors = []
    for a in m.get("author") or []:
        fam, giv = a.get("family"), a.get("given")
        if fam and giv:
            authors.append("%s, %s" % (fam, giv))
        elif fam:
            authors.append(fam)
        elif a.get("name"):
            authors.append(a["name"])
    if not authors:
        failures.append("%s: Crossref holds no author list" % rec["key"])
        continue

    title = esc((m.get("title") or [""])[0])
    venue = esc((m.get("container-title") or [""])[0])
    kind = TYPE_MAP.get(m.get("type"), "misc")
    try:
        year = m["issued"]["date-parts"][0][0]
    except Exception:
        year = rec.get("year") or ""

    lines = ["@%s{%s," % (kind, rec["key"]),
             "  author    = {%s}," % " and ".join(esc(a) for a in authors),
             "  title     = {{%s}}," % title]
    if venue:
        # A chapter's container is a book, not a journal. Emitting `journal` for @incollection made
        # BibTeX warn about an empty booktitle and print the entry without its container at all.
        field = "booktitle" if kind in ("inproceedings", "incollection") else "journal"
        lines.append("  %-9s = {%s}," % (field, venue))
    lines.append("  year      = {%s}," % year)
    if m.get("volume"):
        lines.append("  volume    = {%s}," % esc(m["volume"]))
    if m.get("issue"):
        lines.append("  number    = {%s}," % esc(m["issue"]))
    if m.get("publisher") and kind != "article":
        lines.append("  publisher = {%s}," % esc(m["publisher"]))
    lines.append("  doi       = {%s}" % rec["doi"])
    lines.append("}")
    entries.append((rec["key"], "\n".join(lines)))
    print("   %-22s %s" % (rec["key"], title[:62]))
    time.sleep(0.3)

if failures:
    print()
    print("STOP: %d entry could not be built. Nothing written." % len(failures))
    for f in failures:
        print("   %s" % f)
    sys.exit(1)

body = "\n\n".join(e for _, e in sorted(entries))
for ch, name in ((u"–", "en dash"), (u"—", "em dash")):
    if ch in body:
        print("STOP: an %s reached the .bib" % name)
        sys.exit(1)

# CHECK BEFORE WRITING, not after. The first version wrote the file and then reported that it
# contained characters LaTeX could not render, which leaves a bad .bib on disk for the next build to
# pick up. A gate that fires after the damage is a report, not a gate.
if UNMAPPED:
    print()
    print("STOP: characters with no LaTeX mapping would reach the .bib: %s"
          % [(c, "U+%04X" % ord(c)) for c in sorted(UNMAPPED)])
    print("Nothing written. Add them to ACCENTS with the macro that renders them.")
    sys.exit(1)

io.open(DEST, "w", encoding="utf-8").write(body + "\n")
print()
print("%d entries -> draft/references.bib" % len(entries))
