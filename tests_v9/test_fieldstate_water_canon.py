"""اختبار وحدة لـBundle D — المرحلة D1: حقن ET0/ETc الكنسيّين في الحالة القانونيّة.

يقفل: (أ) `compose_field_state` يضيف `et0_mm`/`etc_mm`(=Kc·ET0)/`etc_demand_class` عند توفّر إشارة ET0
— **إضافة صرفة** لا تمسّ Kc/effective_status (حفظ السلوك)؛ وغياب ET0 ⇒ لا etc (صدق). (ب) مساعِد ET0 من
حمولة الطقس يحسب عبر المحرّك الموحّد ويتدرّج إلى None بصدق عند نقص البيانات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

# النواة (core فقط — بلا api، فلا حاجة لتخطٍّ): اختبار حقن ETc في compose_field_state.
from core.agronomic_state_engine import (  # noqa: E402
    CropContext,
    SignalInput,
    compose_field_state,
)


def _ctx(et0: float | None = None) -> CropContext:
    return CropContext(crop_id="wheat", days_after_planting=60, et0_mm=et0)


def test_etc_injected_when_et0_present():
    """ET0 (عبر CropContext) + سياق محصول ⇒ et0_mm/etc_mm(=Kc·ET0)/etc_demand_class + provenance."""
    cs = compose_field_state("f1", [SignalInput(source="ndvi", value=0.6)], crop_context=_ctx(7.0))
    t = cs.operational_truths
    assert "kc" in t  # Kc محسوب (سياق المحصول مُمرَّر)
    assert t["et0_mm"] == 7.0
    assert t["etc_mm"] == pytest.approx(round(t["kc"] * 7.0, 2))
    assert t["etc_demand_class"] in {"high", "medium", "low"}
    assert any(p.get("contributes_to") == "etc_mm" for p in cs.provenance)


def test_no_etc_without_et0_behavior_preserved():
    """غياب ET0 ⇒ لا et0_mm/etc_mm؛ وKc وeffective_status بلا تغيير (إضافة صرفة)."""
    base = compose_field_state("f1", [SignalInput(source="ndvi", value=0.6)], crop_context=_ctx())
    with_et0 = compose_field_state(
        "f1", [SignalInput(source="ndvi", value=0.6)], crop_context=_ctx(7.0)
    )
    # بلا ET0: الحقول المائيّة الجديدة غائبة.
    assert "etc_mm" not in base.operational_truths
    assert "et0_mm" not in base.operational_truths
    # حفظ السلوك: Kc وeffective_status متطابقان مع/بدون ET0 (الإضافة لا تمسّهما).
    assert base.operational_truths.get("kc") == with_et0.operational_truths.get("kc")
    assert base.operational_truths.get("effective_status") == with_et0.operational_truths.get(
        "effective_status"
    )


def test_no_etc_without_crop_context():
    """بلا سياق محصول (لا Kc) ⇒ لا etc (لا اختلاق بلا Kc)."""
    cs = compose_field_state("f1", [SignalInput(source="ndvi", value=0.6)])
    assert "etc_mm" not in cs.operational_truths


def test_etc_demand_class_thresholds():
    """تصنيف الطلب: ETc>8 high · >4 medium · وإلّا low (عتبات مُعلَنة)."""
    hi = compose_field_state(
        "f1", [SignalInput(source="ndvi", value=0.6)], crop_context=_ctx(20.0)
    ).operational_truths
    lo = compose_field_state(
        "f1", [SignalInput(source="ndvi", value=0.6)], crop_context=_ctx(1.0)
    ).operational_truths
    assert hi["etc_demand_class"] == "high"
    assert lo["etc_demand_class"] in {"low", "medium"}


# ── مساعِد ET0 من حمولة الطقس (يستورد api ⇒ تخطٍّ صادق في بيئة Unit Tests الأدنى) ──
try:
    from api.field_state_projection import _et0_from_weather_payload
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة
    _et0_from_weather_payload = None


@pytest.mark.skipif(_et0_from_weather_payload is None, reason="platform/api deps unavailable")
def test_et0_payload_computes_from_temps():
    """حمولة بحرارة عظمى/صغرى ⇒ ET0 موجب (Hargreaves عبر المحرّك الموحّد)."""
    payload = {"daily": {"temperature_2m_max": [34.0], "temperature_2m_min": [18.0]}}
    et0 = _et0_from_weather_payload(payload, lat=15.5, elevation_m=1800.0, doy=180)
    assert et0 is not None and et0 > 0.0


@pytest.mark.skipif(_et0_from_weather_payload is None, reason="platform/api deps unavailable")
def test_et0_payload_missing_temps_is_none():
    """نقص الحرارة/شكل غير متوقَّع ⇒ None (صدق، لا اختلاق)."""
    assert _et0_from_weather_payload({"daily": {}}, 15.5, None, 180) is None
    assert _et0_from_weather_payload({}, 15.5, None, 180) is None
    assert _et0_from_weather_payload(None, 15.5, None, 180) is None
