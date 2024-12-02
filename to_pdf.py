# Use this script to generate a .tex document which can be built with latex. This is manual, I only needed to do it once.

preamble = r"""
\documentclass{article}
\usepackage{graphicx}
\usepackage[a4paper,landscape,margin=0pt]{geometry}
\usepackage{pdfpages}

\begin{document}
\thispagestyle{empty}
\noindent
"""


image = """
\\includegraphics[width=\\paperwidth,height=\\paperheight]{{{image}}}
\\newpage
\includepdf[pages=1]{{background.pdf}}
"""

postamble = r"""
\end{document}
"""


from pathlib import Path

images = list(Path(__file__, "..").resolve().glob("*.png"))

print(preamble)
for img in images:
    print(image.format(image=img.name))

print(postamble)
