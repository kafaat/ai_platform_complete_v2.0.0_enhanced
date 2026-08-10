#!/usr/bin/env python3
"""الاختبار المُعطَّل دَينٌ — والدَّينُ يُحرَس أو يتراكم صامتاً.

``VISUAL-FIXME-DEBT-UNGUARDED-01``

**العطل الذي يحرسه:** ``test.fixme`` يجعل الاختبار **يُعَدّ ولا يُنفَّذ**. فتقرير
Playwright يقول ``22 passed · 0 failed`` وهو صادق حرفيّاً وكاذبٌ دلاليّاً: اثنان من
مسارات القيمة لم يُقاسا أصلاً. ولا شيء في الشجرة يمنع أن يصير الاثنان ثلاثةً ثمّ عشرة —
كلّ واحدٍ منها بمبرّرٍ وجيه في لحظته، والمجموع مقبرةُ ديون خضراء.

**والعلاج ليس نزع ``fixme`` ليخضرّ CI:** ذلك تزييفُ إغلاق. العلاج أن تكون الزيادة
**حاجزة**: خطٌّ أساس مُعلَن، وكلّ تجاوزٍ له قرارٌ صريح لا انزلاق.

**وثلاثة بنودٍ لا واحد:**

1. **العدد لا يزيد عن خطّ الأساس** — راتشِت ينزل ولا يصعد (نمطُ أرضيّة التغطية نفسه).
2. **العدد لا يقلّ عنه بلا تحديث** — ``fixme`` أُزيل والأساس باقٍ يعني سقفاً مُرتخياً
   يبتلع عودة الدَّين صامتاً. فالنقصان يفشل برسالةٍ تطلب **خفض** الأساس.
3. **كلّ ``fixme`` يحمل سبباً ومرساةَ فجوة** — عددٌ بلا أسباب يقول «اثنان» ولا يقول
   «لماذا» ولا «متى يُغلَقان»، فيصير الأساس رقماً يُنقَل بين الأجيال بلا معنى.

**وحدّ صدق:** هذا يحرس **تراكم** الدَّين لا يُغلِقه. الاختباران المُعطَّلان يبقيان
دَيناً مفتوحاً — وإغلاقُهما يحتاج تهيئة Terra Draw مستقرّةً بلا SwiftShader، وهو قياسٌ
بيئيّ لا نصّيّ. وما يمنعه هذا الملفّ: أن يُضاف ثالثٌ بلا مُحاكَمة.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: خطّ الأساس المُعلَن — بالمسار، لأنّ «ملفّان بواحدٍ» غير «ملفٌّ باثنين».
#: **راتشِت:** يُخفَّض عند إغلاق دَين، ولا يُرفَع إلّا بمُحاكَمة مكتوبة في `why`.
BASELINE: dict[str, dict] = {
    "frontend/e2e/maphub-webgl.spec.ts": {
        "count": 2,
        "why": (
            "رسم المضلّع (measure-area) ورسم الخطّ (measure-length) عبر مؤشّر حقيقيّ: "
            "تهيئة Terra Draw لا تكتمل تحت SwiftShader headless (data-draw-ready لا يُرفَع). "
            "مسار القيمة نفسه محروسٌ حتميّاً في frontend/src/lib/measureDrawWiring.test.ts."
        ),
        "gap": "MAPHUB-WEBGL-VISUAL-DEBT-01",
    },
}

#: `test.fixme(` بأشكاله — بما فيها `test.fixme.only`/`test.describe.fixme`.
#: **وصيغة النداء شرطٌ لا زينة:** أوّل صياغةٍ طابقت الاسم وحده فعدَّت **ذِكرَه في شرحٍ**
#: اختباراً مُعطَّلاً (أربعة بدل اثنين في هذا الملفّ بعينه). وعدٌّ يُعاقِب التوثيق يُدرِّب
#: كاتبه على حذفه — فيُقاس ما يُنفَّذ: اسمٌ يتبعه قوس.
_FIXME_RE = re.compile(r"\btest(?:\.describe)?\.fixme(?:\.only)?\s*\(")

#: سطرٌ يبدأ بتعليق (بعد الفراغ البادئ) لا يُعلِن اختباراً مهما حمل من نصّ.
_COMMENT_RE = re.compile(r"\A\s*(?://|/?\*)")

#: المرساة المطلوبة قرب كلّ `fixme`: معرّف فجوة أو رقم قضيّة. عددٌ بلا سببٍ لا يُغلَق.
_ANCHOR_RE = re.compile(r"(?:[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+-\d+|#\d+)")

#: كم سطراً قبل السطر يُعَدّ «شرحاً مصاحباً». التعليقات في هذا المستودع مُسهَبة عمداً.
_CONTEXT_LINES = 14


def count_fixmes(text: str) -> list[int]:
    """أرقام الأسطر (1-based) التي تحمل `test.fixme`."""
    return [
        i
        for i, line in enumerate(text.splitlines(), 1)
        if _FIXME_RE.search(line) and not _COMMENT_RE.match(line)
    ]


def _has_anchor(lines: list[str], line_number: int) -> bool:
    """هل يحمل الشرحُ المصاحب مرساةَ فجوة/قضيّة؟"""
    start = max(0, line_number - 1 - _CONTEXT_LINES)
    window = "\n".join(lines[start:line_number])
    return bool(_ANCHOR_RE.search(window))


def violations(read: dict[str, str | None]) -> list[str]:
    """المخالفات — والنقصان مخالفةٌ كالزيادة.

    ``read`` يربط المسار بمحتواه، أو ``None`` إن كان الملفّ غائباً. وغيابُ ملفٍّ مُدرَجٍ
    في الأساس مخالفةٌ لا سكوت: مسارٌ نُقِل بلا تحديث الأساس يجعل الحارس يحرس لا شيء.
    """
    found: list[str] = []

    for path, expected in sorted(BASELINE.items()):
        text = read.get(path)
        if text is None:
            found.append(
                f"{path}: مُدرَجٌ في خطّ الأساس وغير موجود — "
                "مسارٌ نُقِل أو حُذِف بلا تحديث الأساس يجعل الحارس يحرس لا شيء."
            )
            continue

        lines = text.splitlines()
        positions = count_fixmes(text)
        limit = expected["count"]

        if len(positions) > limit:
            found.append(
                f"{path}: {len(positions)} × test.fixme والأساس {limit} — "
                f"دَينٌ جديد بلا مُحاكَمة (الأسطر: {positions}). "
                "إمّا يُغلَق الاختبار، وإمّا يُرفَع الأساس بقرارٍ مكتوب في BASELINE['why']."
            )
        elif len(positions) < limit:
            found.append(
                f"{path}: {len(positions)} × test.fixme والأساس {limit} — "
                "أُغلِق دَينٌ ولم يُخفَّض الأساس. سقفٌ مُرتخٍ يبتلع عودته صامتاً؛ "
                f"اخفِض BASELINE['{path}']['count'] إلى {len(positions)}."
            )

        for line_number in positions:
            if not _has_anchor(lines, line_number):
                found.append(
                    f"{path}:{line_number}: test.fixme بلا مرساة فجوة/قضيّة في "
                    f"الأسطر الـ{_CONTEXT_LINES} السابقة — "
                    "عددٌ بلا سببٍ يُنقَل بين الأجيال بلا معنى. "
                    "أضِف معرّف فجوة (مثل ABC-DEF-01) أو رقم قضيّة (#123) في الشرح."
                )

    return found


def _read(root: Path) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for path in BASELINE:
        target = root / path
        out[path] = target.read_text(encoding="utf-8") if target.is_file() else None
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="جذر الشجرة المفحوصة")
    args = parser.parse_args(argv)

    problems = violations(_read(args.root))
    if problems:
        print("visual_fixme_baseline_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(
            "\nالدَّين يُحرَس ولا يُزوَّر إغلاقُه: نزعُ fixme ليخضرّ CI بلا استقرار "
            "التهيئة headless يُنتِج اختباراً هشّاً — وهو أسوأ من دَينٍ مُعلَن."
        )
        return 1

    total = sum(item["count"] for item in BASELINE.values())
    print(
        f"visual_fixme_baseline_guard: PASS "
        f"({len(BASELINE)} ملفّاً مُراقَباً · {total} × test.fixme عند خطّ الأساس، لكلٍّ سببٌ ومرساة)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
