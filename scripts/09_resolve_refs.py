r"""Resolve the references this paper actually engages, by title, and refuse the ones that do not match.

WRITTEN FIRST, RESOLVED SECOND. The list below is the works this argument has to answer, chosen by
reading the novelty screens rather than by harvesting a keyword pool. Paper 27 tried the pool route
and found the search undiscriminating in this space: "coverage" returned satellite constellations
and vaccination programmes. A bibliography assembled from a query is a bibliography of the query.

TWO INDEPENDENT ASSERTIONS PER ENTRY, NOT ONE. The title must match at 0.8 overlap AND the year in
the citation key must match the resolved year within one. Paper 27's bibliography carried the wrong
work because a 2016 book chapter shares its title with the 2013 conference paper it summarises, and
the title scored 1.00. The year check rejected six same-title candidates for that key.

Grouped by the job each does in the paper, which is also the order they appear in it.

    py 09_resolve_refs.py
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "references.json")
UA = {"User-Agent": "ref-resolve/1.0 (mailto:emil.huseynov.zabil@bsu.edu.az)"}

WANTED = [
    # --- the venue's own record. Cite it and position against it.
    ("cran2020", "Evolution and prospects of the Comprehensive R Archive Network CRAN package ecosystem",
     "JSEP. a package registry studied as a registry - the closest venue precedent"),
    ("techlag2019", "A formal framework for measuring technical lag in component repositories",
     "JSEP. a declared version against what is actually there - our shape, different property"),
    ("privaterepos2026", "Security Assessment of Private Package Repositories",
     "JSEP 2026. package repositories, current"),
    ("pytechdebt2020", "Evolution of technical debt remediation in Python",
     "JSEP. Python ecosystem mining in this journal"),

    # --- declared versus actual in a neighbouring ecosystem, where a compiler enforces the level
    ("androidcompat2024", "An empirical study on compatibility issues in Android API",
     "IST 2024. the same problem class where the platform enforces the declared level"),
    ("androidapi2019", "Data-driven solutions to detect API compatibility issues in Android",
     "MSR 2019. detecting a declared support level the code contradicts"),

    # --- what the neighbourhood actually is: conflicts BETWEEN packages, not within one
    # Crossref's bibliographic query cannot find this one from its title - it scores below 0.8
    # against every candidate returned - so the DOI is given directly, taken from DBLP's own record
    # of the ICSE 2020 proceedings. A DOI given by hand is resolved and title-checked like any
    # other; it skips the search, not the verification.
    ("watchman2020", "DOI:10.1145/3377811.3380426",
     "ICSE 2020. the canonical Python dependency-conflict work; a different object"),
    ("smartpip2022", "smartPip: A Smart Approach to Resolving Python Dependency Conflict Issues",
     "ASE 2022. resolution rather than declaration"),
    ("pydepconflict2024", "An Empirical Study on Python Library Dependency and Conflict Issues",
     "QRS 2024. how common conflicts are between packages"),

    # --- what a version number promises across releases, which is the adjacent claim
    ("semver2017", "Semantic versioning and impact of breaking changes in the Maven repository",
     "JSS 2017. a declared compatibility signal measured against reality"),
    ("breakingbad2022", "Breaking bad? Semantic versioning and impact of breaking changes",
     "EMSE 2022. the replication at ecosystem scale"),
    ("semverscam2014", "Semantic Versioning versus Breaking Changes",
     "SCAM 2014. the original measurement of the same kind of promise"),
    ("zerospace2021", "Lost in zero space - an empirical comparison of 0.y.z releases in software package distribution systems",
     "SCICO 2021. a declared version signal in package distribution systems"),

    # --- the registry as a frame, and what a sample drawn from it can support
    ("bommarito2019", "An Empirical Analysis of the Python Package Index",
     "the frame this study draws from, characterised"),
    ("decan2019", "An empirical comparison of dependency network evolution in seven software packaging ecosystems",
     "how ecosystems differ, which bounds external validity"),
    ("valiev2018", "Ecosystem-level determinants of sustained activity in open-source projects",
     "PyPI at ecosystem scale"),
    ("kalliamvakou2014", "The promises and perils of mining GitHub",
     "the canonical threats for repository-derived samples"),
    ("nagappan2013", "Diversity in software engineering research",
     "sampling and what a sample can support"),
    ("dockerpkgs2021", "On the usage of JavaScript, Python and Ruby packages in Docker Hub images",
     "package ecosystem mining, and how declarations travel into images"),

    # --- declared versus actual INSIDE one package: the closest family, on a different property
    ("typeevo2022", "The evolution of type annotations in Python: an empirical study",
     "FSE 2022. the canonical measurement of a declared property of Python source"),
    ("typeadopt2026", "How do third-party Python libraries use type annotations",
     "MSR 2026. adoption and public-API coverage; killed a neighbouring idea for this paper"),
    ("pystatictypes2023", "Towards a Large-Scale Empirical Study of Python Static Type Annotations",
     "SANER 2023. defects in a declared property, at scale"),
    ("gradualcheck2023", "How Well Static Type Checkers Work with Gradual Typing",
     "ICPC 2023. a tool acting on a partial declaration"),

    # --- a published signal consumed far from the context that produced it
    ("zahan2023", "Software Bills of Materials Are Required. Are We There Yet?",
     "a published assurance consumed far from its context"),
    ("wermke2022", "Committed to Trust: A Qualitative Study on Security and Trust in Open Source Software Projects",
     "trust in a signal rests on whether it has been right before"),
    ("enck2022", "Top Five Challenges in Software Supply Chain Security",
     "practitioners establishing facts about artefacts they consume"),

    # --- how the ecosystem's own tooling reads these declarations
    ("pipresolver2022", "An empirical study of dependency downgrades",
     "what a resolver does when a constraint cannot be met"),
    # ("condapypi2021", ...) was written from memory and no such work resolved. Removed rather than
    # loosened into a match: a citation that exists only because the threshold was lowered is worse
    # than a missing one.
]


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            if attempt == 3:
                return None, str(e)
            time.sleep(3)
    return None, "unreachable"


def norm(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def overlap(a, b):
    wa, wb = set(norm(a).split()), set(norm(b).split())
    return (len(wa & wb) / len(wa)) if wa else 0.0


def key_year(key):
    m = re.search(r"(19|20)\d{2}", key)
    return int(m.group(0)) if m else None


def item_year(it):
    try:
        return it["issued"]["date-parts"][0][0]
    except Exception:
        return None


def main():
    resolved, unresolved = [], []
    for key, title, why in WANTED:
        # A DOI given directly still goes through the same record fetch; only the search is skipped.
        if title.startswith("DOI:"):
            doi = title[4:]
            d, err = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
            if err:
                unresolved.append((key, doi, "direct DOI fetch failed: %s" % err))
                print("  FAILED   %-22s %s" % (key, err[:42]))
                continue
            m = d["message"]
            resolved.append({"key": key, "doi": m.get("DOI"),
                             "title": (m.get("title") or [""])[0], "year": item_year(m),
                             "venue": (m.get("container-title") or [""])[0],
                             "type": m.get("type"), "why": why, "match": 1.0,
                             "authors": [{"family": a.get("family"), "given": a.get("given")}
                                         for a in (m.get("author") or [])]})
            print("  ok(doi)  %-22s       %s" % (key, (m.get("title") or [""])[0][:50]))
            time.sleep(0.35)
            continue

        url = ("https://api.crossref.org/works?rows=8"
               "&select=title,DOI,issued,author,container-title,type"
               "&query.bibliographic=%s" % urllib.parse.quote(title))
        d, err = get(url)
        if err:
            unresolved.append((key, title, "query failed: %s" % err))
            print("  FAILED   %-22s %s" % (key, err[:42]))
            continue

        want = key_year(key)
        best, score, rejected = None, 0.0, []
        for it in d["message"]["items"]:
            t = (it.get("title") or [""])[0]
            s = overlap(title, t)
            if s < 0.8:
                continue
            yr = item_year(it)
            if want and yr and abs(yr - want) > 1:
                rejected.append((yr, it.get("DOI"), t))
                continue
            if s > score:
                best, score = it, s

        if not best:
            why_not = ("%d candidate(s) matched the title but not the year %s"
                       % (len(rejected), want)) if rejected else "no title match at 0.8"
            unresolved.append((key, title, why_not))
            print("  NO MATCH %-22s %s" % (key, why_not[:52]))
            time.sleep(0.35)
            continue

        if rejected:
            print("  note     %-22s rejected %d same-title candidate(s) on year"
                  % (key, len(rejected)))
        resolved.append({"key": key, "doi": best.get("DOI"),
                         "title": (best.get("title") or [""])[0],
                         "year": item_year(best),
                         "venue": (best.get("container-title") or [""])[0],
                         "type": best.get("type"), "why": why, "match": round(score, 2),
                         "authors": [{"family": a.get("family"), "given": a.get("given")}
                                     for a in (best.get("author") or [])]})
        print("  ok       %-22s %.2f  %s" % (key, score, (best.get("title") or [""])[0][:50]))
        time.sleep(0.35)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(
        {"resolved": resolved,
         "unresolved": [{"key": k, "title": t, "why": w} for k, t, w in unresolved]},
        ensure_ascii=False, indent=1))

    print()
    print("resolved %d, unresolved %d" % (len(resolved), len(unresolved)))
    if unresolved:
        print()
        print("UNRESOLVED - NOT citable until found by hand:")
        for k, t, w in unresolved:
            print("   %-22s %s" % (k, t[:66]))
            print("   %-22s %s" % ("", w))
    print()
    print("written to research/references.json")
    return 0


sys.exit(main())
