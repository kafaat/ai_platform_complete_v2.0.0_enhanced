"""مفردات حارس انتقال الحالة — BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01.

كان النمط `\\b(CLOSED|…)\\b` خاطئاً في الاتّجاهين معاً، وكلّ خطأ يُخفي الآخر:

* **إيجابيّة كاذبة:** `fail-closed` و`open-closed` **وصفُ تصميم** لا انتقالُ حالة،
  والشرطة حدُّ كلمة. والمصطلح يظهر **٢٧٣ مرّة في الدماغ وحده** و٤٧٧ ملفّاً في
  المستودع — فأيّ مذكّرة دماغيّة تشرح قاعدة fail-closed كانت تُرفَض برسالة عن
  «انتقال إغلاق/تحقّق». حجبٌ صحيح **بسبب كاذب**، وهو أسوأ من عدم الحجب: الرسالة
  تُرسِل القارئ يبحث عن ادّعاء لم يُكتَب قطّ.
* **سلبيّة كاذبة:** `CLOSED_IN_CODE` و`CLOSED_IN_CODE_AND_PG_PROVEN` هما **مفردة
  الإغلاق الفعليّة في هذا المستودع**، و`\\b` يسقط على `_` اللاحقة — فالادّعاءات
  الحقيقيّة التي وُجِد الحارس لأجلها كانت تمرّ من أمامه.

اكتُشف حين حجب هذا الحارسُ شريحةَ بروتوكول دماغ لا تدّعي إغلاقاً، لأنّ سطراً فيها
يشرح **لماذا** قاعدة تصنيف المفاتيح fail-closed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "brain_state_transition_guard", ROOT / "scripts/ci/brain_state_transition_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)

# ادّعاءات إغلاق حقيقيّة — يجب أن تُلتقَط.
_REAL_CLAIMS = [
    "+- **الحالة:** CLOSED",
    "+- **CLOSED_IN_CODE + PG16_PROVEN**",
    "+- CLOSED_IN_CODE_AND_PG_PROVEN",
    "+| GAP-X | عنوان | VERIFIED |",
    "+- RUNTIME_VERIFIED",
    "+- PRODUCTION_CERTIFIED",
    "+- الحالة verified حيّاً بعد النشر",
]

# وصف تصميم أو نصّ عابر — يجب ألّا يُلتقَط.
_NOT_CLAIMS = [
    "+- **لماذا الاتّجاه fail-closed:** العجز عن الإثبات ليس إثباتاً",
    "+- the rule is fail-closed by design",
    "+- open-closed principle applies here",
    "+- الحارس مُغلَق عند الفشل",
    "+- closedness of the import graph",
]


@pytest.mark.parametrize("line", _REAL_CLAIMS)
def test_real_closure_claims_are_still_caught(line: str):
    """الأهمّ: الإصلاح لا يُضعِف الحارس. مفردة الإغلاق الحقيقيّة تبقى محجوبة."""
    assert guard.CLOSED_RE.search(line), f"ادّعاء إغلاق حقيقيّ أفلت: {line}"


@pytest.mark.parametrize("line", _NOT_CLAIMS)
def test_design_descriptions_are_not_closure_claims(line: str):
    """`fail-closed` وصفُ تصميم — حجبُه يُرسِل القارئ خلف ادّعاء لم يُكتَب."""
    assert not guard.CLOSED_RE.search(line), f"إيجابيّة كاذبة: {line}"


def test_the_underscore_vocabulary_was_the_false_negative():
    """تثبيت الاتّجاه الثاني: `CLOSED_IN_CODE` كان يمرّ من أمام الحارس.

    النمط القديم `\\b(CLOSED)\\b` يسقط على `_` اللاحقة. هذا الاختبار يفشل لو عاد
    أحدٌ إلى حدود الكلمة المجرّدة — وهو الاتّجاه الذي لا تكشفه إيجابيّةٌ كاذبة.
    """
    assert guard.CLOSED_RE.search("+- الحالة: CLOSED_IN_CODE")
    assert guard.CLOSED_RE.search("+- الحالة: CLOSED_IN_CODE_AND_PG_PROVEN")


def test_brain_only_diff_without_any_claim_passes(capsys):
    """شريحة دماغ لا تدّعي إغلاقاً تمرّ — وهي الحالة التي كشفت العطل."""
    guard.check(
        ["sahool-brain/decisions/ledger.md"],
        "+- **لماذا الاتّجاه fail-closed:** شرح القاعدة\n",
    )
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out


def test_brain_only_diff_with_a_real_claim_is_still_rejected():
    """والحجب يبقى قائماً حيث يجب: إغلاق مُدَّعى بلا كود تنفيذيّ خارج الدماغ."""
    with pytest.raises(SystemExit):
        guard.check(["sahool-brain/gaps/registry.md"], "+- **الحالة:** CLOSED\n")


def test_a_real_claim_with_executable_evidence_passes(capsys):
    """الادّعاء مصحوباً بكود/اختبار خارج الدماغ يمرّ — وهذا عقد الحارس نفسه."""
    guard.check(
        ["sahool-brain/gaps/registry.md", "services/x/main.py"],
        "+- **الحالة:** CLOSED\n",
    )
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out
