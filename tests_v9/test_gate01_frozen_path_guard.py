"""تكذيب حارس المسارات المجمَّدة خلف GATE-01.

**العطل المقيس الذي يحرسه وقع مرّتين:** حكم المالك يمنع تعديل مسارات التنفيذ
الفيزيائيّ قبل تجميد أدلّة المرحلة 0، وكان مفروضاً بقراءةِ بشرٍ لملفٍّ نثريّ — فمُسّت
المسارات في 2026-08-09 و2026-08-13، وفي المرّتين نُفِّذت رقعةٌ كاملة ثمّ أُرجِعت بايتاً.
والكلفة ليست الوقت: المنع يجب أن يقع **قبل** العمل، وذلك لا يكون بوثيقةٍ تُقرَأ.

**والتأكيد الأهمّ هنا `test_the_real_reverted_patch_would_have_been_caught`:** يقيس
الحارس على المسارَين اللذين مُسّا فعلاً، فيُثبِت أنّه كان سيُمسِك الحادثة الحقيقيّة —
لا حادثةً مُركَّبة تُشبِهها.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "gate01_frozen_path_guard.py"
_POLICY = _ROOT / "docs" / "architecture" / "gate01_frozen_paths.json"


def _load():
    spec = importlib.util.spec_from_file_location("gate01_frozen_path_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_CLOSED = {
    "gate": {"state": "CLOSED", "gap_id": "G-01", "phase_1_code_changes": "NOT_AUTHORIZED"},
    "frozen_paths": ["a/frozen.py", "b/also_frozen.sql"],
}


def test_an_untouched_frozen_path_passes():
    assert guard.violations(_CLOSED, ["docs/readme.md", "scripts/ci/x.py"]) == []


def test_touching_a_frozen_path_is_blocked():
    """الصنف المقصود: تعديلٌ يقع تحت التجميد والبوّابة مغلقة."""
    problems = guard.violations(_CLOSED, ["a/frozen.py"])
    assert problems and "a/frozen.py" in problems[0]


def test_the_message_names_the_gap_and_the_way_out():
    """رسالةٌ تقول «ممنوع» بلا سبيلٍ إلى الحلّ تُقرَأ عائقاً لا حارساً."""
    problems = guard.violations(_CLOSED, ["a/frozen.py"])
    assert "G-01" in problems[0]
    assert "NOT_AUTHORIZED" in problems[0]
    assert "قرار مالكٍ صريح" in problems[0]


def test_an_open_gate_lets_the_same_change_through():
    """البوّابة ليست زينة: فتحُها يجب أن يُغيّر السلوك فعلاً.

    وبدون هذا التأكيد يمكن أن يكون بند `OPEN` كوداً ميّتاً، فيمرّ الحارس أخضر
    عن سؤالٍ لم يُطرَح.
    """
    policy = json.loads(json.dumps(_CLOSED))
    policy["gate"]["state"] = "OPEN"
    assert guard.violations(policy, ["a/frozen.py"]) == []


@pytest.mark.parametrize("state", ["", "closed?", None, "TRUE", "1", "opened"])
def test_any_state_that_is_not_open_fails_closed(state):
    """حقلٌ مشوَّه ليس إذناً — والافتراضيّ الإغلاق لا المرور.

    و`"open "` **ليست** في القائمة عمداً: تشذيب الفراغ حول قيمةٍ في JSON تطبيعٌ لا
    تساهل، ومسافةٌ زائدة حادثةُ تنسيقٍ لا نيّةُ إغلاق. وأوّل صياغةٍ عندي عدّتها
    مشوَّهةً فأحمرّ التأكيد على سلوكٍ صحيح — أي أنّ **الاختبار** كان الخطأ.
    """
    policy = json.loads(json.dumps(_CLOSED))
    policy["gate"]["state"] = state
    assert guard.violations(policy, ["a/frozen.py"]) != []


def test_a_missing_policy_file_fails_closed(tmp_path):
    """سياسةٌ محذوفة ليست «لا تجميد» — وإلّا أُلغي الحارس بحذف ملفٍّ واحد."""
    with pytest.raises(SystemExit):
        guard.load_policy(tmp_path / "absent.json")


def test_a_wrong_schema_fails_closed(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"schema": "else", "frozen_paths": ["x"]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.load_policy(p)


def test_an_empty_frozen_list_fails_closed(tmp_path):
    """قائمةٌ فارغة تجعل الحارس يمرّ دائماً — وهي خضرةٌ لا تقيس شيئاً."""
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"schema": guard.SCHEMA, "frozen_paths": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.load_policy(p)


def test_the_live_policy_is_readable_and_closed():
    policy = guard.load_policy(_POLICY)
    assert policy["gate"]["state"] == "CLOSED", "فُتِحت GATE-01 — راجِع حكم المالك قبل أيّ شيء"
    assert policy["gate"]["frozen_commit_sha"] is None


def test_the_real_reverted_patch_would_have_been_caught():
    """المرساة على الحادثة الحقيقيّة لا على مثالٍ يُشبِهها.

    هذان المساران هما اللذان مُسّا فعلاً ثمّ أُرجِعا بايتاً. فلو لم يُحمِرّ الحارس
    عليهما لكان يحرس عالماً غير الذي وقع فيه العطل.
    """
    policy = guard.load_policy(_POLICY)
    touched = [
        "services/actuator-service/actuator_runtime.py",
        "services/actuator-service/routers/commands.py",
    ]
    problems = guard.violations(policy, touched)
    assert len(problems) == 2, f"الحارس لا يرى الحادثة الحقيقيّة: {problems}"


def test_every_frozen_path_either_exists_or_is_declared_absent():
    """مسارٌ مجمَّد لا وجود له يحرس عدماً — إلّا أن يكون غيابُه **مُصرَّحاً**.

    ومساران هنا من الشريحة المحجوبة نفسها فلم يُدمَجا قطّ؛ تجميدُهما يعني «لا
    تُنشئهما». فالتأكيد يقبل الغياب المُعلَن ويرفض الغياب الصامت — إذ الصامت
    يُخفي انزياح إعادة تسمية، فيصير الحارس يحرس اسماً لم يعد له مسمّى.

    **وهذا التأكيد أمسك خطأً في بياناتي فعلاً:** أدرجتُ المسارين بلا تصريح،
    فأحمرّ ودلّني على أنّ القائمة تصف عالماً غير الموجود.
    """
    policy = guard.load_policy(_POLICY)
    declared_absent = set(policy.get("not_yet_in_tree") or [])
    missing = [
        p for p in policy["frozen_paths"] if not (_ROOT / p).exists() and p not in declared_absent
    ]
    assert missing == [], f"مسارات مجمَّدة غائبة بلا تصريح (أُعيدت تسميتها؟): {missing}"

    ghost = [p for p in declared_absent if (_ROOT / p).exists()]
    assert ghost == [], (
        f"مسارات مُصرَّحٌ بغيابها وهي موجودة: {ghost} — هبطت الشريحة المحجوبة؟ راجِع حالة البوّابة"
    )
