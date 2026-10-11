"""يجمع أوراق المراجعين بعد التقييم ويكشف المفتاح — الحكمُ يبدأ بالأخطاء الحرجة.

    python3 score.py review-001 reviewer_a.csv reviewer_b.csv [--corpus corpus.tsv]

قاعدةٌ صارمة: أيُّ «خطأ حرج = نعم» من أيِّ مراجع على أيِّ مقطع ⇒ المحرّك **مرفوض**، مهما كانت
الطبيعيّة. فـ«لا ترش» مسموعةً «ترش» أو 2.5 مسموعةً 25 خطرٌ مباشر لا يعوّضه صوتٌ جميل.

ولا يُحتسب مراجعٌ مرّتين: كلُّ ورقةٍ تحمل ``reviewer_id`` واحداً غيرَ فارغ، والورقتان المتطابقتان
بايتاً أو المعرّفُ المكرّر أو الصفُّ المكرّر في الورقة تُرفض. والنصُّ والحقائقُ الحرجة في كلِّ صفٍّ
تُطابَق بالنصوص التي بصمتُها في المفتاح، فلا تُقيَّم ورقةٌ أُعدّت على نصوصٍ أخرى. ومقطعٌ قيّمه أقلُّ
من الحدّ الأدنى من المراجعين **المختلفين** يُعدّ ناقصاً لا ناجحاً.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRIT = "خطأ حرج؟ (نعم/لا) — رقم أو وحدة أو جرعة أو مدّة تغيّرت، أو نفيٌ سقط/التبس"
TEXT, FACTS = "النص المكتوب", "الحقائق الحرجة (يجب أن تُسمع حرفيّاً)"


RATING_RANGE = (1.0, 5.0)


def _rating(value, where: str):
    """تقديرٌ «1-5»: فارغٌ ⇒ غيرُ مُقيَّم (None)؛ وغيرُ ذلك يجب أن يكون عدداً منتهياً داخل المدى، وإلّا تُرفض
    الورقةُ باسم الصفّ — لا يُقبل NaN ولا ∞ ولا 7، فتلك تُنتج JSON غيرَ صالح أو متوسّطاتٍ خارج المدى."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        raise SystemExit(f"{where}: تقديرٌ غيرُ عدديّ {text!r}") from None
    if not (math.isfinite(number) and RATING_RANGE[0] <= number <= RATING_RANGE[1]):
        raise SystemExit(f"{where}: تقديرٌ {text!r} خارج {RATING_RANGE[0]:g}–{RATING_RANGE[1]:g}")
    return number


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("review_dir")
    ap.add_argument("sheets", nargs="+")
    ap.add_argument("--corpus", default=str(HERE / "corpus.tsv"))
    ap.add_argument("--min-reviewers", type=int, default=2)
    args = ap.parse_args()
    if args.min_reviewers < 1:
        # 0 أو سالب يجعل كلَّ مقطعٍ «مكتملاً» فينال محرّكٌ بلا أيّ صفٍّ مُقيَّم PASSED_SAFETY_GATE
        raise SystemExit(f"--min-reviewers={args.min_reviewers}: يجب أن يكون 1 على الأقلّ")

    key_doc = json.loads(
        (Path(args.review_dir) / "KEY_DO_NOT_SHARE.json").read_text(encoding="utf-8")
    )
    key = key_doc["clips"]
    corpus_bytes = Path(args.corpus).read_bytes()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()
    if corpus_sha != key_doc.get("corpus_sha256"):
        raise SystemExit(
            f"النصوص {corpus_sha[:16]}… لا تطابق نصوص جولة التقييم {str(key_doc.get('corpus_sha256'))[:16]}…"
        )
    corpus = {
        r["id"]: r
        for r in csv.DictReader(corpus_bytes.decode("utf-8").splitlines(), delimiter="\t")
    }

    seen_sheets, seen_reviewers = {}, {}
    per_engine = defaultdict(lambda: {"critical": [], "clarity": [], "naturalness": []})
    reviewers_per_clip: dict[str, set] = defaultdict(set)
    for sheet in args.sheets:
        raw = Path(sheet).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_sheets:
            raise SystemExit(f"{sheet}: مطابقةٌ بايتاً لـ{seen_sheets[digest]} — لا تُحتسب ورقةٌ مرّتين")
        seen_sheets[digest] = sheet
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
        ids = {(r.get("reviewer_id") or "").strip() for r in rows} - {""}
        if len(ids) != 1 or any(not (r.get("reviewer_id") or "").strip() for r in rows):
            raise SystemExit(
                f"{sheet}: يجب reviewer_id واحدٌ غيرُ فارغ في كلّ الصفوف (وُجد {sorted(ids)})"
            )
        reviewer = ids.pop()
        if reviewer in seen_reviewers:
            raise SystemExit(
                f"{sheet}: المراجع {reviewer!r} سبق في {seen_reviewers[reviewer]} — لا يُحتسب مرّتين"
            )
        seen_reviewers[reviewer] = sheet
        in_sheet = set()
        for row in rows:
            blind = row["blind_id"]
            meta = key.get(blind)
            if meta is None:
                raise SystemExit(f"{sheet}: معرّفٌ أعمى غير معروف {blind}")
            if blind in in_sheet:
                raise SystemExit(f"{sheet}: المقطع {blind} مكرّر في الورقة نفسها")
            in_sheet.add(blind)
            source = corpus[meta["sentence_id"]]
            if (row.get("sentence_id"), row.get(TEXT), row.get(FACTS)) != (
                meta["sentence_id"],
                source["text"],
                source["critical_facts"],
            ):
                raise SystemExit(
                    f"{sheet}: صفُّ {blind} لا يطابق النصَّ أو الحقائقَ الحرجة للجملة "
                    f"{meta['sentence_id']} في النصوص المُبصَّمة"
                )
            verdict = (row.get(CRIT) or "").strip()
            if verdict not in ("نعم", "لا"):
                continue  # غيرُ مُقيَّم
            reviewers_per_clip[blind].add(reviewer)
            e = per_engine[meta["engine"]]
            if verdict == "نعم":
                e["critical"].append(
                    {
                        "sentence": meta["sentence_id"],
                        "reviewer": reviewer,
                        "description": row.get("وصف الخطأ الحرج", ""),
                    }
                )
            for col, bucket in (("الوضوح (1-5)", "clarity"), ("الطبيعيّة (1-5)", "naturalness")):
                if (v := _rating(row.get(col), f"{sheet}: {blind} «{col}»")) is not None:
                    e[bucket].append(v)

    report = {"corpus_sha256": corpus_sha, "reviewers": sorted(seen_reviewers), "engines": {}}
    for engine in sorted({m["engine"] for m in key.values()}):
        e = per_engine[engine]
        clips = [b for b, m in key.items() if m["engine"] == engine]
        under = sum(1 for b in clips if len(reviewers_per_clip[b]) < args.min_reviewers)
        report["engines"][engine] = {
            "verdict": "REJECTED"
            if e["critical"]
            else "INCOMPLETE"
            if under
            else "PASSED_SAFETY_GATE",
            "clips": len(clips),
            "clips_under_min_reviewers": under,
            "critical_failures": e["critical"],
            "clarity_mean": round(statistics.mean(e["clarity"]), 2) if e["clarity"] else None,
            "naturalness_mean": round(statistics.mean(e["naturalness"]), 2)
            if e["naturalness"]
            else None,
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
