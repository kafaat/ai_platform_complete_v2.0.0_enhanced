"""`KNOWLEDGE-PROVENANCE-01` — مُنتِجٌ بلا نَسَبٍ كامل يُحجَب.

**والمرساةُ الزمنيّة هي البند الذي يستحقّ الانتباه:** بلا `generated_at` لا يُقاس
عمرُ القيمة، فيصير كلّ عقدٍ يُعلِن `max_age_seconds` حاجباً دائماً بـ
`FRESHNESS_UNMEASURABLE`. أي أنّ بند الطزاجة في المُحلِّل يبقى **معطَّلاً بصمت**
ما لم يُفرَض هنا — وقد كان كذلك فعلاً حتّى هذه الشريحة.

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
_GUARD = _ROOT / "scripts" / "ci" / "knowledge_provenance_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("knowledge_provenance_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_COMPLETE = """
def build(now):
    return {
        "schema_version": "x.v1",
        "product_version": "x/1.0.0",
        "generated_at": now,
        "effective_at": now,
        "capability_digest": "d",
    }
"""


def _tree(tmp_path: Path, body: str) -> Path:
    (tmp_path / "prod").mkdir(exist_ok=True)
    (tmp_path / "prod" / "p.py").write_text(body, encoding="utf-8")
    return tmp_path


def _keys(**overrides) -> list[dict]:
    entry = {
        "key": "k",
        "source_of_truth": "sot",
        "producer_module": "prod/p.py",
        "producer_field": "f",
        "producer_digest_field": "capability_digest",
    }
    entry.update(overrides)
    return [entry]


def test_a_complete_producer_passes(tmp_path):
    problems, examined = guard.violations(_keys(), _tree(tmp_path, _COMPLETE))
    assert problems == []
    assert examined == 1


@pytest.mark.parametrize("field", list(guard.REQUIRED_PROVENANCE))
def test_each_required_provenance_field_is_enforced_on_its_own(tmp_path, field):
    """كلُّ حقلٍ على حدة: تأكيدٌ واحد على المجموعة لا يقول أيُّها سقط."""
    body = _COMPLETE.replace(f'"{field}":', '"unrelated":')
    problems, _ = guard.violations(_keys(), _tree(tmp_path, body))
    assert problems and field in problems[0]


def test_a_missing_time_anchor_names_the_freshness_consequence(tmp_path):
    """رسالةٌ تقول «ينقصه حقل» لا تُفهِم قارئها لماذا يهمّ."""
    body = _COMPLETE.replace('"generated_at":', '"unrelated":')
    problems, _ = guard.violations(_keys(), _tree(tmp_path, body))
    assert problems and "الطزاجة" in problems[0]


def test_a_producer_without_its_declared_digest_is_blocked(tmp_path):
    body = _COMPLETE.replace('"capability_digest": "d",', "")
    problems, _ = guard.violations(_keys(), _tree(tmp_path, body))
    assert any("بصمة" in p for p in problems)


def test_an_undeclared_digest_field_is_blocked_not_assumed(tmp_path):
    """الافتراض الصامت هو الصنف نفسه: بصمةٌ تُخمَّن ليست بصمة.

    وهذا مقيس: أوّل صياغةٍ للحارس افترضت `capability_digest` فأطلقت على
    `canonical_root_zone_profile` وبصمتُه `profile_digest`.
    """
    keys = _keys()
    del keys[0]["producer_digest_field"]
    problems, _ = guard.violations(keys, _tree(tmp_path, _COMPLETE))
    assert problems and "غير مُعلَن" in problems[0]


def test_a_digest_assigned_as_a_keyword_still_counts(tmp_path):
    """`Cls(**base, capability_digest=_digest(base))` نمطُ هذه الشجرة الفعليّ.

    فحصُ مفاتيح القواميس وحدها كان سيُطلِق على كلّ مُنتِجٍ فيها.
    """
    body = _COMPLETE.replace('        "capability_digest": "d",\n', "") + (
        "\n\ndef make(base):\n    return dict(**base, capability_digest='x')\n"
    )
    problems, _ = guard.violations(_keys(), _tree(tmp_path, body))
    assert problems == [], f"إيجابيّة كاذبة على النمط الحقيقيّ: {problems}"


def test_a_missing_producer_module_is_blocked(tmp_path):
    problems, _ = guard.violations(_keys(producer_module="prod/gone.py"), tmp_path)
    assert any("غير موجود" in p for p in problems)


def test_zero_examined_producers_fails_closed(tmp_path, monkeypatch):
    """«صفر مفحوص» ليس نجاحاً — ويُختبَر عند **عقد `violations`** لا ببيانات.

    أوّل صياغةٍ عندي وجّهت الجذر إلى مجلّدٍ غائب، فوقع الحجب ببند «المُنتِج غير
    موجود» لا ببند الصفر — والفرع لا يُبلَغ ببياناتٍ أصلاً لأنّ كلّ مُنتِجٍ
    مفقود يُضيف مخالفةً قبله. فالبند هنا يحرس **عقداً داخليّاً**: مهما تغيّرت
    `violations` مستقبلاً، `([], 0)` لا يجوز أن يصير PASS. كشفَت الطفرةُ ذلك
    وهي خضراء.
    """
    registry = tmp_path / "reg.json"
    registry.write_text(
        json.dumps({"schema": "sahool.knowledge_source_registry", "keys": _keys()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "violations", lambda keys, root: ([], 0))
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(registry), "--root", str(tmp_path)])


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--root", str(tmp_path)])


def test_a_wrong_schema_fails_closed(tmp_path):
    root = _tree(tmp_path, _COMPLETE)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": "else", "keys": _keys()}), encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(other), "--root", str(root)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_every_live_producer_carries_a_time_anchor():
    """المسار الثاني: المُنتِجون الحقيقيّون — فسقوطُ المرساة يُحمِرّ هنا.

    و`sprinkler` و`graph` كانا بلا مرساةٍ زمنيّة قبل هذه الشريحة؛ وهذا
    التأكيد يمنع عودتهما إلى ذلك.
    """
    keys = guard.load_keys(guard.REGISTRY)
    for entry in keys:
        source = (guard.ROOT / entry["producer_module"]).read_text(encoding="utf-8")
        assert '"generated_at"' in source, entry["producer_module"]
        assert '"effective_at"' in source, entry["producer_module"]
