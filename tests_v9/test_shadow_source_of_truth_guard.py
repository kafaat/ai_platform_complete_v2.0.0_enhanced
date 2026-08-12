"""`SHADOW-SOURCE-OF-TRUTH-01` — مفتاحٌ واحد بمُنتِجٍ واحد، وعقودٌ لا تُخالِف السجلّ.

**والعطل الذي يحرسه وقع فعلاً:** كان `maximum_safe_depth_mm_event` مفتاحاً واحداً
يُصدِره مُنتِجان — قدرةُ الرشّ (قيدُ الجريان) والرسمُ البيانيّ
(`min(machine_depth, safe_event_depth)`، وهو أضيق). ولم يظهر بالقراءة بل ساعةَ
ربط المُنسِّق. وهذا الحارس يجعل ظهورَه لا يعتمد على أن يربط أحدٌ شيئاً.

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
_GUARD = _ROOT / "scripts" / "ci" / "shadow_source_of_truth_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("shadow_source_of_truth_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def _entry(**overrides) -> dict:
    base = {
        "key": "a.k",
        "source_of_truth": "sot_a",
        "producer_module": "prod/a.py",
        "producer_field": "f",
        "producer_digest_field": "capability_digest",
    }
    base.update(overrides)
    return base


def _contracts(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "contracts"
    target.mkdir(exist_ok=True)
    (target / "c.py").write_text(body, encoding="utf-8")
    return target


_AGREEING = """
from .contracts import KnowledgeRequirement, TaskContextContract

C = TaskContextContract(
    task="t",
    requirements=(KnowledgeRequirement(key="a.k", source_of_truth="sot_a"),),
)
"""


def test_an_agreeing_registry_and_contract_pass(tmp_path):
    problems, declared = guard.violations([_entry()], _contracts(tmp_path, _AGREEING))
    assert problems == []
    assert declared == 1


def test_two_producers_for_one_key_are_blocked(tmp_path):
    """العطل المقيس بعينه: اسمٌ واحد لقيمتين مختلفتي المعنى."""
    keys = [_entry(), _entry(source_of_truth="sot_b", producer_module="prod/b.py")]
    problems, _ = guard.violations(keys, _contracts(tmp_path, _AGREEING))
    assert any("مفتاحٌ بمُنتِجَين" in p for p in problems)


def test_one_source_name_claimed_by_two_modules_is_blocked(tmp_path):
    """اسمُ المصدر هويّةٌ لا وصف: مِلَفّان يدّعيانه يجعلان النَّسَب غير قابلٍ للحلّ."""
    keys = [_entry(), _entry(key="a.k2", producer_module="prod/other.py")]
    problems, _ = guard.violations(keys, _contracts(tmp_path, _AGREEING))
    assert any("يُدَّعى مصدراً من مِلَفّين" in p for p in problems)


def test_a_contract_naming_a_different_source_is_blocked(tmp_path):
    """أرخصُ طريقٍ إلى مصدر الحقيقة الظلّ: إعلانٌ واحد يخالف السجلّ."""
    body = _AGREEING.replace('source_of_truth="sot_a"', 'source_of_truth="sot_other"')
    problems, _ = guard.violations([_entry()], _contracts(tmp_path, body))
    assert any("مصدرُ حقيقةٍ ظلّ" in p for p in problems)


def test_a_contract_declaring_an_unregistered_key_is_blocked(tmp_path):
    body = _AGREEING.replace('key="a.k"', 'key="a.unknown"')
    problems, _ = guard.violations([_entry()], _contracts(tmp_path, body))
    assert any("غير مُسجَّل" in p for p in problems)


def test_a_source_name_in_a_comment_is_not_a_declaration(tmp_path):
    """يُقرأ الاستدعاء لا النصّ — وإلّا صار التوثيق يُحمِر الحارس.

    وهذا صنفٌ مُسجَّل في هذه الشجرة (`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`)،
    وقد أحمرّ به اختبارٌ لي فعلاً في بوّابة المنشأ.
    """
    body = _AGREEING + '\n# ملاحظة: source_of_truth="sot_other" مذكورٌ هنا شرحاً فقط\n'
    problems, declared = guard.violations([_entry()], _contracts(tmp_path, body))
    assert problems == [], f"تعليقٌ عُومِل إعلاناً: {problems}"
    assert declared == 1


def test_a_missing_contract_directory_fails_closed(tmp_path):
    problems, _ = guard.violations([_entry()], tmp_path / "absent")
    assert any("غير موجود" in p for p in problems)


def test_zero_declared_requirements_fails_closed(tmp_path, monkeypatch):
    """«لم يُقرأ إعلانٌ» ليس «كلّ الإعلانات موافقة»."""
    registry = tmp_path / "reg.json"
    registry.write_text(
        json.dumps({"schema": "sahool.knowledge_source_registry", "keys": [_entry()]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "violations", lambda keys, contracts: ([], 0))
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(registry), "--contracts", str(tmp_path)])


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--contracts", str(tmp_path)])


def test_a_wrong_schema_fails_closed(tmp_path):
    contracts = _contracts(tmp_path, _AGREEING)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": "else", "keys": [_entry()]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(other), "--contracts", str(contracts)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_the_live_contracts_are_actually_read():
    """المسار الثاني: العقود الحقيقيّة — فصفرُ إعلانٍ يعني أنّ البند لم يُفحَص."""
    keys = guard.load_keys(guard.REGISTRY)
    problems, declared = guard.violations(keys, guard.CONTRACT_DIR)
    assert problems == []
    assert declared >= 2, f"عدد المتطلّبات المُعلَنة انخفض: {declared}"


def test_a_positionally_declared_contract_is_compared_to_the_registry(tmp_path):
    """البند (٣) كان قابلاً للتجاوز بإعلانٍ موضعيّ لا يُقارَن بالسجلّ إطلاقاً.

    `KnowledgeRequirement` صنفُ بيانات، فالتمرير الموضعيّ مشروع — وقراءةُ
    المُسمّى وحده جعلت المخالفة **غير مرئيّة**، وهي أخفى من مخالفةٍ صريحة.
    أمسكتها المراجعة.
    """
    body = (
        "from .contracts import KnowledgeRequirement\n"
        'R = KnowledgeRequirement("a.k", "sot_other")\n'
    )
    problems, declared = guard.violations([_entry()], _contracts(tmp_path, body))
    assert declared == 1
    assert any("مصدرُ حقيقةٍ ظلّ" in p for p in problems)
