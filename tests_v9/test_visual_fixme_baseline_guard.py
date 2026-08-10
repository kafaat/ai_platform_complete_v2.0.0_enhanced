"""`VISUAL-FIXME-DEBT-UNGUARDED-01` — الدَّين يُحرَس، ولا يُدَّعى أنّه أُغلِق.

**ولماذا هذا الحارس أصلاً:** `test.fixme` يجعل الاختبار **يُعَدّ ولا يُنفَّذ**. فتقرير
Playwright يقول `22 passed · 0 failed` صادقاً حرفيّاً وكاذباً دلاليّاً — اثنان من مسارات
القيمة لم يُقاسا. والخطر ليس الاثنين المُعلَنين بل الثالث الذي يُضاف بمبرّرٍ وجيه في
لحظته، والعاشر بعده.

**وحدّ صدقٍ يُقال هنا وفي الحارس:** هذا يحرس **تراكم** الدَّين لا يُغلِقه. إغلاقُ
الاختبارَين يحتاج تهيئة Terra Draw مستقرّةً بلا SwiftShader — قياسٌ بيئيّ لا نصّيّ.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "visual_fixme_baseline_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_visual_fixme_baseline_guard", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل {_SCRIPT} — صحّح المسار"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()

WATCHED = "frontend/e2e/maphub-webgl.spec.ts"
BASELINE_COUNT = MOD.BASELINE[WATCHED]["count"]


def _spec(count: int, *, anchor: bool = True) -> str:
    """ملفّ مواصفةٍ مُركَّب بعدد `fixme` مطلوب، مع شرحٍ يحمل المرساة أو بدونها."""
    blocks = []
    for index in range(count):
        note = (
            "// دَينٌ مُعلَن ومحروس: MAPHUB-WEBGL-VISUAL-DEBT-01"
            if anchor
            else "// معطَّلٌ لأنّ التهيئة لا تكتمل headless"
        )
        blocks.append(f"{note}\ntest.fixme('حالة {index} @visual', async () => {{}});")
    return "import { test } from '@playwright/test';\n\n" + "\n\n".join(blocks) + "\n"


def _run(text: str | None) -> list[str]:
    return MOD.violations({WATCHED: text})


def test_the_declared_baseline_passes():
    """المرساة المقابلة: بلا هذا قد تمرّ كلّ التكذيبات لأنّ الحارس يرفض دائماً."""
    assert _run(_spec(BASELINE_COUNT)) == []


def test_the_repository_itself_is_at_its_baseline():
    """**والأساس يُقاس على الشجرة الحقيقيّة لا على معطياتٍ مُركَّبة وحدها.**

    اختبارٌ يعمل على نصوصٍ مُصطنَعة فقط يبقى أخضر بينما الملفّ الحقيقيّ انزلق — وهو
    بعينه «حارسٌ أخضر لأنّه لا ينظر إلى ما وُجِد له».
    """
    assert MOD.main([]) == 0


def test_one_more_fixme_is_blocked():
    """**البند الأوّل: الزيادة حاجزة.**

    ثالثٌ يُضاف بمبرّرٍ وجيه في لحظته هو الآليّة التي تُنتِج مقبرة الديون. والقرار
    يجب أن يكون صريحاً (رفع الأساس بـ`why` مكتوب) لا انزلاقاً صامتاً.
    """
    problems = _run(_spec(BASELINE_COUNT + 1))
    assert problems, "زيادةٌ عن خطّ الأساس مرّت — الراتشِت لا يحجب"
    assert any("دَينٌ جديد" in line for line in problems)


def test_removing_a_fixme_without_lowering_the_baseline_is_blocked():
    """**البند الثاني: النقصان مخالفةٌ كالزيادة — وهذا هو غير البديهيّ.**

    سقفٌ يبقى `2` بعد إغلاق أحد الاختبارين يبتلع **عودة** الدَّين صامتاً: يُغلَق واحد
    ثمّ يُضاف آخر فيبقى العدّاد `2` والحارس أخضر. الراتشِت الذي ينزل ولا يُحدَّث ليس
    راتشِتاً بل سقفٌ مُرتخٍ — نمطُ أرضيّة التغطية نفسه (20 → 40 → 42 → 43).
    """
    problems = _run(_spec(BASELINE_COUNT - 1))
    assert problems, "نقصانٌ بلا خفض الأساس مرّ — السقف مُرتخٍ"
    assert any("اخفِض" in line for line in problems)


def test_a_fixme_without_a_gap_anchor_is_blocked():
    """**البند الثالث: عددٌ بلا سببٍ يُنقَل بين الأجيال بلا معنى.**

    «اثنان» لا يقول لماذا ولا متى يُغلَقان. والمرساة تجعل الدَّين قابلاً للتتبّع بدل أن
    يصير رقماً يرثه من لا يعرف قصّته.
    """
    problems = _run(_spec(BASELINE_COUNT, anchor=False))
    assert problems, "fixme بلا مرساة مرّ — الدَّين بلا سبب"
    assert any("بلا مرساة" in line for line in problems)


def test_a_missing_watched_file_fails_closed():
    """مسارٌ نُقِل أو حُذِف بلا تحديث الأساس ⇒ الحارس يحرس لا شيء.

    وهي الحالة التي تجعل حارساً «أخضرَ إلى الأبد»: لا ملفّ ⇒ لا `fixme` ⇒ لا مخالفة.
    فالغياب فشلٌ مُسمّى لا سكوت.
    """
    problems = _run(None)
    assert problems, "ملفٌّ غائب مرّ — الحارس يحرس لا شيء وهو أخضر"
    assert any("غير موجود" in line for line in problems)


def test_a_mention_in_prose_is_not_counted_as_a_disabled_test():
    """**يُقاس ما يُنفَّذ لا ما يُذكَر — وهذا عطلٌ وقع فعلاً في أوّل صياغة.**

    طابقت الصياغة الأولى الاسمَ وحده فعدَّت **شرحاً** يذكر `test.fixme` اختباراً
    مُعطَّلاً: أربعة بدل اثنين في الملفّ الحقيقيّ. وعدٌّ يُعاقِب التوثيق يُدرِّب كاتبه
    على حذفه — فالضرر مضاعف: رقمٌ خاطئ وتوثيقٌ أقلّ.
    """
    prose = (
        "// يتبقّى مُخطَّطان (test.fixme @visual) — شرحٌ لا إعلان\n"
        "// والمذكوران test.fixme أدناه محروسان\n"
        "// دَينٌ مُعلَن ومحروس: MAPHUB-WEBGL-VISUAL-DEBT-01\n"
        "test.fixme('واحدٌ حقيقيّ @visual', async () => {});\n"
    )
    assert MOD.count_fixmes(prose) == [4]

    # **والحالة التي أمسكتها الطفرة:** إعلانٌ كاملُ الصيغة داخل تعليق. صيغةُ النداء
    # وحدها تُطابِقه، فلولا استبعاد التعليقات لعُدَّ اختباراً قائماً — ولأُلزِم من علّق
    # سطراً برفع خطّ الأساس لاختبارٍ **غير موجود**. وهذا أسوأ من العدّ الزائد: راتشِتٌ
    # يُرفَع لدَينٍ وهميّ يفقد معناه.
    commented_out = (
        "// MAPHUB-WEBGL-VISUAL-DEBT-01\n"
        "// test.fixme('مُعطَّلٌ ومُعلَّق معاً', async () => {});\n"
        "/* test.fixme('وفي كتلة تعليق', async () => {}); */\n"
        "test.fixme('القائم وحده', async () => {});\n"
    )
    assert MOD.count_fixmes(commented_out) == [4]


@pytest.mark.parametrize(
    "declaration",
    [
        "test.fixme('س', async () => {});",
        "test.describe.fixme('س', () => {});",
        "test.fixme.only('س', async () => {});",
        "  test.fixme ('س', async () => {});",
    ],
)
def test_every_disabling_form_is_counted(declaration):
    """أشكال التعطيل كلّها تُعَدّ — وإلّا صار الالتفاف على الراتشِت تغييرَ صيغة.

    `test.describe.fixme` يُعطّل **كتلةً** كاملة، فهو أشدّ من الفرديّ لا أخفّ.
    """
    text = "// MAPHUB-WEBGL-VISUAL-DEBT-01\n" + declaration + "\n"
    assert MOD.count_fixmes(text) == [2], f"شكلٌ غير معدود: {declaration!r}"


def test_the_honesty_limit_is_written_down():
    """حدُّ المدى مكتوبٌ في الحارس نفسه لا في مراجعةٍ تُنسى.

    من يقرأ خضرة هذا الحارس يجب أن يعرف أنّها تعني «لم يتراكم»، لا «أُغلِق الدَّين».
    """
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "لا يُغلِقه" in body
    assert "SwiftShader" in body
