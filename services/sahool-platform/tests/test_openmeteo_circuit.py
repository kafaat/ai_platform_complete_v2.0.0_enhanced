"""
tests/test_openmeteo_circuit.py — تكامل القاطع مع موصِّل Open-Meteo (دون شبكة).

يؤكّد:
  - الاستيراد وaccessor الحالة يعملان.
  - عند فتح القاطع قسراً ← fail-fast بنفس نوع الاستثناء المنبعيّ
    (httpx.RequestError) فيُحفَظ تعامل 503 لدى المتّصلين.
  - أخطاء HTTP المنبعيّة المتكرّرة تفتح القاطع (عبر respx، بلا شبكة حقيقيّة).
  - النجاح يُبقي القاطع مغلقاً ويُصفّر العدّاد.
"""

import api.connectors.openmeteo as om
import httpx
import pytest
import respx

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_breaker():
    """يضمن قاطعاً نظيفاً قبل/بعد كلّ اختبار (حالة مشتركة على مستوى الوحدة)."""
    om._OPENMETEO_BREAKER.reset()
    yield
    om._OPENMETEO_BREAKER.reset()


def test_import_and_accessor():
    snap = om.openmeteo_breaker_state()
    assert snap["name"] == "openmeteo"
    assert snap["state"] == "closed"
    assert "consecutive_failures" in snap


def test_public_api_unchanged():
    # التواقيع العامّة + الدوالّ ما زالت موجودة (توافق خلفيّ).
    for fn in (
        "fetch_current",
        "fetch_daily_forecast",
        "fetch_historical",
        "fetch_current_batch",
        "fetch_bundle",
    ):
        assert callable(getattr(om, fn))


@pytest.mark.asyncio
async def test_fail_fast_when_breaker_open():
    # افتح القاطع قسراً.
    om._OPENMETEO_BREAKER._open()
    assert om.openmeteo_breaker_state()["state"] == "open"

    # يجب أن يفشل سريعاً بنفس عائلة استثناء العطل المنبعيّ التي يلتقطها
    # المتّصلون (ConnectError ⊂ RequestError) — دون لمس الشبكة.
    with pytest.raises(httpx.RequestError) as exc:
        await om.fetch_current(16.15, 45.30)
    assert "circuit open" in str(exc.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_repeated_upstream_failures_open_breaker():
    route = respx.get(om.FORECAST_URL).mock(return_value=httpx.Response(503))
    threshold = om._OPENMETEO_BREAKER.failure_threshold

    # كلّ استدعاء يرفع HTTPStatusError (عطل منبعيّ) ويزيد العدّاد.
    for _ in range(threshold):
        with pytest.raises(httpx.HTTPStatusError):
            await om.fetch_current(16.15, 45.30)

    assert om.openmeteo_breaker_state()["state"] == "open"
    calls_before = route.call_count

    # الآن fail-fast بلا أيّ طلب شبكة إضافيّ.
    with pytest.raises(httpx.RequestError):
        await om.fetch_current(16.15, 45.30)
    assert route.call_count == calls_before  # لم يُلمَس المنبع


@pytest.mark.asyncio
@respx.mock
async def test_success_keeps_breaker_closed():
    payload = {"current": {"temperature_2m": 41.0, "time": "2026-06-16T12:00"}}
    respx.get(om.FORECAST_URL).mock(return_value=httpx.Response(200, json=payload))

    # سجّل فشلاً منبعيّاً واحداً ثمّ نجاحاً — يجب أن يبقى مغلقاً والعدّاد يُصفَّر.
    om._OPENMETEO_BREAKER.record_failure()
    assert om.openmeteo_breaker_state()["consecutive_failures"] == 1

    res = await om.fetch_current(16.15, 45.30)
    assert res.temperature_c == 41.0
    snap = om.openmeteo_breaker_state()
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 0
