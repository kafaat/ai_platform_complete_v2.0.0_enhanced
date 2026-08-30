#!/usr/bin/env python3
"""`IMAGE-MANIFEST-WITHOUT-ITS-EVIDENCE-READS-AS-CLEAN-01` — البصماتُ الأربعُ تُفرَض.

بيانُ صور التشغيل يُنتَج في مسارٍ ويُستهلَك في آخر. فإن نقصته بصمةُ فحصٍ أو جردٍ أو
تحقّقٍ، فذلك يعني أنّ خطوةً **لم تُشغَّل** — لا أنّها مرّت. **وقراءةُ الناقص خُلوّاً هي
تحويلُ غيابِ البيانات إلى نجاح**، وهو الصنفُ الذي رفضه تقريرُ المختبر في OSV ثمّ لم
يُعمِّمه على بقيّة الأدوات.

**ولمَ حارسٌ مستقلٌّ لا تأكيدٌ داخل الـworkflow:** المتنُ الذي يُنتِج البصمات هو نفسُه
الذي كان سيتحقّق منها — **ومُنتِجٌ يشهد لنفسه ليس شاهداً**. وهذا الملفُّ يعمل في
مسارِ الاستهلاك، بلا شبكةٍ وبلا pytest، فيُكذَّب في ثوانٍ.

**وحدُّ صدقٍ يُقال صراحةً:** المفروضُ هنا **حضورُ البصمة وشكلُها**، لا أنّ الملفَّ
الذي تصفه سليمُ المحتوى. مطابقةُ البصمة بمحتواها تقع حين تُنزَّل المصنوعةُ نفسُها؛
وهذا الحارسُ يمنع **البيانَ الأعمى** لا الملفَّ الكاذب.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# الترميزُ يُضبَط عند التحميل لا داخل ``main`` — حارسٌ يموت وهو يطبع نجاحَه تحت
# ``LC_ALL=C`` عطلٌ وقع في هذا المستودع، وعلاجُه سطرٌ واحدٌ في الموضع الصحيح.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover — مجرًى غير قابل لإعادة الضبط
        pass

REQUIRED_EVIDENCE = (
    "scan_sha256",
    "sbom_sha256",
    "provenance_verification_sha256",
    "sbom_verification_sha256",
)

HEX = set("0123456789abcdef")


def _is_digest(value: Any) -> bool:
    """بصمةُ SHA-256 صغيرةُ الحروف بأربعٍ وستّين خانة — **والطولُ وحدَه لا يكفي**.

    ``len(x) == 64`` يقبل أربعاً وستّين محرفاً أيّاً كانت، وقد وقع هذا في مسار
    الترقية: ``test "${#TARGET_SHA}" = 40`` كان يقبل أربعين محرفاً غيرَ ستّ عشريّة.
    """
    return isinstance(value, str) and len(value) == 64 and all(c in HEX for c in value)


def failures(manifest: dict, tested_sha: str | None = None) -> list[str]:
    """دالّةٌ نقيّة — تُكذَّب مباشرةً بلا ملفّاتٍ ولا شبكة."""
    problems: list[str] = []

    images = manifest.get("images")
    if not isinstance(images, dict) or not images:
        return ["البيانُ بلا صور — `images` غائبةٌ أو فارغة، والخُضرةُ هنا «لم يُنظَر»"]

    if tested_sha:
        declared = manifest.get("source_sha")
        if declared != tested_sha:
            problems.append(
                f"البيانُ يصف لقطةً أخرى: `source_sha` = {declared!r} والمُختبَر {tested_sha!r} — "
                "دليلٌ من SHA آخر ليس دليلاً على هذه"
            )

    for service, row in sorted(images.items()):
        if not isinstance(row, dict):
            problems.append(f"{service}: الصفُّ ليس خريطة")
            continue

        image = row.get("image")
        if not isinstance(image, str) or "@sha256:" not in image:
            problems.append(
                f"{service}: المرجعُ ليس ببصمة ({image!r}) — **وسمٌ قد يُعاد توجيهه بين الفحص والترقية**"
            )

        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            problems.append(f"{service}: لا كتلةَ `evidence` — لم يُشغَّل الفحصُ ولا الجردُ ولا التحقّق")
            continue

        for key in REQUIRED_EVIDENCE:
            if key not in evidence:
                problems.append(f"{service}: بصمةٌ غائبة `{key}` — الخطوةُ لم تُشغَّل")
            elif not _is_digest(evidence[key]):
                problems.append(
                    f"{service}: بصمةٌ غيرُ صالحة `{key}` = {evidence[key]!r} "
                    "— ليست SHA-256 ستّ عشريّة بأربعٍ وستّين خانة"
                )

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tested-sha", default=None)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"path3_image_evidence_guard: البيانُ غير موجود: {args.manifest}\n"
            "**غيابُ الملفّ فشلٌ لا تخطٍّ** — يعني أنّ خطوةَ التنزيل لم تعمل.",
            file=sys.stderr,
        )
        return 1
    except json.JSONDecodeError as error:
        print(f"path3_image_evidence_guard: بيانٌ غيرُ صالح: {error}", file=sys.stderr)
        return 1

    problems = failures(manifest, args.tested_sha)
    if problems:
        print("path3_image_evidence_guard: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        print(
            "\nلا تُرقَّ صورةٌ ببيانٍ ناقص، ولا تُقرأ البصمةُ الغائبة «صفرَ ثغرات».",
            file=sys.stderr,
        )
        return 1

    count = len(manifest.get("images") or {})
    print(f"path3_image_evidence_guard_ok: {count} صورةً، ولكلٍّ بصماتُها الأربع")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
