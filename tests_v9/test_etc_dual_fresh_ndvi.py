"""اختبار وحدة لجلب NDVI الطازج من COG في نقطة etc-dual — منطق اختيار المصدر بلا شبكة.

يقفل الصدق على سلّم الأولويّة الجديد: **تجاوز الطلب > COG طازج (real_data=true) > مخزَّن > none**.
المنطق النقيّ في ``_pick_ndvi`` يُختبَر مباشرةً؛ والجلب الخدميّ ``_fetch_fresh_ndvi`` يُختبَر
بـmock بسيط لردّ raster (real_data=true ⇒ stats.mean؛ real_data=false/تعذّر ⇒ تدرّج صامت None).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

# استيراد الراوتر يتطلّب تبعيّات المنصّة (fastapi/asyncpg…) ويُهيّئ api.main كاملاً. في وظيفة
# CI «Unit Tests» الأدنى (بلا api/requirements) تغيب هذه التبعيّات ⇒ نتخطّى الوحدة بصدق
# (تُغطّى في «Platform Unit Tests» الذي يُثبّت api/requirements) — نمط test_etc_dual_weather.
try:
    import api.main  # noqa: E402, F401 — تهيئة كاملة تسجّل الراوترات
    from api.routers import etc_dual  # noqa: E402
    from api.routers.etc_dual import EtcDualRequest, _fetch_fresh_ndvi, _pick_ndvi  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable (minimal Unit Tests env)", allow_module_level=True)


# ─── _pick_ndvi: سلّم الأولويّة النقيّ (تجاوز > طازج > مخزَّن > none) ──────────────


def test_pick_ndvi_request_override_wins():
    """تجاوز الطلب يسبق كلّ شيء (حتّى مع طازج ومخزَّن حاضرين)."""
    used, source = _pick_ndvi(req_ndvi=0.7, fresh_ndvi=0.6, stored_ndvi=0.5)
    assert used == 0.7
    assert source == "request"


def test_pick_ndvi_fresh_beats_stored():
    """بلا تجاوز ⇒ COG الطازج يسبق المخزَّن."""
    used, source = _pick_ndvi(req_ndvi=None, fresh_ndvi=0.62, stored_ndvi=0.41)
    assert used == 0.62
    assert source == "raster_fresh_cog"


def test_pick_ndvi_stored_when_no_fresh():
    """تعذّر الطازج (None) ⇒ تدرّج للمخزَّن."""
    used, source = _pick_ndvi(req_ndvi=None, fresh_ndvi=None, stored_ndvi=0.41)
    assert used == 0.41
    assert source == "imagery_automation_fields"


def test_pick_ndvi_none_when_nothing():
    """لا تجاوز ولا طازج ولا مخزَّن ⇒ none (تدرّج صادق لا اختلاق)."""
    used, source = _pick_ndvi(req_ndvi=None, fresh_ndvi=None, stored_ndvi=None)
    assert used is None
    assert source == "none"


def test_pick_ndvi_casts_to_float():
    """قيم int/Decimal-شبيهة تُحوَّل float (المخزَّن قد يأتي Decimal من القاعدة)."""
    used, source = _pick_ndvi(req_ndvi=None, fresh_ndvi=None, stored_ndvi=1)
    assert used == 1.0
    assert isinstance(used, float)
    assert source == "imagery_automation_fields"


# ─── _fetch_fresh_ndvi: الجلب الخدميّ (mock لواجهة raster) — صدق real_data ────────


def _patch_client(monkeypatch, *, payload=None, raise_exc=None, seen=None):
    """P2 raster facade: ``_fetch_fresh_ndvi`` يقرأ COG عبر ``get_indicator_grid`` (واجهة
    raster) بدل فتح ``httpx.AsyncClient`` محلّيّاً. نُرقِّع الواجهة كما تستوردها الوحدة،
    ونلتقط المستأجِر الممرَّر (W1-01: كلّ قراءة raster ترسل X-Tenant-Id)."""

    async def _fake_get_indicator_grid(
        field_id, *, tenant_id=None, index="ndvi", date="latest", timeout_s=8.0
    ):
        if seen is not None:
            seen.append(tenant_id)
        if raise_exc is not None:
            raise raise_exc
        return payload

    monkeypatch.setattr(etc_dual, "get_indicator_grid", _fake_get_indicator_grid)


def _observed(mean=0.63, *, acquired="2026-11-09T08:12:00Z", passed=True, field_id="field-1"):
    """ردّ indicator-grid لمنتجٍ مرصود: حكم raster (quality_gate_passed) + تاريخ الاقتناء."""
    return {
        "real_data": True,
        "field_id": field_id,
        "index": "ndvi",
        "grid": [[mean, mean], [mean, mean]],
        "stats": {"mean": mean},
        "indicator_product": {
            "quality_gate_passed": passed,
            "estimated": False,
            "provenance": {"acquisition_datetime": acquired},
        },
    }


async def test_fetch_fresh_ndvi_real_data_returns_mean_and_acquisition_date(monkeypatch):
    """منتجٌ مرصود ⇒ (stats.mean، تاريخ اقتناء المنتج) — لا date.today()."""
    seen: list = []
    _patch_client(monkeypatch, payload=_observed(), seen=seen)
    val, acquired = await _fetch_fresh_ndvi("field-1", "tenant-a")
    assert val == pytest.approx(0.63), f"المتوسّط المرصود لم يُرجَع: {val!r}"
    assert acquired is not None and acquired.isoformat() == "2026-11-09", (
        f"تاريخ NDVI يجب أن يكون تاريخ الاقتناء لا اليوم: {acquired!r}"
    )
    assert seen == ["tenant-a"], f"قراءة raster بلا X-Tenant-Id: {seen!r}"


async def test_fetch_fresh_ndvi_without_tenant_does_not_call_raster(monkeypatch):
    """بلا مستأجِر ⇒ لا نداء أصلاً (raster يحلّ الطبقات بالمستأجِر؛ fail-closed)."""
    seen: list = []
    _patch_client(monkeypatch, payload=_observed(), seen=seen)
    assert await _fetch_fresh_ndvi("field-1", None) == (None, None), "قراءة بلا مستأجِر قُبِلت"
    assert seen == [], f"نودِي raster بلا مستأجِر: {seen!r}"


async def test_fetch_fresh_ndvi_quality_gate_failed_returns_none(monkeypatch):
    """منتجٌ لم يجتز بوّابة جودة raster ⇒ لا يُستعمَل (حكم الخدمة نفسها)."""
    _patch_client(monkeypatch, payload=_observed(passed=False))
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), (
        "منتجٌ فاشل الجودة صار NDVI طازجاً"
    )


async def test_fetch_fresh_ndvi_other_field_product_returns_none(monkeypatch):
    """منتجٌ لحقلٍ آخر ⇒ يُرفَض (لا خلط هويّة)."""
    _patch_client(monkeypatch, payload=_observed(field_id="field-2"))
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), "منتج حقلٍ آخر قُبِل"


async def test_fetch_fresh_ndvi_without_acquisition_date_returns_none(monkeypatch):
    """بلا تاريخ اقتناء ⇒ لا يُدَّعى طازجاً (كان يُختلَق date.today())."""
    payload = _observed()
    payload["indicator_product"]["provenance"] = {}
    _patch_client(monkeypatch, payload=payload)
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), (
        "NDVI بلا تاريخ اقتناء قُبِل طازجاً"
    )


async def test_fetch_fresh_ndvi_simulation_returns_none(monkeypatch):
    """real_data=false (محاكاة) ⇒ None (لا نستخدم قيماً غير حقيقيّة — صدق)."""
    payload = _observed(0.5)
    payload["real_data"] = False
    _patch_client(monkeypatch, payload=payload)
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), "محاكاة قُبِلت"


async def test_fetch_fresh_ndvi_missing_mean_returns_none(monkeypatch):
    """منتجٌ مرصود لكن stats.mean مفقود ⇒ None (شكل ناقص ⇒ تدرّج)."""
    payload = _observed()
    payload["stats"] = {}
    _patch_client(monkeypatch, payload=payload)
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), "متوسّط مفقود قُبِل"


async def test_fetch_fresh_ndvi_network_error_returns_none(monkeypatch):
    """تعذّر شبكيّ ⇒ None (تدرّج صامت، لا خطأ يُعطّل النقطة)."""
    import httpx

    _patch_client(monkeypatch, raise_exc=httpx.ConnectError("boom"))
    assert await _fetch_fresh_ndvi("field-1", "tenant-a") == (None, None), "تعذّر شبكيّ لم يتدرّج"


# ─── علم prefer_fresh_ndvi (افتراضه True — يسمح بتعطيل الجلب الحيّ) ──────────────


def test_prefer_fresh_ndvi_defaults_true():
    """العلم يُمكِّن الجلب الحيّ افتراضيّاً (حفظ سلوك التحسين)."""
    assert EtcDualRequest().prefer_fresh_ndvi is True


def test_prefer_fresh_ndvi_can_disable():
    """يمكن تعطيله صراحةً (الاكتفاء بالمخزَّن)."""
    assert EtcDualRequest(prefer_fresh_ndvi=False).prefer_fresh_ndvi is False


# تأكيد أنّ المساعد الخدميّ معرَّف داخل الموجِّه (البصمة محصورة في etc_dual.py)
def test_fetch_helper_lives_in_router_module():
    assert _fetch_fresh_ndvi.__module__ == etc_dual.__name__
