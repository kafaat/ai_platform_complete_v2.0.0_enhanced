"""مرشّح غيوم CDSE: شرط جودة لا حقل اختياريّ — SILENT-EXCEPTION-HANDLERS-11-01 (الأخير).

كان `except (TypeError, ValueError): pass` يسقط إلى `filtered.append(feature)` — أي أنّ
قيمة `eo:cloud_cover` **غير القابلة للتحليل تُقبَل المشهدَ**. والتعليق فوق المرشّح يقول
إنّه موجود تحديداً لأنّ مسار fallback قد يكون أسقط مرشّح المزوّد، فهو أحياناً المرشّح
**الوحيد** العامل. أي fail-open في شرط جودة، على المسار الذي يُفترَض أن يحرسه.

المبدأ الحاكم: **عدم القدرة على إثبات أنّ المشهد تحت الحدّ لا يساوي إثبات أنّه صالح.**

لكنّ `invalid` و`missing` لا يُعامَلان سواءً:
  • تالف (`"bad"`) ⇒ رفض.
  • غائب (`None`) ⇒ جودة مجهولة: يُقبَل مؤقّتاً **مع عدّ وتسجيل**، لأنّ رفضه بلا قياس
    حيّ قد يحوّل نقص بيانات وصفيّة من المزوّد إلى فقد مشاهد واسع. القياس أوّلاً، ثمّ
    التشديد بقرار.

وفي الحالتين لا إسقاط صامت: لكلّ مشهد سطر تشخيص بسببه وقيمته الخام.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "cdse_client_under_test", ROOT / "services/raster-service/cdse_client.py"
)
cdse = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["cdse_client_under_test"] = cdse
_SPEC.loader.exec_module(cdse)


def _scene(scene_id: str, cloud):
    props = {} if cloud is _MISSING else {"eo:cloud_cover": cloud}
    return {"id": scene_id, "properties": props}


_MISSING = object()


# ───────────────── الحالات الأربع التي حدّدها المالك ─────────────────


def test_valid_value_under_threshold_is_accepted():
    """«12.5» تحت الحدّ ⇒ يُقبَل، بلا تشخيص (لا شيء غير مُثبَت)."""
    accepted, diags = cdse._apply_cloud_filter([_scene("s1", 12.5)], 40.0)
    assert [f["id"] for f in accepted] == ["s1"]
    assert diags == []


def test_valid_value_over_threshold_is_rejected_without_diagnostics():
    """فوق الحدّ ⇒ رفض عاديّ مُثبَت — ليس «جودة غير مُثبَتة»، فلا يُشوّش التشخيص."""
    accepted, diags = cdse._apply_cloud_filter([_scene("s1", 91.0)], 40.0)
    assert accepted == []
    assert diags == []


def test_unparseable_value_is_rejected_with_reason():
    """«bad» ⇒ رفض — هذا هو الانحدار الأصليّ: كان يُقبَل."""
    accepted, diags = cdse._apply_cloud_filter([_scene("s1", "bad")], 40.0)
    assert accepted == []
    assert len(diags) == 1
    assert diags[0]["reason"] == "invalid_cloud_cover"
    assert diags[0]["accepted"] is False
    assert diags[0]["raw_value"] == "bad"
    assert diags[0]["scene_id"] == "s1"


def test_missing_value_is_classified_not_coerced_to_zero():
    """`None` ⇒ «جودة مجهولة» لا صفر.

    التحويل إلى 0.0 كان سيجعله يمرّ **أيّ** عتبة بوصفه «صافياً تماماً» — وهو ادّعاء
    لا يملكه أحد. يُقبَل مؤقّتاً بقرار مُعلَن، لكنّه **مُصنَّف ومعدود**.
    """
    accepted, diags = cdse._apply_cloud_filter([_scene("s1", _MISSING)], 0.0)
    assert [f["id"] for f in accepted] == ["s1"]
    assert diags[0]["reason"] == "quality_unknown"
    assert diags[0]["raw_value"] is None
    assert diags[0]["accepted"] is True


def test_a_lone_corrupt_scene_does_not_become_valid_by_being_the_only_one():
    """مشهد وحيد ببيانات تالفة لا يصير مرشّحاً صالحاً لمجرّد أنّه الوحيد.

    الحالة التي سمّاها المالك: الندرة لا تُرقّي المجهول إلى مُثبَت.
    """
    accepted, diags = cdse._apply_cloud_filter([_scene("only", "n/a")], 40.0)
    assert accepted == [], "مشهد تالف وحيد يجب أن يبقى مرفوضاً"
    assert diags[0]["reason"] == "invalid_cloud_cover"


# ───────────────── العقد الصريح allow_unknown ─────────────────


def test_allow_unknown_is_not_the_default(monkeypatch):
    """الافتراضيّ `strict`: لا يُورَث قبول المجهول صامتاً."""
    monkeypatch.delenv(cdse._CLOUD_POLICY_ENV, raising=False)
    assert cdse._cloud_policy() == "strict"
    accepted, _ = cdse._apply_cloud_filter([_scene("s1", "bad")], 40.0)
    assert accepted == []


def test_allow_unknown_when_explicitly_requested(monkeypatch):
    """وضع بحث يقبل جودة مجهولة عقدٌ يُطلَب صراحةً — ويبقى مُشخَّصاً."""
    monkeypatch.setenv(cdse._CLOUD_POLICY_ENV, cdse._ALLOW_UNKNOWN)
    accepted, diags = cdse._apply_cloud_filter([_scene("s1", "bad")], 40.0)
    assert [f["id"] for f in accepted] == ["s1"]
    assert diags[0]["reason"] == "invalid_cloud_cover"
    assert diags[0]["accepted"] is True, "القبول مُعلَن لا صامت"


# ───────────────── سلوك مُجمَّع ─────────────────


def test_mixed_batch_keeps_only_provable_scenes():
    """دفعة مختلطة: يمرّ المُثبَت والمجهول، ويسقط التالف وما فوق العتبة."""
    batch = [
        _scene("good", 10.0),
        _scene("cloudy", 88.0),
        _scene("corrupt", "??"),
        _scene("nometa", _MISSING),
    ]
    accepted, diags = cdse._apply_cloud_filter(batch, 40.0)
    assert sorted(f["id"] for f in accepted) == ["good", "nometa"]
    reasons = {d["scene_id"]: d["reason"] for d in diags}
    assert reasons == {"corrupt": "invalid_cloud_cover", "nometa": "quality_unknown"}


def test_diagnostics_summary_groups_by_reason():
    """الملخّص يُجمَّع بالسبب — سجلّ قابل للقراءة لا سطر لكلّ مشهد."""
    batch = [_scene(f"c{i}", "bad") for i in range(3)] + [_scene("m", _MISSING)]
    _, diags = cdse._apply_cloud_filter(batch, 40.0)
    summary = cdse._summarize_cloud_diagnostics(diags)
    assert "invalid_cloud_cover:rejected=3" in summary
    assert "quality_unknown:accepted=1" in summary


def test_empty_input_is_not_an_error():
    assert cdse._apply_cloud_filter([], 40.0) == ([], [])


# ───────────── العدّادات المُسمّاة: شرط إغلاق صريح ─────────────


def _reset_counters():
    for k in cdse.CDSE_METADATA_OBS:
        cdse.CDSE_METADATA_OBS[k] = 0


def test_named_counters_exist_with_the_agreed_names():
    """أسماء ثابتة متّفق عليها — لا حقل `reason` داخل قائمة يقرأها أحد يدويّاً."""
    snapshot = cdse.metadata_obs_snapshot()
    assert "cdse_metadata_invalid_rejected" in snapshot
    assert "cdse_metadata_missing_accepted" in snapshot


def test_invalid_increments_only_the_rejected_counter():
    _reset_counters()
    cdse._apply_cloud_filter([_scene("s1", "bad")], 40.0)
    snap = cdse.metadata_obs_snapshot()
    assert snap["cdse_metadata_invalid_rejected"] == 1
    assert snap["cdse_metadata_missing_accepted"] == 0


def test_missing_increments_only_the_accepted_counter():
    """هذا العدّاد تحديداً هو ما يجعل «اقبل الآن وقِس ثمّ شدِّد» ممكناً.

    بلاه يستحيل قياس نسبة `missing` حيّاً، فتتحوّل السياسة المؤقّتة إلى دائمة صامتاً.
    """
    _reset_counters()
    cdse._apply_cloud_filter([_scene("s1", _MISSING)], 40.0)
    snap = cdse.metadata_obs_snapshot()
    assert snap["cdse_metadata_missing_accepted"] == 1
    assert snap["cdse_metadata_invalid_rejected"] == 0


def test_allow_unknown_acceptance_is_counted_separately(monkeypatch):
    """قبول التالف تحت العقد الصريح لا يُخلَط برفضه — وإلّا ضاع أثر تفعيل العقد."""
    monkeypatch.setenv(cdse._CLOUD_POLICY_ENV, cdse._ALLOW_UNKNOWN)
    _reset_counters()
    cdse._apply_cloud_filter([_scene("s1", "bad")], 40.0)
    snap = cdse.metadata_obs_snapshot()
    assert snap["cdse_metadata_invalid_accepted_allow_unknown"] == 1
    assert snap["cdse_metadata_invalid_rejected"] == 0


def test_valid_scenes_increment_nothing():
    """المُثبَت لا يُعدّ — العدّادات لجودة **غير مُثبَتة** فقط."""
    _reset_counters()
    cdse._apply_cloud_filter([_scene("a", 10.0), _scene("b", 99.0)], 40.0)
    assert cdse.metadata_obs_snapshot() == dict.fromkeys(cdse.CDSE_METADATA_OBS, 0)


def test_unexpected_exception_stays_visible():
    """الالتقاط ضيّق: شكل `properties` غير متوقَّع يُرفَع ولا يُبتلَع.

    شرط إغلاق صريح — الاستثناء غير المتوقَّع يبقى ظاهراً بدل أن يعود الابتلاع
    الصامت من باب آخر.
    """

    class Hostile:
        def get(self, *_a, **_k):
            raise RuntimeError("properties store unavailable")

    with pytest.raises(RuntimeError, match="properties store unavailable"):
        cdse._apply_cloud_filter([{"id": "s1", "properties": Hostile()}], 40.0)
