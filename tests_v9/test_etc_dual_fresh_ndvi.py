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


def _patch_client(monkeypatch, *, payload=None, raise_exc=None):
    """P2 raster facade: ``_fetch_fresh_ndvi`` يقرأ COG عبر ``get_indicator_grid`` (واجهة
    raster) بدل فتح ``httpx.AsyncClient`` محلّيّاً. نُرقِّع الواجهة كما تستوردها الوحدة —
    النيّة محفوظة: real_data=true ⇒ stats.mean؛ محاكاة/شكل ناقص/تعذّر ⇒ None."""

    async def _fake_get_indicator_grid(
        field_id, *, tenant_id=None, index="ndvi", date="latest", timeout_s=8.0
    ):
        if raise_exc is not None:
            raise raise_exc
        return payload

    monkeypatch.setattr(etc_dual, "get_indicator_grid", _fake_get_indicator_grid)


async def test_fetch_fresh_ndvi_real_data_returns_mean(monkeypatch):
    """real_data=true ⇒ يُرجِع stats.mean كـfloat (الطازج الحقيقيّ)."""
    _patch_client(monkeypatch, payload={"real_data": True, "stats": {"mean": 0.63}})
    val = await _fetch_fresh_ndvi("field-1")
    assert val == pytest.approx(0.63)


async def test_fetch_fresh_ndvi_simulation_returns_none(monkeypatch):
    """real_data=false (محاكاة) ⇒ None (لا نستخدم قيماً غير حقيقيّة — صدق)."""
    _patch_client(monkeypatch, payload={"real_data": False, "stats": {"mean": 0.5}})
    assert await _fetch_fresh_ndvi("field-1") is None


async def test_fetch_fresh_ndvi_missing_mean_returns_none(monkeypatch):
    """real_data=true لكن stats.mean مفقود ⇒ None (شكل ناقص ⇒ تدرّج)."""
    _patch_client(monkeypatch, payload={"real_data": True, "stats": {}})
    assert await _fetch_fresh_ndvi("field-1") is None


async def test_fetch_fresh_ndvi_network_error_returns_none(monkeypatch):
    """تعذّر شبكيّ ⇒ None (تدرّج صامت، لا خطأ يُعطّل النقطة)."""
    import httpx

    _patch_client(monkeypatch, raise_exc=httpx.ConnectError("boom"))
    assert await _fetch_fresh_ndvi("field-1") is None


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
