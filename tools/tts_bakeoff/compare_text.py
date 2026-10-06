"""يقارن النصَّ الخام بالنصّ المحوَّل مقابل **فحوص الحقائق المعلنة** — قبل أيّ توليد صوت.

    <venv فيه المحوّلات>/bin/python compare_text.py --out text-001

خطوط المعالجة:
  • raw                 — النصّ كما هو (يُرسَل للمحرّك دون تحويل).
  • arabic_tts_frontend — ``normalise(text).tts`` من الحزمة بنسختها المثبّتة.
  • num2words_naive     — غلافٌ ساذج **كتبناه هنا** يستبدل كلّ رقم بـ``num2words(..., lang="ar")``؛ ليس منتجاً
                          قائماً بل تمثيلٌ لِما يفعله تكاملٌ مباشر بالمكتبة.
يُحفظ لكلّ جملة: النصُّ الداخل والخارج، وأخطاءُ الفحوص المعلنة (``semantic.check``)، والمحتوى الذي لم
تُغطِّه أيُّ حقيقة (``semantic.coverage``). «اجتاز» يعني **اجتاز الفحوص المعلنة** — لا «المعنى محفوظ». ويُحفظ إصدارُ كلّ حزمة
وبصماتُ النصوص والحقائق والمحلّل وهذا السكربت، فتُعاد النتيجة أو يُكشف ما تغيّر.

ولا يُستنتج منه ما **يسمعه** المستخدم: النصُّ ليس الصوت؛ ذلك يحتاج توليداً واستماعاً فعليّين.

حدودُه: المحلّلُ لا يرى النحو — «خمسون كيلوجراماً» (صوابها خمسين) و«ثلاثة ساعات» (صوابها ثلاث) تمرّان لأنّ
القيمة والوحدة محفوظتان. الحكمُ على النحو والنطق للمراجع البشريّ، وعلى الصوت لجولة التقييم الأعمى.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from importlib import metadata
from pathlib import Path

import semantic
from semantic import HERE

PINNED = {"arabic-tts-frontend": "0.1.0", "num2words": "0.5.14"}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pipelines() -> dict:
    found = {}
    for dist in PINNED:
        try:
            found[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            found[dist] = None
    out = {"raw": (lambda t: t, {"package": None})}
    if found["arabic-tts-frontend"] == PINNED["arabic-tts-frontend"]:
        from arabic_tts_frontend import normalise

        out["arabic_tts_frontend"] = (
            lambda t: normalise(t).tts,
            {
                "package": "arabic-tts-frontend",
                "version": found["arabic-tts-frontend"],
                "call": "normalise(text).tts",
            },
        )
    if found["num2words"] == PINNED["num2words"]:
        from num2words import num2words

        def n2w(text: str) -> str:
            return re.sub(
                r"\d+(?:\.\d+)?",
                lambda m: num2words(
                    float(m.group()) if "." in m.group() else int(m.group()), lang="ar"
                ),
                text.translate(_DIGITS),
            )

        out["num2words_naive"] = (
            n2w,
            {
                "package": "num2words",
                "version": found["num2words"],
                "call": "re.sub(digits → num2words(n, lang='ar')) — غلافٌ محلّيّ",
            },
        )
    return out, found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--corpus", default=str(HERE / "corpus.tsv"))
    ap.add_argument("--facts", default=str(HERE / "semantic_facts.json"))
    ap.add_argument("--require-all", action="store_true", help="افشل إن غاب محوّلٌ بنسخته المثبّتة")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        print(f"مرفوض: {out} موجود — كلّ مقارنةٍ في مجلّدٍ جديد", file=sys.stderr)
        return 5
    corpus_path, facts_path = Path(args.corpus), Path(args.facts)
    with corpus_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    facts = semantic.load_facts(facts_path)
    missing = {r["id"] for r in rows} ^ set(facts)
    if missing:
        print(f"مرفوض: الحقائق والنصوص لا تتطابق في المعرّفات {sorted(missing)}", file=sys.stderr)
        return 3

    pipes, versions = pipelines()
    absent = [d for d, v in PINNED.items() if versions[d] != v]
    if absent and args.require_all:
        print(f"مرفوض: نسخٌ غير مثبّتة أو غائبة {versions} والمطلوب {PINNED}", file=sys.stderr)
        return 4

    report = {
        "kind": "text-level declared-facts check — not audio, not engine output; passing ≠ meaning preserved",
        "stopwords_not_counted_as_uncovered": sorted(semantic.STOP),
        "corpus_sha256": _sha(corpus_path),
        "facts_sha256": _sha(facts_path),
        "semantic_py_sha256": _sha(HERE / "semantic.py"),
        "compare_text_py_sha256": _sha(Path(__file__)),
        "python": sys.version.split()[0],
        "versions_found": versions,
        "versions_pinned": PINNED,
        "skipped_pipelines": absent,
        "pipelines": {},
        "sentences": {},
    }
    for name, (fn, meta) in pipes.items():
        failed, review, uncovered_total = [], [], 0
        for r in rows:
            sid = r["id"]
            try:
                converted = fn(r["text"])
                v = semantic.verdict(converted, facts[sid])
            except Exception as exc:  # المحوّلُ الذي ينهار على جملةٍ خطأٌ لا تخطٍّ
                converted = None
                v = {
                    "status": "FAILED_DECLARED_CHECKS",
                    "errors": [f"انهار المحوّل: {type(exc).__name__}: {exc}"],
                    "uncovered_content": [],
                }
            errors, uncovered = v["errors"], v["uncovered_content"]
            report["sentences"].setdefault(sid, {"text": r["text"]})[name] = {
                "output": converted,
                "changed": converted != r["text"],
                "status": v["status"],
                "errors": errors,
                "uncovered_content": uncovered,
                "quantity_mapping": semantic.quantity_mapping(r["text"], converted)
                if converted is not None
                else [],
            }
            uncovered_total += len(uncovered)
            if v["status"] == "REVIEW_UNCOVERED_CONTENT":
                review.append(sid)
            if errors:
                failed.append(sid)
        report["pipelines"][name] = meta | {
            "sentences": len(rows),
            "passed_declared_checks": len(rows) - len(failed) - len(review),
            "review_uncovered_content": review,
            "failed_ids": failed,
            "uncovered_tokens_total": uncovered_total,
        }
    out.mkdir(parents=True)
    (out / "text_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, p in report["pipelines"].items():
        print(
            f"{name:20} {p['passed_declared_checks']}/{p['sentences']} اجتازت الفحوص المعلنة · "
            f"للمراجعة (محتوى غيرُ مغطّى): {p['review_uncovered_content'] or '—'} · فشل: {p['failed_ids'] or '—'}"
        )
    if absent:
        print(f"تنبيه: لم يُقَس {absent} (النسخة الموجودة {versions})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
