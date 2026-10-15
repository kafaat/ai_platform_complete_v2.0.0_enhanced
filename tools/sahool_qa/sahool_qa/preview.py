"""Self-contained Arabic HTML preview (prints cleanly to PDF).

* Images are embedded as data URIs, so nothing goes missing on export.
* Text is bidi-safe by construction (hyphen ranges, LRI/PDI around
  coordinate lists, ISO dates); options without Arabic letters are laid out
  as LTR blocks; contexts are one block per line.
* One example per family, plus coverage per split and the data-issue summary.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

from .config import EVIDENCE_KINDS, LEVELS

_LTR = re.compile(
    r"(\[[^\]\n]{1,200}\]"  # bracketed lists (bbox)
    r"|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:[+-]\d{2}:\d{2})?)?)?"  # ISO dates / timestamps
    r"|[A-Za-z_][A-Za-z0-9_\-./=:]*(?:\s?\([A-Za-z0-9 ,.]+\))?"  # Latin tokens (SA-3, demo-tenant, dS/m, Vincenty)
    r"|±?[\d٠-٩][\d٠-٩.,٫٬]*(?:[–\-][\d٠-٩][\d٠-٩.,٫٬]*)?%?)"
)


_GEOJSON = re.compile(r'\{"type":"(?:Multi)?Polygon","coordinates":(\[.*?\]{3,4})\}')


def short_context(text: str, limit: int = 420) -> str:
    """Preview only: polygons summarised, long contexts truncated (full text is in the JSONL)."""
    text = _GEOJSON.sub(
        lambda m: f"[مضلع: {m.group(1).count('],[') + 1} رأساً — كاملاً في ملف JSONL]", text
    )
    return (
        text
        if len(text) <= limit
        else text[:limit].rsplit(" ", 1)[0] + " … (السياق الكامل في ملف JSONL)"
    )


def ltr(text: str) -> str:
    """Escape, and render numbers / ranges / dates / identifiers as atomic LTR
    inline boxes. An inline-block cannot be reordered by any bidi
    implementation, old (wkhtmltopdf) or new, unlike <bdi> or bare text."""
    text = re.sub("[\u2066-\u2069]", "", text)
    if not re.search(r"[\u0600-\u06ff]", text):
        return f'<span class="n" dir="ltr">{html.escape(text)}</span>'
    out, pos = [], 0
    for m in _LTR.finditer(text):
        out.append(html.escape(text[pos : m.start()]))
        out.append(f'<span class="n" dir="ltr">{html.escape(m.group(0))}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def plain(text: str) -> str:
    return html.escape(re.sub("[\u2066-\u2069]", "", text))


def evidence_line(text: str) -> str:
    if re.match(
        r"^(TAW|ETc|p|RAW|Dr0|Ks|I_net|ET_actual|DP|Dr_end|Ks_end|V_gross|Q_well|Q_total|pump_days"
        r"|θFC|θWP|Zr|p_table|Ea|fao_crop) = ",
        text,
    ):
        return f'<div class="formula" dir="ltr">{html.escape(text)}</div>'
    return f"<div>{ltr(text)}</div>"


CSS = """
:root{--green:#367C2B;--yellow:#FFDE00;--ink:#1d2a1b;--muted:#5d6b5a;--line:#dfe6dc;--bg:#f7f9f5;--card:#fff;
--ok:#e8f3e4;--warn:#fff6d6;--bad:#fde8e6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#e8efe5;--muted:#a9b8a4;--line:#34402f;
--bg:#141a12;--card:#1c2419;--ok:#20331b;--warn:#3a3313;--bad:#3d1d1a}}
*{box-sizing:border-box}
.card,.ev,figcaption,.q,.banner,p{text-align:right;overflow-wrap:anywhere;word-wrap:break-word}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:Tajawal,"Noto Naskh Arabic","Segoe UI",Tahoma,sans-serif;line-height:1.7}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px;color:var(--green)}h2{font-size:19px;margin:32px 0 10px}
.meta{color:var(--muted);font-size:14px}.banner{background:var(--warn);border-inline-start:4px solid var(--yellow);
padding:10px 14px;border-radius:6px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:14px;background:var(--card)}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:start;vertical-align:top}th{background:var(--ok)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0;
break-inside:avoid;page-break-inside:avoid}
.tag{display:inline-block;font-size:12px;background:var(--ok);color:var(--green);border-radius:999px;padding:1px 10px;
margin-inline-end:6px}.tag.abst{background:var(--warn);color:#7a5b00}.tag.kind{background:#eef0fb;color:#3b4a8a}
.q{font-weight:700;font-size:16.5px;margin:8px 0}
ol.opts{list-style:none;padding:0;margin:8px 0}ol.opts li{padding:4px 10px;border-radius:6px;margin:3px 0;
border:1px solid var(--line)}ol.opts li.ans{background:var(--ok);border-color:var(--green);font-weight:700}
.ev{font-size:13px;color:var(--muted);border-top:1px dashed var(--line);margin-top:10px;padding-top:8px}
figure{margin:10px 0}figure img{max-width:100%;image-rendering:pixelated;border-radius:6px;display:block}
figcaption{font-size:12.5px;color:var(--muted)}
.balance .ev{font-size:12px;line-height:1.45}
.formula{direction:ltr;unicode-bidi:isolate;text-align:left;overflow-wrap:anywhere;margin:3px 0}
.n{display:inline-block;direction:ltr;unicode-bidi:embed}
ol.opts li .v[dir=ltr]{display:inline-block;direction:ltr;unicode-bidi:embed}
.ctx{font-size:12.5px;color:var(--muted)}.ctx div{margin:2px 0}
@media print{body{background:#fff}.card{border-color:#bbb}}
"""


_ARABIC = re.compile("[\u0600-\u06ff]")


def _opt(text: str) -> str:
    """Options without Arabic letters (coordinate lists, 'x-y mg/kg') are laid out as LTR blocks."""
    clean = re.sub("[\u2066-\u2069]", "", text)
    if not _ARABIC.search(clean):
        return f'<span class="v" dir="ltr">{html.escape(clean)}</span>'
    return f'<span class="v">{ltr(clean)}</span>'


def _img(out: Path, rel: str) -> str:
    p = out / rel
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def render_preview(items: list[dict], manifest: dict, out: Path) -> str:
    c = manifest["counts"]
    parts = [
        '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>معاينة أسئلة سهول</title><style>{CSS}</style></head><body><main>",
        "<h1>معاينة أسئلة سهول</h1>",
        f'<div class="meta">{ltr(manifest["generator"])} · {ltr(manifest["created_utc"])} · '
        f"المصدر {ltr(manifest['source'])} · النطاق {html.escape(manifest['tenant_scope'])} · "
        f'بصمة المدخلات <bdi dir="ltr">{manifest["input_fingerprint"]}</bdi></div>',
    ]
    if manifest["synthetic"] or manifest.get("synthetic_rasters"):
        parts.append(
            '<div class="banner"><b>مدخلات اصطناعية</b> — هذه الأسئلة لاختبار خط الإنتاج، لا لتقييم المعرفة الزراعية.</div>'
        )
    for w in manifest["warnings"]:
        parts.append(f'<div class="banner">{ltr(w)}</div>')
    parts.append(
        f"<p>عدد الأسئلة {ltr(str(c['items_total']))} — منها {ltr(str(c['abstention_correct']))} إجابتها الصحيحة الامتناع، "
        f"و{ltr(str(c['with_image']))} بصورة. خط الصدفة لكل تقسيم: "
        + "، ".join(
            f"{s} {ltr(str(round(100 * v, 1)))}%" for s, v in manifest["chance_accuracy"].items()
        )
        + "؛ ودقة من يختار الامتناع دائماً: "
        + "، ".join(
            f"{s} {ltr(str(round(100 * v, 1)))}%"
            for s, v in manifest.get("always_abstain_accuracy", {}).items()
        )
        + "</p>"
    )

    splits = list(manifest["coverage"])
    fams = sorted({f for s in splits for f in manifest["coverage"][s]})
    parts.append(
        "<h2>التغطية حسب العائلة والتقسيم</h2><table><tr><th>العائلة</th>"
        + "".join(
            f"<th>{s}<br><small>أسئلة / وحدات مصدر / امتناع / صور</small></th>" for s in splits
        )
        + "</tr>"
    )
    for f in fams:
        row = f"<tr><td><bdi dir='ltr'>{f}</bdi></td>"
        for s in splits:
            v = manifest["coverage"][s].get(f)
            if v:
                cell = "{} / {} / {} / {}".format(
                    v["items"], v["units"], v["abstention"], v["with_image"]
                )
                row += "<td>" + ltr(cell) + "</td>"
            else:
                row += "<td>—</td>"
        parts.append(row + "</tr>")
    parts.append("</table>")

    di = manifest["data_issues"]["by_code"]
    if di:
        parts.append(
            "<h2>مشكلات البيانات</h2><table><tr><th>الرمز</th><th>العدد</th></tr>"
            + "".join(
                f"<tr><td><bdi dir='ltr'>{k}</bdi></td><td>{v}</td></tr>"
                for k, v in sorted(di.items())
            )
            + "</table>"
        )

    parts.append(
        '<h2>مثال من كل عائلة</h2><p class="meta">السياق الخام لكل سؤال (السجلات كما يجلبها الوكيل) '
        "موجود في ملفات JSONL ولا يُطبع هنا.</p>"
    )
    order = list(LEVELS)
    chosen = {}
    for it in sorted(
        items,
        key=lambda r: (
            order.index(r["level"]),
            r["family"],
            "image" not in r,
            not r["answerable"],
            r["id"],
        ),
    ):
        chosen.setdefault(it["family"], it)
    abst = {}
    for it in sorted(items, key=lambda r: r["id"]):
        if not it["answerable"]:
            abst.setdefault(it["family"], it)
    for it in (
        list(chosen.values())
        + [a for f, a in sorted(abst.items()) if chosen[f]["id"] != a["id"]][:4]
    ):
        tags = f'<span class="tag">{it["level_ar"]}</span><span class="tag"><bdi dir="ltr">{it["family"]}</bdi></span>'
        tags += f'<span class="tag kind">دليل {EVIDENCE_KINDS[it["evidence"]["kind"]]}</span>'
        if not it["answerable"]:
            tags += '<span class="tag abst">إجابتها الامتناع</span>'
        card_class = "card balance" if it["family"] == "water.stress_status" else "card"
        card = [f'<section class="{card_class}">{tags}<div class="q">{ltr(it["question"])}</div>']
        if it.get("image"):
            src = _img(out, it["image"])
            legend = next((x for x in it["context"].split("\n") if x.startswith("الصورة:")), "")
            card.append(
                f'<figure><img src="{src}" alt="{html.escape(it["id"])}"><figcaption>{ltr(legend)}</figcaption></figure>'
            )
        card.append(
            '<ol class="opts">'
            + "".join(
                f'<li class="{"ans" if o["key"] == it["answer"] else ""}">{o["key"]}) {_opt(o["text"])}'
                f"{' ✓' if o['key'] == it['answer'] else ''}</li>"
                for o in it["options"]
            )
            + "</ol>"
        )
        ev = it["evidence"]
        evtxt = ev.get("computation", "")
        if ev.get("rule"):
            evtxt += " — القاعدة: " + ev["rule"]
        if ev.get("caveats"):
            evtxt += " — تحفّظات: " + "؛ ".join(ev["caveats"])
        # one block per line: a formula like "TAW = 1000 × (θFC − θWP) × Zr" stays a single left-to-right run
        evhtml = "".join(evidence_line(line) for line in evtxt.split("\n") if line.strip())
        card.append(
            f'<div class="ev">{evhtml}<div dir="ltr" style="text-align:right">{it["id"]} · {it["split"]}</div></div>'
        )
        card.append(
            "</section>"
        )  # the raw-record context is in the JSONL files; it is noise in a printed preview
        parts.append("".join(card))
    parts.append("</main></body></html>")
    return "\n".join(parts)
