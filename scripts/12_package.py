r"""Build what the JSEP submission PORTAL asks for, which is not what its author guidelines describe.

THE PORTAL OVERRIDES ITS OWN GUIDE, and both differences matter. Read from the upload step itself on
28.08.2026:

  MAIN MANUSCRIPT        "Maximum of 1... You may bundle LaTeX manuscript files in a single archive
                         including all LaTeX files, BibTeX files, figures, tables, all LaTeX classes
                         and packages". So ONE archive, not the three separate designations the
                         author guidelines describe ("Main Document - LaTeX .tex File", "Main
                         Document - LaTeX PDF", "LaTeX Supplementary File"). Those designations do
                         not exist on this form.
  GRAPHICAL ABSTRACT     the guidelines say "no more than 80 words or 3 sentences". The portal's own
  TEXT                   upload slot says "A short statement of 50 words or less (1-2 sentences)".
                         The tighter one wins, because it is the one the form enforces.
  GRAPHICAL ABSTRACT     ".jpg, .tif, .png" - not PDF. The figure has to be rasterised.
  IMAGE

Every limit here is enforced rather than trusted, and the figure is lifted out of the manuscript
rather than redrawn so the two cannot drift apart.

    py 12_package.py
"""
import io
import os
import re
import subprocess
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = os.path.join(ROOT, "draft")
FINAL = os.path.join(ROOT, "final")
TECTONIC = os.path.join(os.path.dirname(ROOT), "_shared", "tools", "tectonic.exe")

GA_WORD_MAX = 50            # the portal's number, not the guidelines' 80
GA_SENTENCE_MAX = 2         # the portal's number, not the guidelines' 3
DPI = 600                   # the guidelines ask 600 minimum for drawings, 800 preferred

# Two sentences, 50 words or fewer. Every number appears in the manuscript and in analysis.json.
GA_TEXT = (
    "A PyPI package declares its Python support in three places: classifiers the page shows and no "
    "tool reads, a specifier pip enforces and nothing displays, and wheel tags nobody reads. Only "
    "30.5 percent publish both, and 36 of 1,368 projects install onto interpreters that cannot run "
    "them."
)

FIGURE_TEX = r"""\documentclass[border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{newtxtext}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,fit,backgrounds}
\newcommand{\code}[1]{\texttt{#1}}
\begin{document}
%%FIGURE%%
\end{document}
"""


def stop(msg):
    print("STOP: %s" % msg)
    print("Nothing usable was written.")
    sys.exit(1)


