r"""Resolve every cited DOI against Crossref and cross-check the author list against a second index
(Semantic Scholar batch endpoint). Writes v2/research/references.json and v2/draft/references.bib.

A reference whose author family names differ between the two indexes, or that one index does not
hold, is printed and marked; the gate refuses a bibliography with an unchecked author list.
Web-only sources (specifications, documentation, software) carry a URL and an access date.

    py v2/scripts/30_refs.py
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "reference-check/2.0"}

DOIS = {
    "peng2024": "10.1145/3597503.3639077",
    "li2025": "10.1016/j.jss.2025.112337",
    "malloy2017": "10.1109/esem.2017.45",
    "malloy2019": "10.1007/s10664-018-9637-2",
    "ye2022": "10.1145/3510003.3510127",
    "yang2024": "10.1587/transinf.2023edp7238",
    "horton2019": "10.1109/icse.2019.00047",
    "wang2020": "10.1145/3377811.3380426",
    "wang2022": "10.1145/3551349.3560437",
    "decan2019": "10.1007/s10664-017-9589-y",
    "valiev2018": "10.1145/3236024.3236062",
    "kalliamvakou2014": "10.1145/2597073.2597074",
    "nagappan2013": "10.1145/2491411.2491415",
    "scalabrino2019": "10.1109/msr.2019.00055",
    "zerouali2019": "10.1002/smr.2157",
    "ochoa2022": "10.1007/s10664-021-10052-y",
    "gao2024": "10.1145/3660822",
}
WEB = {
    "pep345": ("PEP 345: Metadata for Python Software Packages 1.2", "Jones R", 2005,
               "https://peps.python.org/pep-0345/"),
    "pep440": ("PEP 440: Version Identification and Dependency Specification", "Coghlan A, Stufft D",
               2013, "https://peps.python.org/pep-0440/"),
    "pep425": ("PEP 425: Compatibility Tags for Built Distributions", "Holth D", 2012,
               "https://peps.python.org/pep-0425/"),
    "astdoc": ("ast: Abstract Syntax Trees (Python 3.13 documentation)",
               "Python Software Foundation", 2025, "https://docs.python.org/3.13/library/ast.html"),
    "vermin": ("Vermin: Concurrently detect the minimum Python versions needed to run code, "
               "version 1.9.2", "Kristensen M", 2026, "https://github.com/netromdk/vermin"),
    "toppypi": ("Top PyPI Packages: monthly dump of the 15,000 most-downloaded packages",
                "van Kemenade H", 2026, "https://hugovk.github.io/top-pypi-packages/"),
}


def get(url, data=None):
    for a in range(5):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **({"Content-Type": "application/json"}
                                                                  if data else {})),
                                         data=json.dumps(data).encode() if data else None)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(15 * (a + 1))
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def main():
    out = {}
    for k, doi in DOIS.items():
        m = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))["message"]
        title = " ".join(m.get("title") or [])
        if m.get("subtitle"):
            title += ": " + " ".join(m["subtitle"])
        out[k] = {"doi": doi, "title": title,
                  "container": (m.get("container-title") or [""])[0],
                  "year": (m.get("issued", {}).get("date-parts") or [[None]])[0][0],
                  "volume": m.get("volume"), "issue": m.get("issue"), "page": m.get("page"),
                  "article": m.get("article-number"), "type": m.get("type"),
                  "crossref_authors": [[a.get("given", ""), a.get("family", a.get("name", ""))]
                                       for a in m.get("author") or []]}
        time.sleep(1)
    s2 = get("https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,authors,year",
             {"ids": ["DOI:" + d for d in DOIS.values()]}) or []
    for (k, doi), p in zip(DOIS.items(), s2 + [None] * (len(DOIS) - len(s2))):
        r = out[k]
        if not p:
            r["second_index"] = "missing"
            continue
        a2 = [a.get("name", "") for a in p.get("authors") or []]
        fam1 = [norm(f) for _, f in r["crossref_authors"]]
        fam2 = [norm(n.split()[-1]) if n.split() else "" for n in a2]
        r["s2_authors"] = a2
        r["second_index"] = "agree" if fam1 == fam2 else "DISAGREE"
    for k, r in out.items():
        print("%-16s %-8s %s | %s" % (k, r.get("second_index"), r["year"], r["title"][:70]))
        if r.get("second_index") != "agree":
            print("     crossref:", [f for _, f in r["crossref_authors"]])
            print("     s2      :", r.get("s2_authors"))
    json.dump({"doi": out, "web": WEB}, open(os.path.join(V2, "research", "references.json"), "w",
                                             encoding="utf-8"), ensure_ascii=False, indent=1)
    # BibTeX
    bib = []
    for k, r in sorted(out.items()):
        auth = " and ".join("%s, %s" % (f, g) for g, f in r["crossref_authors"])
        typ = "article" if r["type"] == "journal-article" else "inproceedings"
        cont = "journal" if typ == "article" else "booktitle"
        f = ["  author = {%s}" % auth, "  title = {%s}" % r["title"],
             "  %s = {%s}" % (cont, r["container"]), "  year = {%s}" % r["year"],
             "  doi = {%s}" % r["doi"]]
        if r["volume"]:
            f.append("  volume = {%s}" % r["volume"])
        if r["issue"]:
            f.append("  number = {%s}" % r["issue"])
        if r["page"] or r["article"]:
            f.append("  pages = {%s}" % (r["page"] or r["article"]).replace("--", "-").replace("–", "-"))
        bib.append("@%s{%s,\n%s\n}" % (typ, k, ",\n".join(f)))
    for k, (title, auth, year, url) in sorted(WEB.items()):
        bib.append("@misc{%s,\n  author = {%s},\n  title = {%s},\n  year = {%s},\n"
                   "  howpublished = {\\url{%s}},\n  note = {Accessed 14 November 2026}\n}"
                   % (k, "{" + auth + "}" if "Foundation" in auth else auth, title, year, url))
    os.makedirs(os.path.join(V2, "draft"), exist_ok=True)
    open(os.path.join(V2, "draft", "references.bib"), "w", encoding="utf-8").write(
        "\n\n".join(bib) + "\n")
    print("written references.json and draft/references.bib")


main()
