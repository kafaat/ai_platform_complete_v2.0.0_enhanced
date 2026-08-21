"""سقفُ *Unit Tests* يبقى فوق أبطأ قياسٍ حقيقيّ — ``MUT-SWEEP-TIMEOUT-01``.

**العطلُ المقيس، لا المتوقَّع:** على #882 أنهت الوظيفةُ عند ٥٩:٠٢ مقابل سقف ٦٠ —
مرّت بـ**٥٨ ثانية**. والأساسُ على ``1cb3f278`` كان ٤٦:٠٦. والسببُ مقيس: السجلّ
انتقل من ٣٨٤ إلى ٤٠١ طفرةً مُعلَنة، و``MUT-PRE0`` فوقها فعّلت ٨ مواصفاتٍ كانت
محسوبةً في ٣٨٤ **ولا تُشغَّل قطّ** — أي ~٢٥ دورةَ زرعٍ↔pytest↔ردٍّ إضافيّة.

**ولماذا حارسٌ لا مجرّد رفعِ سقف:** رفعُ السقف وحده يشتري وقتاً ولا يُبقي أحداً
على علم. فالنموّ التالي كان سيُكتشَف بعد **حرقِ تسعين دقيقة** في CI ثمّ انتظارِ
تشخيص — وهو أغلى صنفِ اكتشاف. هذا الملفّ يجعله يحمرّ في ثوانٍ، محلّيّاً، قبل الدفع.

**وحدُّ صدقٍ يُقال صراحةً:** لا يُقاس هنا زمنٌ ولا يُحاكى عدّاء. يُقاس **بديلٌ**
(عددُ الطفرات المُعلَنة) لأنّه المحرّك المهيمن المقيس — لا لأنّه الزمن. فحين يحمرّ،
الواجبُ إعادةُ قياسٍ حقيقيّة، لا تحريكُ الرقم حتّى يخضرّ.

**والعلاجُ البنيويّ ليس هنا:** نقلُ المكنسة إلى وظيفةٍ مستقلّة هو الحدّ الصحيح —
ويلزمه إضافةُ اسمِ الوظيفة الجديدة إلى الفحوص المطلوبة في الـRuleset، وإلّا صارت
المكنسةُ إرشاديّةً **صامتاً**. وذلك إعدادٌ خارج المستودع لا يُفرَض من ملفٍّ فيه.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
REGISTRY = ROOT / "docs/architecture/guard_mutation_registry.json"

#: أبطأُ قياسٍ حقيقيّ (دقائق) وقتَ كتابة هذا العقد — تشغيل #882، وظيفة *Unit Tests*.
MEASURED_SLOWEST_MINUTES = 59.0

#: عددُ الطفرات المُعلَنة عند ذلك القياس.
MEASURED_MUTATIONS = 401

#: علامةُ الماء: تجاوزُها يوجب إعادةَ قياسٍ حقيقيّة قبل الدفع. اشتُقّت من الهامش
#: المتاح (٩٠ − ٥٩ = ٣١ دقيقة) بتقديرٍ **متحفّظ** لكلفة الطفرة الواحدة، لا بنموذجٍ
#: مضبوط — والتحفّظ مقصود: أن يحمرّ باكراً أرخص من أن يحمرّ بعد حرقِ تسعين دقيقة.
MUTATION_WATERMARK = 441


def _declared_mutations() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    total = 0
    for section in ("mutated", "behavioural"):
        for spec in (registry.get(section) or {}).values():
            if isinstance(spec, dict):
                total += len(spec.get("mutations") or [])
    return total


def _unit_tests_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow.get("jobs") or {}
    job = jobs.get("unit-tests")
    assert job is not None, "وظيفة `unit-tests` اختفت من ci.yml — العقد يشير إلى لا شيء."
    return job


def test_the_unit_tests_ceiling_stays_above_the_slowest_measured_run():
    """**القيمةُ المقرَّرة ليست هنا** — قفلُها الوحيد في ``test_ci_pipeline_settings``.

    أوّلُ صياغةٍ لهذا الملفّ أكّدت ``timeout-minutes == 90`` أيضاً، فصار للحقيقةِ
    الواحدةِ سلطتان. وذلك يمرّ أخضرَ اليوم ويتباعد غداً: يُحدَّث أحدُهما فيُقرَأ
    الآخرُ عقداً قائماً وهو بائت — وهو صنفُ العطل الذي يطارده هذا المستودع نفسه.

    فالمقيسُ هنا **العلاقة** لا القيمة: أيّاً كان المقرَّر، يجب أن يعلو أبطأ قياسٍ
    حقيقيّ. تكذيبُه بخفضِ السقف تحت ٥٩.٠ يبقى قائماً، ولا يُكرَّر الرقمُ المقرَّر.
    """
    declared = _unit_tests_job().get("timeout-minutes")
    assert isinstance(declared, int), f"`timeout-minutes` = {declared!r} ليس عدداً."
    assert declared > MEASURED_SLOWEST_MINUTES, (
        f"السقف {declared} لا يعلو أبطأ قياسٍ حقيقيّ {MEASURED_SLOWEST_MINUTES} "
        "دقيقة (#882) — سقفٌ أضيق من الواقع يصنع فشلاً زائفاً، ويُقرَأ عطلاً في "
        "الاختبارات لا ضيقاً في السقف فيُشخَّص في الاتّجاه الخطأ."
    )


def test_the_sweep_has_not_grown_past_the_point_that_was_measured():
    """المحرّكُ المهيمن مقيس: كلُّ طفرةٍ دورةُ زرعٍ↔pytest↔ردّ على المسار الحرج."""
    declared = _declared_mutations()
    assert declared <= MUTATION_WATERMARK, (
        f"الطفراتُ المُعلَنة {declared} تجاوزت علامةَ الماء {MUTATION_WATERMARK} "
        f"(كانت {MEASURED_MUTATIONS} عند قياسِ {MEASURED_SLOWEST_MINUTES} دقيقة).\n"
        "أعِد قياساً حقيقيّاً لزمن *Unit Tests*، ثمّ إمّا انقل المكنسة إلى وظيفةٍ "
        "مستقلّة **بعد** إضافة اسمها إلى الفحوص المطلوبة في الـRuleset، أو أعِد "
        "تبرير السقف بالرقم الجديد. لا تُحرِّك هذا الثابت حتّى يخضرّ."
    )


def test_the_sweep_still_runs_inside_the_job_the_ruleset_actually_requires():
    """نقلُها بلا ضبط القفل يجعلها إرشاديّةً صامتاً — **والقيدُ مقيسٌ لا مُفترَض.**

    القائمةُ المطلوبة في حماية الفرع مُدوَّنةٌ في
    ``test_check_names_survive_the_slice_and_unit_tests_is_a_singleton``: أربعةَ
    عشرَ اسماً حرفيّاً، مقروءةً من سجلّ ``branch_protection_contract_guard`` —
    و**``Unit Tests`` منها**. فوظيفةٌ جديدة باسمٍ جديد ليست فيها، ونقلُ المكنسة
    إليها يُخرِجها من الحجب **بلا أن يحمرّ شيء**.

    و``branch_protection_contract_guard`` نفسه لا يُعدّد الفحوصَ بالاسم (يفرض حلَّ
    المحادثات وحده)، فلا شيءَ في الشجرة يمنع ذلك الخروج. فيبقى التأكيدُ هنا: ما دامت
    المكنسةُ في *Unit Tests* فهي محكومةٌ بما يحكم اسماً **في القائمة فعلاً**.
    """
    steps = _unit_tests_job().get("steps") or []
    runs = [str(s.get("run") or "") for s in steps if isinstance(s, dict)]
    assert any("guard_mutation_guard.py --run" in r for r in runs), (
        "مكنسةُ الطفرات لم تعد خطوةً في *Unit Tests*. إن نُقِلت عمداً فتأكّد أنّ اسم "
        "الوظيفة الجديدة أُضيف إلى الفحوص المطلوبة في الـRuleset، ثمّ حدّث هذا العقد — "
        "وإلّا فقد كفّت عن الحجب بلا أن تحمرّ."
    )
