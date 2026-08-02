#!/usr/bin/env python3
"""يمسك الفشل الصامت الذي يتركه دمج `union` — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.

`merge=union` يحلّ تعارض الملفّات الإلحاقيّة بضمّ سطور الجانبين بدل ترك العلامات.
وهو صحيح حين يُضيف كلّ جانب **مدخلاً مختلفاً**. لكن حين يُحرّر الجانبان **نفس السطر**
— وهو بالضبط ما يحدث حين تُحدّث جلستان حالة الفجوة نفسها — يُبقي union الاثنين
و**يخرج بـ0**:

    ## GAP-A — هبطت على main في abc1234
    ## GAP-A — مُغلقة بالجلسة الأخرى        ← حالتان متناقضتان، وgit يقول «نجح»

مقيس في مستودع مؤقّت، لا مفترَض. فالفشل صامت: لا علامة تعارض يمسكها
`conflict_marker_guard`، ولا خطأ نحويّ، ولا اختبار يسقط — فقط سجلّ يقول شيئين
متناقضين عن الفجوة نفسها. ولهذا يسبق هذا الحارس تفعيل union، لا يتبعه.

**والتصميم صُحِّح بالقياس مرّتين قبل أن يُكتَب:**

① **الهويّة لا النصّ.** مقارنة عناوين حرفيّاً تفوت الحالة الخطرة تماماً: العنوانان
   أعلاه مختلفان نصّاً، متطابقان هويّةً. المقارنة على **معرّف الفجوة** وحده.

② **والتلاصق لا التكرار.** أوّل تصميم كان «معرّف يتكرّر ⇒ فشل». تشغيله على الشجرة
   أعطى **١١** إصابة، **عشرٌ منها شرعيّة**: السجلّ يحتفظ عمداً بسلاسل تاريخيّة
   (`SILENT-EXCEPTION-HANDLERS-11-01` ثلاث مرّات بثلاث حالات مؤرَّخة،
   و`SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01` بمدخل موسوم «أُبقي للمصدر»). حارسٌ
   يرفع عشرة إنذارات كاذبة يُعطَّل في أوّل يوم — وهو عطل الحارس الأكثر شيوعاً في هذا
   المستودع، مسجَّل مراراً.

   بصمة فساد union **بنيويّة ومميِّزة**: العنوانان **متلاصقان** (سطران متتاليان بلا
   متن بينهما)، لأنّ union يضمّ نسختَي **السطر الواحد**. والسلسلة التاريخيّة الشرعيّة
   يفصلها متن دائماً. المقيس على الشجرة: **١ من ١١** متلاصق — وهي إصابة حقيقيّة
   موجودة أصلاً (`BRANCH-GRAVEYARD-POLICY`)، أي أنّ الحارس وجد فساداً قائماً قبل أن
   يُوصَل.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard` و`brain_commit_claim_guard`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# الملفّات الأربعة المقيسة بوصفها إلحاقيّة ومتعدّدة الكتّاب: 89 + 77 + 75 + 32 =
# **٢٧٣ من ٢٨١** لمسة على `sahool-brain/` منذ 2026-07-01. وهي نفسها المسارات التي
# يشملها `merge=union` في `.gitattributes` — الشبكة والحارس على **نفس النطاق** عمداً،
# فبقعةٌ يضمّها union ولا يفحصها الحارس هي بالضبط الثغرة التي وُجِد ليسدّها.
#
# ليست glob: `sahool-brain/**/*.md` يشمل رنبوكات ووثائق ليست إلحاقيّة، فيصير الحارس
# يحكم على ملفّات لم تُقَس. المقيس اليوم: registry=99 عنواناً بمعرّف · ledger=11 ·
# log=2 · hot=0 — والأربعة نظيفة من التلاصق بعد إصلاح `BRANCH-GRAVEYARD-POLICY`.
DEFAULT_TARGETS = (
    "sahool-brain/gaps/registry.md",
    "sahool-brain/hot.md",
    "sahool-brain/log.md",
    "sahool-brain/decisions/ledger.md",
)

# معرّف فجوة: مقطعان كبيران فأكثر بشرطات، في **بداية عنوان `## `**.
# `^##` مع `re.M` مرساة أساسيّة: ذكرُ معرّف داخل فقرة ليس إعلان حالة، ومطابقته
# تُنتج نفس صنف الإيجابيّ الكاذب الذي أسقط `CONFLICT_RE` غير المُرسى في #768.
HEADING_RE = re.compile(
    r"^##\s+(?P<gap_id>[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)+)\b",
)

_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _strip_fenced_blocks(lines: list[str]) -> list[str | None]:
    """يُعيد الأسطر مع `None` مكان ما هو داخل كتلة كود.

    عنوانٌ داخل ``` مثالٌ في وثيقة لا سجلّ — وهذا الملفّ **يشرح** الحارس بأمثلة،
    فبلا هذا الاستبعاد يُطلِق الحارس على توثيقه لنفسه.
    """
    out: list[str | None] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(None)
            continue
        out.append(None if in_fence else line)
    return out


def adjacent_duplicate_identities(text: str) -> list[tuple[str, int, int]]:
    """عناوين متلاصقة تحمل نفس معرّف الفجوة: (المعرّف، سطر الأوّل، سطر الثاني).

    «متلاصقان» = سطران متتاليان **كلاهما عنوان** لنفس المعرّف. هذا هو ما ينتجه
    union حين يضمّ نسختَي سطر واحد؛ والسلسلة التاريخيّة يفصلها متن فتمرّ.
    """
    # `splitlines()` يتولّى CRLF وLF معاً، فلا حاجة لتطبيع منفصل.
    lines = _strip_fenced_blocks(text.splitlines())
    ids: list[str | None] = []
    for line in lines:
        if line is None:
            ids.append(None)
            continue
        m = HEADING_RE.match(line)
        ids.append(m.group("gap_id") if m else None)

    found: list[tuple[str, int, int]] = []
    for i in range(len(ids) - 1):
        if ids[i] is not None and ids[i] == ids[i + 1]:
            found.append((ids[i], i + 1, i + 2))  # أسطر 1-based
    return found


def check(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if not path.exists():
            problems.append(f"هدف مفقود: {path.relative_to(ROOT)}")
            continue
        rel = path.relative_to(ROOT).as_posix()
        for gap_id, first, second in adjacent_duplicate_identities(
            path.read_text(encoding="utf-8")
        ):
            problems.append(f"duplicate gap identity: {gap_id}\n  {rel}:{first}\n  {rel}:{second}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "targets",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="مسارات نسبيّة للجذر (الافتراضيّ: سجلّ الفجوات)",
    )
    args = parser.parse_args()

    problems = check([ROOT / t for t in args.targets])
    if problems:
        print("عناوين متلاصقة تحمل نفس هويّة الفجوة — بصمة دمج union على سطر واحد:")
        for line in problems:
            print(f"  ✗ {line}")
        print(
            "\nالعلاج: ادمج العنوانين في مدخل واحد يحفظ نصّيهما، أو افصلهما بمتن إن\n"
            "كانا حالتين تاريخيّتين مختلفتين. لا تحذف أحدهما بلا قراءة — الجانبان\n"
            "جاءا من جلستين، وحذف أحدهما يمحو عمل جلسة."
        )
        return 1

    print("brain_duplicate_gap_identity_guard: PASS (لا عناوين متلاصقة متطابقة الهويّة)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
