"""`KNOWLEDGE-CANONICAL-CONSUMPTION-01` — الارتداد إلى الخام يُحجَب.

**والاختبارات على أشجارٍ مُركَّبة** (`tmp_path`) لا على الشجرة الحيّة: حارسٌ لا
يُكذَّب إلّا بتحريك المستودع الحقيقيّ يصير تكذيبُه رهن حالته اليوم، فيمرّ أخضرَ
صامتاً يوم تتغيّر. والشجرة الحيّة مسارٌ ثانٍ (اختباران في الذيل).

**وأهمّ ما هنا اختبارٌ سالب:** `test_a_separate_legitimate_raw_read_is_not_a_violation`.
حارسٌ يُجرِّم كلّ ذِكرٍ لـ`raw_mm` كان سيُطلِق على `hourly_energy_aware_irrigation_mpc`
الذي يقرؤه لغرضه المشروع — والإيجابيّة الكاذبة تُدرِّب قارئها على تجاهل الأحمر،
فتُسقِط الحارس بلا أن تُعطِّله.

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
_GUARD = _ROOT / "scripts" / "ci" / "canonical_consumer_bypass_guard.py"

_FIELD = "maximum_safe_depth_mm_event"


def _load():
    spec = importlib.util.spec_from_file_location("canonical_consumer_bypass_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def _tree(tmp_path: Path, *, producer: str, consumers: dict[str, str]) -> Path:
    """شجرةٌ مُركَّبة: مُنتِجٌ ومستهلكون، بمسارات نسبيّة كما في السجلّ."""
    (tmp_path / "prod").mkdir(exist_ok=True)
    (tmp_path / "prod" / "producer.py").write_text(producer, encoding="utf-8")
    (tmp_path / "cons").mkdir(exist_ok=True)
    for name, body in consumers.items():
        (tmp_path / "cons" / f"{name}.py").write_text(body, encoding="utf-8")
    return tmp_path


def _keys(consumers: list[str], **overrides) -> list[dict]:
    entry = {
        "key": "root_zone.maximum_safe_depth_mm_event",
        "source_of_truth": "canonical_sprinkler_runoff_capability",
        "producer_module": "prod/producer.py",
        "producer_field": _FIELD,
        "forbidden_raw_inputs": ["raw_mm", "taw_mm"],
        "forbidden_reason_ar": "سبب",
        "consumers": [f"cons/{c}.py" for c in consumers],
    }
    entry.update(overrides)
    return [entry]


_PRODUCER = f'''
def build():
    return {{"{_FIELD}": 12.0}}
'''

_GOOD_CONSUMER = f'''
def plan(capability):
    depth = capability.get("{_FIELD}")
    return depth
'''


def test_a_canonical_read_alone_passes(tmp_path):
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"good": _GOOD_CONSUMER})
    problems, examined = guard.violations(_keys(["good"]), root)
    assert problems == []
    assert examined == 1


def test_an_or_fallback_to_raw_is_blocked(tmp_path):
    """`cap.get(F) or raw_mm` — الشكل الأوّل للارتداد، وأقصرُه."""
    body = f'''
def plan(capability, raw_mm):
    depth = capability.get("{_FIELD}") or raw_mm
    return depth
'''
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"bad": body})
    problems, _ = guard.violations(_keys(["bad"]), root)
    assert problems, "الارتداد بـ`or` يجب أن يُحجَب"
    assert "depth" in problems[0]


def test_a_deferred_none_fallback_is_blocked(tmp_path):
    """الشكل الثاني، وهو الأرجح عمليّاً: قراءةٌ قانونيّة ثمّ سدُّ الغياب بالخام."""
    body = f'''
def plan(capability, raw_mm):
    depth = capability.get("{_FIELD}")
    if depth is None:
        depth = raw_mm * 0.8
    return depth
'''
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"bad": body})
    problems, _ = guard.violations(_keys(["bad"]), root)
    assert problems and "depth" in problems[0]


def test_a_separate_legitimate_raw_read_is_not_a_violation(tmp_path):
    """شكلُ `hourly_energy_aware_irrigation_mpc` بعينه: اسمان منفصلان، غرضان.

    `raw_mm` كمّيّةٌ مشروعة لحساب الاستنزاف؛ تجريمُ ذِكرِها يجعل الحارس يكذب.
    """
    body = f'''
def plan(capability, water_state):
    depth = capability.get("{_FIELD}")
    raw = water_state.get("raw_mm")
    depletion = water_state.get("depletion_mm")
    needed = raw - depletion
    return min(depth, needed)
'''
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"ok": body})
    problems, _ = guard.violations(_keys(["ok"]), root)
    assert problems == [], f"إيجابيّة كاذبة: {problems}"


def test_a_dict_key_is_a_write_not_a_read(tmp_path):
    """`{"raw_mm": x}` إعلانُ حقلٍ في مخرَج، لا قراءةٌ منه.

    **والشكل هنا شكلُ مُعيدِ التصدير بعينه** — `canonical_irrigation_capability_graph`
    يفعله فعلاً: يقرأ الحقل القانونيّ ثمّ يعرضه مفتاحاً في مخرَجه. فلو عُدَّت
    مفاتيحُ القاموس قراءةً لصار القاموسُ الواحد مربوطاً بالحقل **و**ملوَّثاً
    بالخام معاً، فتُطلَق المخالفة على مُنتِجٍ سليم.

    وأوّل صياغةٍ عندي وضعت المفتاح الخام في قاموسٍ لا يحمل الحقل القانونيّ، فلم
    يتقاطع شيءٌ ومرّ الاختبار بلا أن يمسّ القاعدة — كشفَته الطفرة وهي خضراء.
    """
    body = f'''
def build(capability, water_state):
    depth = capability.get("{_FIELD}")
    raw = water_state.get("raw_mm")
    base = {{
        "{_FIELD}": depth,
        "raw_mm": raw,
    }}
    return base
'''
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"ok": body})
    problems, _ = guard.violations(_keys(["ok"]), root)
    assert problems == [], f"مفتاح قاموس عُومِل قراءةً: {problems}"


def test_a_consumer_that_never_reads_the_field_is_blocked(tmp_path):
    """البند الإيجابيّ: مدخلٌ يَعِد بحراسةٍ لا تقع.

    مُستهلِكٌ كفّ عن قراءة الحقل يجعل السجلّ يصف شجرةً زالت — والخضرة عنه
    تُقرأ «مفحوصٌ وسليم» وهي «لم يُفحَص شيء».
    """
    body = "def plan(capability):\n    return capability.get('other')\n"
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"stale": body})
    problems, _ = guard.violations(_keys(["stale"]), root)
    assert problems and "لا يقرأ" in problems[0]


def test_a_missing_consumer_file_is_blocked(tmp_path):
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"good": _GOOD_CONSUMER})
    problems, _ = guard.violations(_keys(["good", "gone"]), root)
    assert any("غير موجود" in p for p in problems)


def test_a_missing_producer_is_blocked(tmp_path):
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"good": _GOOD_CONSUMER})
    keys = _keys(["good"], producer_module="prod/vanished.py")
    problems, _ = guard.violations(keys, root)
    assert any("المُنتِج المُعلَن غير موجود" in p for p in problems)


def test_a_producer_that_lost_the_field_is_blocked(tmp_path):
    """المُنتِج أُعيدت تسمية حقله ⇒ السجلّ يصف عقداً لم يعد قائماً."""
    root = _tree(
        tmp_path, producer="def build():\n    return {}\n", consumers={"good": _GOOD_CONSUMER}
    )
    problems, _ = guard.violations(_keys(["good"]), root)
    assert any("لا يذكر الحقل" in p for p in problems)


def test_an_entry_without_forbidden_inputs_is_blocked(tmp_path):
    """قيدٌ بلا محتوى: مدخلٌ يُعلَن ولا يمنع شيئاً — وهو أسوأ من غيابه."""
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"good": _GOOD_CONSUMER})
    problems, _ = guard.violations(_keys(["good"], forbidden_raw_inputs=[]), root)
    assert problems and "بلا محتوى" in problems[0]


def test_zero_examined_consumers_fails_closed(tmp_path):
    """«صفر مفحوص» ليس نجاحاً — وهو الفرع الذي يجعل حارساً أخضرَ إلى الأبد."""
    registry = tmp_path / "reg.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "sahool.knowledge_source_registry",
                "keys": _keys([]),
            }
        ),
        encoding="utf-8",
    )
    _tree(tmp_path, producer=_PRODUCER, consumers={})
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(registry), "--root", str(tmp_path)])


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--root", str(tmp_path)])


def test_an_unparsable_registry_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(bad), "--root", str(tmp_path)])


def test_a_wrong_schema_fails_closed(tmp_path):
    """مخطَّطٌ آخر يُقرأ سجلّاً ⇒ الحارس يفحص وثيقةً ليست وثيقتَه.

    **والوثيقة هنا سليمةٌ تماماً عدا مخطَّطها** عمداً: أوّل صياغةٍ عندي كتبت
    `keys: []` فكان الحجب يقع بفرع «سجلٌّ بلا مفاتيح» لا بفرع المخطَّط، فبقيت
    الخاصّيّة بلا حارس — والطفرة هي التي كشفت ذلك وهي خضراء.
    """
    root = _tree(tmp_path, producer=_PRODUCER, consumers={"good": _GOOD_CONSUMER})
    other = tmp_path / "other.json"
    other.write_text(
        json.dumps({"schema": "something.else", "version": 1, "keys": _keys(["good"])}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(other), "--root", str(root)])


def test_an_empty_key_list_fails_closed(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text(
        json.dumps({"schema": "sahool.knowledge_source_registry", "keys": []}), encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(empty), "--root", str(tmp_path)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_the_live_registry_declares_the_two_slice_keys():
    """المسار الثاني: السجلّ الحقيقيّ نفسه — فتغيُّرُه يُحمِرّ هنا لا في مكانٍ بعيد."""
    keys = guard.load_keys(guard.REGISTRY)
    declared = {entry["key"] for entry in keys}
    assert "root_zone.root_zone_refill_cap_mm" in declared
    assert "root_zone.maximum_safe_depth_mm_event" in declared
    problems, examined = guard.violations(keys, guard.ROOT)
    assert problems == []
    assert examined >= 4, f"عدد المستهلكين المفحوصين انخفض: {examined}"
