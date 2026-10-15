"""Optional renderer: pip install weasyprint==70.0; requires Pango and DejaVu Sans."""

import argparse

from weasyprint import CSS, HTML

p = argparse.ArgumentParser()
p.add_argument("html")
p.add_argument("pdf")
a = p.parse_args()
HTML(filename=a.html).write_pdf(
    a.pdf,
    stylesheets=[
        CSS(
            string="""
@page {size:A4; margin:14mm;}
body {font-family: "DejaVu Sans", sans-serif;}
.card {break-inside:avoid;}
.ev {border-top:1px solid #ddd;}
.q {break-after:avoid;}
figure img {max-height:85mm; width:auto; max-width:100%;}
"""
        )
    ],
)