def main():
    os.makedirs(FINAL, exist_ok=True)
    tex_src = os.path.join(DRAFT, "manuscript.tex")
    pdf_src = os.path.join(DRAFT, "manuscript.pdf")
    bib_src = os.path.join(DRAFT, "references.bib")
    for p in (tex_src, pdf_src, bib_src):
        if not os.path.exists(p):
            stop("%s is missing" % p)
    if os.path.getmtime(pdf_src) < os.path.getmtime(tex_src):
        stop("manuscript.pdf is older than manuscript.tex - rebuild before packaging")
    tex = io.open(tex_src, encoding="utf-8").read()

    # ---- 1. the Main Manuscript: one archive, flat
    members = [("manuscript.tex", tex_src), ("references.bib", bib_src)]
    zip_path = os.path.join(FINAL, "JSEP_28_main_manuscript.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in members:
            z.write(src, arcname=arc)
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(z.namelist())
        if z.testzip():
            stop("the archive is corrupt")
    if names != sorted(a for a, _ in members):
        stop("the archive holds %s, not the intended set" % names)
    if any("/" in n or "\\" in n for n in names):
        stop("nested paths in the archive")

    print("=" * 92)
    print("MAIN MANUSCRIPT - one archive, which is what the form asks for")
    print("=" * 92)
    print("   %-34s %8d bytes" % (os.path.basename(zip_path), os.path.getsize(zip_path)))
    for n in names:
        print("      %s" % n)
    print("   reopened and checked: %d members, no nested paths, no build debris" % len(names))

    # ---- 2. the reviewer PDF, kept as an additional file rather than as the main document
    pdf_dest = os.path.join(FINAL, "JSEP_28_manuscript_pdf.pdf")
    io.open(pdf_dest, "wb").write(io.open(pdf_src, "rb").read())
    print()
    print("   %-34s %8d bytes   the locally built PDF, for the reviewer-PDF slot"
          % (os.path.basename(pdf_dest), os.path.getsize(pdf_dest)))

    # ---- 3. the graphical abstract text, against the PORTAL's limits
    words = len(GA_TEXT.split())
    sentences = len([s for s in re.split(r"(?<=[.!?])\s+", GA_TEXT.strip()) if s])
    print()
    print("=" * 92)
    print("GRAPHICAL ABSTRACT TEXT - the portal's limits, not the guidelines'")
    print("=" * 92)
    print("   words     %3d   (portal ceiling %d; the author guidelines say 80)" % (words, GA_WORD_MAX))
    print("   sentences %3d   (portal ceiling %d; the author guidelines say 3)"
          % (sentences, GA_SENTENCE_MAX))
    if words > GA_WORD_MAX:
        stop("the graphical abstract text is %d words, over the portal's %d" % (words, GA_WORD_MAX))
    if sentences > GA_SENTENCE_MAX:
        stop("the text is %d sentences, over the portal's %d" % (sentences, GA_SENTENCE_MAX))
    for ch, name in ((u"\u2013", "en dash"), (u"\u2014", "em dash")):
        if ch in GA_TEXT:
            stop("an %s reached the graphical abstract text" % name)
    ga_txt = os.path.join(FINAL, "JSEP_28_graphical_abstract_text.txt")
    io.open(ga_txt, "w", encoding="utf-8", newline="\n").write(GA_TEXT + "\n")
    print("   %-34s %8d bytes" % (os.path.basename(ga_txt), os.path.getsize(ga_txt)))

    # ---- 4. the graphical abstract image, rasterised because the portal will not take a PDF
    m = re.search(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", tex, re.S)
    if not m:
        stop("could not find the tikzpicture in the manuscript to reuse")
    fig_tex = os.path.join(FINAL, "JSEP_28_figure.tex")
    io.open(fig_tex, "w", encoding="utf-8", newline="\n").write(
        FIGURE_TEX.replace("%%FIGURE%%", m.group(0)))
    r = subprocess.run([TECTONIC, "-X", "compile", "JSEP_28_figure.tex"],
                       cwd=FINAL, capture_output=True, text=True)
    fig_pdf = os.path.join(FINAL, "JSEP_28_figure.pdf")
    if not os.path.exists(fig_pdf):
        print(r.stderr[-1000:])
        stop("the standalone figure did not compile")

    import pymupdf
    doc = pymupdf.open(fig_pdf)
    pix = doc[0].get_pixmap(dpi=DPI)
    png = os.path.join(FINAL, "JSEP_28_graphical_abstract.png")
    pix.save(png)
    doc.close()
    print()
    print("=" * 92)
    print("GRAPHICAL ABSTRACT IMAGE - rasterised, because the slot takes .jpg .tif .png and not PDF")
    print("=" * 92)
    print("   %-34s %8d bytes   %d by %d px at %d dpi"
          % (os.path.basename(png), os.path.getsize(png), pix.width, pix.height, DPI))
    if pix.width < 1000:
        stop("the image is only %d px wide; the journal asks 600 dpi minimum for drawings"
             % pix.width)

    print()
    print("=" * 92)
    print("UPLOAD MAP")
    print("=" * 92)
    print("   Main Manuscript                 JSEP_28_main_manuscript.zip")
    print("   Additional File for Review      JSEP_28_manuscript_pdf.pdf")
    print("   Graphical Abstract Text         JSEP_28_graphical_abstract_text.txt")
    print("   Graphical Abstract Image        JSEP_28_graphical_abstract.png")
    print()
    print("   STILL BY HAND: short title (70 chars), six keywords, and the data availability")
    print("   statement, which now carries github.com/emilhuseyn/pypi-interpreter-claims")
    return 0


sys.exit(main())
