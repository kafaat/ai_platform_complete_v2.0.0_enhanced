"""بوّابةُ الأثر تقرأ متنَ الـPR حيّاً — لا حمولةَ الحدث المجمَّدة.

`GATE-READS-A-FROZEN-EVENT-PAYLOAD-NOT-THE-LIVE-BODY-01` — مقيس على #887:
`github.event.pull_request.body` يتجمّد لحظةَ الحدث، فتصحيحُ المتن بعد انطلاق
التشغيل غيرُ مرئيّ، و«أعد التشغيل» يكرّر الحمولةَ القديمة لأنّ `edited` ليست
من أنواع `pull_request` الافتراضيّة. الحلُّ المؤقّت كان إغلاقَ الـPR وإعادةَ
فتحه؛ والإصلاحُ البنيويّ هنا: خطوةُ الإنفاذ تجلب المتنَ من الـAPI وقتَ التشغيل
وتفشل مغلقةً عند تعذّر الجلب — السقوطُ الصامت إلى الحمولة المجمَّدة يُعيد
العطلَ بثوب احتياط.

الإرساءُ على **خطوة الإنفاذ** وحدها لا على الملفّ كلِّه: الحمولةُ المجمَّدة
مشروعةٌ لِما يتجمّد بحقّ (SHAs — البوّابة تحكم على حالة الحدث الشيفريّة)،
والمحظورُ قراءةُ **المتن** منها.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/capability-governance.yml"


def _enforce_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("- name: Enforce declared PR capability impact")
    # حدُّ الخطوة هو الخطوةُ التالية — لا عدُّ أسطرٍ يبيت مع أوّل تعديل.
    end = text.index("- name: ", start + 1)
    return text[start:end]


def test_the_enforce_step_does_not_read_the_body_from_the_frozen_payload():
    step = _enforce_step()
    assert "github.event.pull_request.body" not in step, (
        "متنُ الحدث حمولةٌ مجمَّدة: تصحيحُ المتن بعد الانطلاق غيرُ مرئيّ لها — "
        "اقرأ المتنَ من الـAPI وقتَ التشغيل"
    )
    assert "PR_BODY:" not in step, "اسمُ الوسيط القديم عائدٌ — المتنُ يُقرأ حيّاً لا يُمرَّر حدثاً"


def test_the_enforce_step_fetches_the_body_live_and_fails_closed():
    step = _enforce_step()
    assert "/pulls/${PR_NUMBER}" in step, "الجلبُ الحيّ من مسار الـPR نفسه هو الإصلاح"
    assert "github.token" in step, "الجلبُ يحتاج رمزَ التشغيل الافتراضيّ"
    assert "jq -r '.body // \"\"'" in step, "المتنُ يُستخرَج من استجابة الـAPI"
    # الفشلُ مغلق: تعذّرُ الجلب يوقف البوّابة ولا يسقط إلى الحمولة المجمَّدة.
    assert 'if [ "$HTTP_STATUS" != "200" ]' in step and "exit 1" in step, (
        "سقوطٌ صامت إلى الحمولة المجمَّدة عند فشل الجلب يُعيد العطلَ بثوب احتياط"
    )


def test_the_frozen_shas_remain_the_judged_subject():
    """الحمولةُ المجمَّدة صحيحةٌ لِما يتجمّد بحقّ — البوّابة تحكم على شيفرة الحدث."""
    step = _enforce_step()
    assert "github.event.pull_request.head.sha" in step
    assert "github.event.pull_request.base.sha" in step
