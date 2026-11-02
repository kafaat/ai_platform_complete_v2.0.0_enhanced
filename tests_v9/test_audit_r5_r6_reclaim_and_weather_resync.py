"""شواهد انحدار R5/R6 (تدقيق المصدر 2026-11-01) — بلا خدمات حيّة، والحدودُ دوالٌّ مُرقَّعة.

R5: نيّةُ إبطال كاش الراستر العالقة في ``running`` (عاملٌ مات بين المطالبة والإنهاء)
    لم تكن تُطالَب ثانيةً أبداً. الاستعادةُ نفسُها SQL فتُقاس على Postgres حيّ في
    ``test_d1_raster_invalidation_owner_api_integration.py``؛ وهنا الشطرُ البايثونيّ:
    الاستعادةُ تَعُدّ المحاولةَ الضائعة، والمستنفَدةُ تنتهي ``failed`` بلا إرسال.
R6: مجموعةُ مواقع الطقس كانت تُبنى مرّةً عند الإقلاع (``load_from_db``)، فالحقلُ
    المُنشَأ بعده لا يُسحَب طقسُه حتّى إعادة التشغيل، والمحذوفُ يبقى يُسحَب.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
pytestmark = pytest.mark.unit

if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


# ── R5: حدُّ المحاولات بعد الاستعادة ─────────────────────────────────────────


def _reclaimed_job(attempts: int) -> dict:
    return {
        "id": 7,
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "field_id": "f1",
        "parameters": '{"request_id": "field.geometry.updated:f1:rev1", "reason": "r"}',
        "result": (
            '{"lease": {"token": "tok", "expires_at": "2026-11-02"}, '
            f'"reclaimed": true, "attempts": {attempts}}}'
        ),
    }


async def test_reclaimed_intent_that_exhausted_its_attempts_fails_without_sending(monkeypatch):
    from api import spatial_sync

    finish = AsyncMock(return_value="failed")
    monkeypatch.setattr(spatial_sync, "_finish", finish)
    send = AsyncMock()

    outcome = await spatial_sync.deliver(None, _reclaimed_job(spatial_sync.MAX_ATTEMPTS), send=send)

    assert outcome == "failed"
    send.assert_not_awaited()
    kwargs = finish.await_args.kwargs
    assert kwargs["status"] == "failed"
    assert kwargs["attempts"] == spatial_sync.MAX_ATTEMPTS
    assert "lease expired" in kwargs["error"]
    assert finish.await_args.args[2] == "tok", "الإنهاءُ CAS على رمز الإجارة الجديدة"


async def test_reclaimed_intent_with_attempts_left_is_redelivered_with_the_same_key(monkeypatch):
    from api import spatial_sync

    finish = AsyncMock(return_value="delivered")
    monkeypatch.setattr(spatial_sync, "_finish", finish)
    send = AsyncMock(return_value={"accepted": True, "deduplicated": True})

    outcome = await spatial_sync.deliver(None, _reclaimed_job(1), send=send)

    assert outcome == "delivered"
    assert send.await_args.kwargs["request_id"] == "field.geometry.updated:f1:rev1"
    assert finish.await_args.kwargs == {
        "status": "completed",
        "attempts": 2,
        "ack": {"accepted": True, "deduplicated": True},
    }


def test_claim_statement_reclaims_running_rows_and_counts_the_lost_attempt():
    """الحارسُ البنيويّ للعبارة؛ دلالتُها تُقاس حيّةً في اختبار التكامل."""
    import inspect

    from api import spatial_sync

    src = inspect.getsource(spatial_sync.claim_due)
    assert "status = 'running'" in src, "R5: running منتهي الإجارة لا يُطالَب ⇒ عالقٌ للأبد"
    assert "'reclaimed', j.status = 'running'" in src
    assert "THEN 1 ELSE 0 END" in src, "الاستعادةُ بلا عَدٍّ للمحاولة ⇒ لا حدَّ لها"


# ── R6: مزامنةُ مواقع الطقس من القاعدة عند كلّ تكّة ──────────────────────────


def _row(lat: float, lon: float, field_id: str | None) -> dict:
    return {"location_key": f"{lat},{lon}", "lat": lat, "lon": lon, "field_id": field_id}


@pytest.fixture
def weather(monkeypatch):
    """أتمتةُ طقسٍ بمسبحٍ حارس (لا يُستعمَل) وحدودُ I/O مُرقَّعة: القراءة والحفظ والمزوّد."""
    from api.weather_automation import WeatherAutomation

    fetched: list[tuple[float, float]] = []

    async def _fetch_current(lat, lon):
        fetched.append((lat, lon))
        return SimpleNamespace(
            temperature_c=30.0,
            humidity_pct=20.0,
            wind_speed_ms=2.0,
            precipitation_mm=0.0,
            cloud_cover_pct=0.0,
            weather_code=0,
            timestamp="2026-11-02T00:00",
        )

    monkeypatch.setitem(
        sys.modules,
        "api.connectors.openmeteo",
        SimpleNamespace(fetch_current=_fetch_current, describe_weather_ar=lambda c: "صحو"),
    )
    wa = WeatherAutomation()
    wa.set_pool(object())
    wa._fetch_tracked_rows = AsyncMock()
    wa._persist_cache = AsyncMock()
    return wa, fetched


async def test_field_created_after_start_enters_the_schedule_on_the_next_tick(weather):
    wa, fetched = weather
    wa._fetch_tracked_rows.return_value = [_row(15.0, 44.0, "f1")]
    await wa.load_from_db()
    assert wa.registered_count() == 1

    # حقلٌ أُنشئ بعد الإقلاع: صفُّه في القاعدة، وليس في الذاكرة.
    wa._fetch_tracked_rows.return_value = [_row(15.0, 44.0, "f1"), _row(16.0, 45.0, "f2")]
    result = await wa.refresh_all()

    assert (16.0, 45.0) in fetched, "R6: الحقلُ الجديد لا يُسحَب طقسُه حتّى إعادة التشغيل"
    assert result["refreshed"] == 2
    assert wa.registered_count() == 2
    assert wa.get_cached(16.0, 45.0) is not None


async def test_location_deleted_from_the_db_leaves_the_schedule_and_its_cache(weather):
    wa, fetched = weather
    wa._fetch_tracked_rows.return_value = [_row(15.0, 44.0, "f1"), _row(16.0, 45.0, "f2")]
    await wa.refresh_all()
    assert wa.get_cached(15.0, 44.0) is not None

    wa._fetch_tracked_rows.return_value = [_row(16.0, 45.0, "f2")]  # صفُّ f1 حُذف
    fetched.clear()
    result = await wa.refresh_all()

    assert fetched == [(16.0, 45.0)], "موقعٌ محذوف ما زال يُسحَب طقسُه"
    assert result["refreshed"] == 1
    assert wa.registered_count() == 1
    assert wa.get_cached(15.0, 44.0) is None


async def test_resync_never_duplicates_and_a_failed_read_keeps_the_current_set(weather):
    wa, fetched = weather
    # الخليّةُ المُقرَّبة نفسُها مرّتين ⇒ موقعٌ واحد، وتكّتان ⇒ لا ازدواج.
    wa._fetch_tracked_rows.return_value = [_row(15.0, 44.0, "f1"), _row(15.0001, 44.0001, "f9")]
    await wa.refresh_all()
    await wa.refresh_all()
    assert wa.registered_count() == 1
    assert len(fetched) == 2

    wa._fetch_tracked_rows.side_effect = RuntimeError("db down")
    fetched.clear()
    result = await wa.refresh_all()
    assert wa.registered_count() == 1, "قراءةٌ فاشلة لا تمحو الجدولة"
    assert result["refreshed"] == 1
