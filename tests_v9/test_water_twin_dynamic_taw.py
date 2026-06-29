"""اختبار وحدة لاشتقاق TAW الديناميكيّ من عمق الجذور Zr في نقطة توأم المياه — بلا قاعدة.

يقفل الصدق المنهجيّ لربط Zr بحساب الاستنزاف (Bundle B):
  - TAW المُشتقّ **يزيد مع عمر المحصول** (جذور أعمق ⇒ خزّان أعمق) — FAO-56 §8 + Eq.82.
  - تمرير ``taw_mm`` صراحةً ⇒ ``taw_source == "request"`` (حفظ السلوك القائم تماماً، لا انحدار).
  - بطاقة محصول مفقودة + لا ``taw_mm`` ⇒ ``ValueError`` (يُترجَم 422 يطلب taw_mm صريحاً، لا تخمين).

يُختبَر المنطق النقيّ ``resolve_taw_raw`` (الذي يحقنه الراوتر) دون DB. استيراد ``api.*`` ملفوف
بـtry/except → ``pytest.skip(allow_module_level=True)`` (نمط ``test_etc_dual_weather.py``) كي لا يكسر
وظيفة CI «Unit Tests» الأدنى (بلا تبعيّات المنصّة)؛ تُغطّى في «Platform Unit Tests».
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    import api.main  # noqa: E402, F401 — تهيئة كاملة تسجّل الراوترات وتحلّ الاستيراد الدائريّ
    from api.routers.water_twin import FieldWaterTwinRequest, resolve_taw_raw  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable (minimal Unit Tests env)", allow_module_level=True)


def test_dynamic_taw_increases_with_age():
    """TAW المُشتقّ من Zr يزيد مع العمر (جذور أعمق) ثمّ يستقرّ عند العمق الأقصى."""
    req = FieldWaterTwinRequest(zr_min=0.10, zr_max=1.0, texture="loam")
    taw_young, _, meta_young = resolve_taw_raw(req, "قمح", 5)
    taw_mid, _, meta_mid = resolve_taw_raw(req, "قمح", 20)
    taw_max, _, _ = resolve_taw_raw(req, "قمح", 200)
    assert taw_young < taw_mid < taw_max  # نموّ رتيب قبل التشبّع
    # المصدر مُعلَن + عمق الجذور المُشتقّ مكشوف (شفافيّة) + عمق أعمق لعمر أكبر.
    assert meta_young["taw_source"] == "dynamic_zr"
    assert meta_young["root_depth_m"] < meta_mid["root_depth_m"]
    assert any("معايرة" in n for n in meta_young["notes"])  # صدق: Zr/θ تقديريّة


def test_dynamic_raw_is_fraction_of_taw():
    """RAW المُشتقّ = p·TAW عند غياب raw_mm (نسبة الاستنزاف المسموح)."""
    req = FieldWaterTwinRequest(zr_min=0.10, zr_max=1.0, raw_fraction=0.5)
    taw, raw, _ = resolve_taw_raw(req, "قمح", 30)
    assert raw == pytest.approx(taw * 0.5)


def test_explicit_taw_preserves_behavior():
    """تمرير taw_mm/raw_mm صراحةً ⇒ القيم كما هي + source=request (لا انحدار، لا اشتقاق)."""
    req = FieldWaterTwinRequest(taw_mm=120.0, raw_mm=60.0)
    taw, raw, meta = resolve_taw_raw(req, "قمح", 30)
    assert (taw, raw) == (120.0, 60.0)
    assert meta["taw_source"] == "request"
    assert meta["root_depth_m"] is None


def test_explicit_taw_default_raw_fraction():
    """taw_mm صريح بلا raw_mm ⇒ RAW = taw·raw_fraction، والمصدر يبقى request."""
    req = FieldWaterTwinRequest(taw_mm=100.0, raw_fraction=0.4)
    taw, raw, meta = resolve_taw_raw(req, "قمح", 30)
    assert (taw, raw) == (100.0, 40.0)
    assert meta["taw_source"] == "request"


def test_missing_card_without_taw_raises():
    """بطاقة محصول مفقودة + لا taw_mm ⇒ ValueError صادق (يصير 422 يطلب taw_mm)."""
    req = FieldWaterTwinRequest()  # لا taw_mm
    with pytest.raises(ValueError, match="taw_mm"):
        resolve_taw_raw(req, "نبات وهميّ", 30)
    with pytest.raises(ValueError, match="taw_mm"):
        resolve_taw_raw(req, None, 30)


def test_missing_age_without_taw_raises():
    """بطاقة موجودة لكن العمر مفقود (لا تاريخ زراعة) + لا taw_mm ⇒ ValueError يطلب taw_mm."""
    req = FieldWaterTwinRequest()
    with pytest.raises(ValueError, match="taw_mm"):
        resolve_taw_raw(req, "قمح", None)
