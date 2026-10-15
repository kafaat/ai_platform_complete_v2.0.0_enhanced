"""Score model / agent predictions against generated items.

Predictions: JSONL with {"id": ..., "prediction": "..."} (also accepts
"answer" or "output"). A prediction may be an option letter (أ/ب/ج/د, also
A–D), "أ)"-style, or the option text itself. Anything else is "unparsed".

Reports accuracy by split / level / family, the abstention behaviour that
matters for SAHOOL's recommendation confidence:
  * hallucination rate — chose a value when the data is missing;
  * false abstention   — chose "no data" when the answer was available;
and the chance baseline, so a score can be read against random guessing.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .arabic import LETTERS, normalize
from .config import ABSTAIN_TEXT, LEVELS

_LATIN = dict(zip("ABCDE", LETTERS))
_NLET = {normalize(l): l for l in LETTERS}


def read_jsonl(paths) -> list[dict]:
    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_prediction(pred, item: dict) -> str | None:
    """Return the option key chosen by `pred`, or None if it cannot be parsed."""
    if pred is None:
        return None
    raw = str(pred).strip()
    if not raw:
        return None
    m = re.match(r"^[\(\[]?\s*([A-Ea-e])\s*[\)\]\.:\-]?(\s|$)", raw)
    if m:
        letter = _LATIN.get(m.group(1).upper())
        return letter if any(o["key"] == letter for o in item["options"]) else None
    p = normalize(raw)
    m = re.match(r"^[\(\[]?\s*(ا|ب|ج|د|ه)\s*(?:[\)\]\.:\-،]|\s|$)", p)
    if m:
        letter = _NLET[m.group(1)]
        return letter if any(o["key"] == letter for o in item["options"]) else None
    texts = {o["key"]: normalize(o["text"]) for o in item["options"]}
    for k, t in texts.items():
        if p == t:
            return k
    hits = [k for k, t in texts.items() if t and t in p]
    if len(hits) > 1:  # keep the longest if one option text contains the others
        longest = max(hits, key=lambda k: len(texts[k]))
        if all(texts[h] in texts[longest] for h in hits):
            hits = [longest]
    return hits[0] if len(hits) == 1 else None


def _acc(rows):
    return round(sum(r["correct"] for r in rows) / len(rows), 4) if rows else None


def _rate(num, den):
    return round(num / den, 4) if den else None


def score(gold: list[dict], preds: list[dict]) -> dict:
    """Accuracy counts missing/unparsed predictions as wrong (and reports them).
    Abstention metrics are computed on VALID predictions only, so an
    operational failure is never reported as a hallucination; the strict
    "abstention failure incl. invalid" is reported separately (F05)."""
    pmap = {}
    for p in preds:
        pmap[p.get("id")] = p.get("prediction", p.get("answer", p.get("output")))
    rows = []
    for it in gold:
        chosen = parse_prediction(pmap.get(it["id"]), it) if it["id"] in pmap else None
        if not it["answerable"]:
            abstain_key = it["answer"]
        else:
            abstain_key = next((o["key"] for o in it["options"] if o["text"] == ABSTAIN_TEXT), None)
        rows.append({
            "id": it["id"], "split": it.get("split", "?"), "level": it["level"], "family": it["family"],
            "answerable": it["answerable"], "abstain_offered": abstain_key is not None,
            "missing": it["id"] not in pmap, "unparsed": it["id"] in pmap and chosen is None,
            "valid": chosen is not None, "chosen": chosen,
            "chose_abstain": chosen is not None and chosen == abstain_key,
            "correct": chosen is not None and chosen == it["answer"], "chance": 1 / len(it["options"]),
        })
    by = lambda key: {k: {"n": len(v), "valid": sum(r["valid"] for r in v), "accuracy": _acc(v),  # noqa: E731
                          "accuracy_on_valid": _acc([r for r in v if r["valid"]])}
                      for k, v in sorted(_group(rows, key).items())}
    valid = [r for r in rows if r["valid"]]
    unans = [r for r in rows if not r["answerable"]]
    unans_valid = [r for r in unans if r["valid"]]
    ans_off_valid = [r for r in rows if r["answerable"] and r["abstain_offered"] and r["valid"]]
    return {
        "n_items": len(rows),
        "coverage": _rate(len(valid), len(rows)),
        "accuracy": _acc(rows),
        "accuracy_on_valid": _acc(valid),
        "chance_accuracy": round(sum(r["chance"] for r in rows) / len(rows), 4) if rows else None,
        "missing_predictions": sum(r["missing"] for r in rows),
        "unparsed_predictions": sum(r["unparsed"] for r in rows),
        "by_split": by("split"),
        "by_level": {LEVELS.get(k, k): v for k, v in by("level").items()},
        "by_family": by("family"),
        "abstention": {
            "unanswerable_items": len(unans),
            "valid_predictions": len(unans_valid),
            "invalid_predictions": len(unans) - len(unans_valid),
            "correct_abstention_rate": _rate(sum(r["chose_abstain"] for r in unans_valid), len(unans_valid)),
            "hallucination_rate": _rate(sum(not r["chose_abstain"] for r in unans_valid), len(unans_valid)),
            "abstention_failure_incl_invalid": _rate(sum(not r["chose_abstain"] for r in unans), len(unans)),
            "answerable_with_abstain_offered_valid": len(ans_off_valid),
            "false_abstention_rate": _rate(sum(r["chose_abstain"] for r in ans_off_valid), len(ans_off_valid)),
        },
        "predicted_letters": dict(Counter(r["chosen"] for r in valid)),
        "rows": rows,
    }


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


def render(report: dict) -> str:
    pct = lambda x: "—" if x is None else f"{100 * x:.1f}%"  # noqa: E731
    out = [f"الأسئلة: {report['n_items']} | التغطية: {pct(report['coverage'])} | الدقة: {pct(report['accuracy'])} "
           f"(على التنبؤات الصالحة {pct(report['accuracy_on_valid'])}) | خط الصدفة: {pct(report['chance_accuracy'])}",
           f"تنبؤات مفقودة: {report['missing_predictions']} | غير مفهومة: {report['unparsed_predictions']}", "",
           "| المستوى | العدد | الدقة |", "|---|---|---|"]
    out += [f"| {k} | {v['n']} | {pct(v['accuracy'])} |" for k, v in report["by_level"].items()]
    out += ["", "| العائلة | العدد | الدقة |", "|---|---|---|"]
    out += [f"| {k} | {v['n']} | {pct(v['accuracy'])} |" for k, v in report["by_family"].items()]
    a = report["abstention"]
    out += ["", f"الامتناع: {a['unanswerable_items']} سؤالاً بلا بيانات موثوقة، منها {a['valid_predictions']} بتنبؤ صالح — "
                f"امتناع صحيح {pct(a['correct_abstention_rate'])}، هلوسة {pct(a['hallucination_rate'])} (من التنبؤات الصالحة)؛ "
                f"إخفاق الامتناع شاملاً غير الصالح {pct(a['abstention_failure_incl_invalid'])} | "
                f"امتناع خاطئ عند توفر البيانات: {pct(a['false_abstention_rate'])}"]
    return "\n".join(out)
