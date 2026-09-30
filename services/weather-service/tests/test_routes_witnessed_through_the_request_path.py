"""المسارات التي لم يُسمِّها أيُّ اختبار — تُشهَد الآن عبر **مسار الطلب** لا النواة.

``SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01``: اختباراتُ الخدمة كانت تستورد
``compute_*``/``build_*`` مباشرةً، فتشهد للحساب وتترك ما بين الطلب والنواة: تفكيكَ الجسم
إلى نموذج الطلب · المخبّأ · الجلب · تحويلَ الفشل إلى رمز حالة. وهذا بالضبط حيث وقع عطلُ
النقاط الأربع للإجهاد المحصوليّ (``test_crop_stress_endpoints.py``: 500 على كلّ نداءٍ منذ
يوم كتابتها، والنواةُ خضراء).

**المقيس على ``bcb7f0ed`` قبل هذا الملفّ** (بادئةُ كلّ مسارٍ مُسجَّلٍ في ``main.py`` قبل
``{``، مبحوثةً في نصّ ``tests/*.py``): ٢٩ مساراً، **٨ لا يُسمِّيها أيُّ اختبار** —
``/healthz`` · ``/health`` · ``/metrics`` · ``/runtime-identity`` ·
``POST agro/etc/hourly`` · ``POST agro/canonical-state`` · ``POST agro/state-report`` ·
``GET cache-stats``. (السجلُّ قال ستّة على ٢٧ مساراً؛ ``/metrics`` و``/runtime-identity``
أُضيفا بعد قياسه.) كلُّ اختبارٍ هنا يبني ``TestClient(main.app)`` الحقيقيّ.

والاختبارُ الأخير في ``test_every_registered_route_is_named_by_a_test.py`` يمنع عودة
الصنف: مسارٌ جديد بلا شاهد يُحمِر الجناحَ نفسَه الذي تُشغّله وظيفة *Weather Service Unit
Tests* — راتشِتٌ أساسُه صفر، لا حارسٌ عامّ جديد.
"""

from __future__ import annotations

import functools
import importlib
import json
import os
import sys
from time import monotonic

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

import cache  # noqa: E402

main = importlib.import_module("main")
rt = importlib.import_module("weather_runtime")

from canonical_weather_state import (  # noqa: E402
    build_canonical_weather_state,
    weather_state_report,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def memory_cache_only(monkeypatch):
    """مخبّأ الذاكرة حصراً ومُفرَغ — وإلّا صار عدُّ المدخلات وقياسُ «طازج/بائت» رهنَ البيئة."""
    monkeypatch.setattr(cache, "REDIS_URL", None)
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    monkeypatch.setattr(cache, "_REDIS_ERROR", None)
    cache._CACHE.clear()
    yield
    cache._CACHE.clear()


@pytest.fixture
def client():
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


# ── صحّة العمليّة ───────────────────────────────────────────────────────────


def test_healthz_and_its_legacy_alias_answer_the_same_body(client):
    live = client.get("/healthz")
    legacy = client.get("/health")
    assert live.status_code == legacy.status_code == 200
    assert live.json() == {"status": "ok", "service": "weather-service", "mode": "runtime"}
    # الاسمُ القديم يجب أن يبقى **اسماً مستعاراً** — لا نسخةً تنحرف بصمت.
    assert legacy.json() == live.json()


def test_metrics_answers_prometheus_exposition_not_404(client):
    """الهدفُ مُعلَنٌ في `prometheus/prometheus.yml`؛ غيابُ النقطة كان يعني `up=0` دائماً."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE " in response.text


def test_runtime_identity_serves_the_image_file_and_never_invents_one(
    client, tmp_path, monkeypatch
):
    import shared.runtime_identity as runtime_identity

    # (أ) لا ملفَّ بناءٍ في هذه البيئة ⇒ فشلٌ مغلق، لا هويّةٌ مُختلَقة من البيئة.
    missing = functools.partial(
        runtime_identity.load_build_identity, metadata_path=tmp_path / "absent.json"
    )
    monkeypatch.setattr(runtime_identity, "load_build_identity", missing)
    assert client.get("/runtime-identity").status_code == 500

    # (ب) ملفٌّ صالح ⇒ الجوابُ منه حرفيّاً، واسمُ الخدمة هو ما يطلبه المسار نفسُه.
    metadata = tmp_path / "build.json"
    metadata.write_text(
        json.dumps(
            {"service": "weather-service", "git_sha": "a" * 40, "build_id": "build-20260930-1"}
        ),
        encoding="utf-8",
    )
    original = missing.func
    monkeypatch.setattr(
        runtime_identity,
        "load_build_identity",
        functools.partial(original, metadata_path=metadata),
    )
    response = client.get("/runtime-identity")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["service"] == "weather-service"
    assert body["git_sha"] == "a" * 40
    assert body["metadata_source"] == "immutable-image-file"


# ── ETc الساعيّ: الجسم ⇒ النموذج ⇒ المخبّأ ⇒ الجلب ⇒ رمز الحالة ────────────────


def _provider(hours: int = 3) -> dict:
    return {
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": [f"2026-07-14T{h:02d}:00" for h in range(hours)],
            "et0_fao_evapotranspiration": [0.2, 0.3, 0.4][:hours],
            "precipitation": [0.0, 1.0, 0.0][:hours],
        },
    }


_ETC_BODY = {
    "lat": 15.0,
    "lon": 44.0,
    "horizon_hours": 3,
    "daily_kc_by_date": {"2026-07-14": 0.8},
    "daily_runoff_mm_by_date": {"2026-07-14": 0.2},
}


def _stub_hourly_fetch(monkeypatch, *payloads, error: Exception | None = None) -> list[dict]:
    """يستبدل الجلبَ الشبكيّ ويُسجّل **مُعاملاتِه** — العدُّ وحده لا يُثبت ما طُلِب."""
    calls: list[dict] = []

    async def fake(lat, lon, *, horizon_hours, model):
        calls.append({"lat": lat, "lon": lon, "horizon_hours": horizon_hours, "model": model})
        if error is not None:
            raise error
        return payloads[min(len(calls) - 1, len(payloads) - 1)]

    monkeypatch.setattr(rt, "fetch_hourly_fao_et0_precipitation", fake)
    return calls


def test_hourly_etc_cold_cache_fetches_once_and_returns_the_verified_product(client, monkeypatch):
    calls = _stub_hourly_fetch(monkeypatch, _provider())
    response = client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "verified"
    assert body["cache_state"] == "refreshed"
    assert [h["etc_mm"] for h in body["hours"]] == [0.16, 0.24, 0.32]
    # الجسمُ وصل الجلبَ كما أُرسِل: الأفقُ والنموذجُ الافتراضيّ لم يُفقَدا في التفكيك.
    assert calls == [{"lat": 15.0, "lon": 44.0, "horizon_hours": 3, "model": "best_match"}]


def test_hourly_etc_fresh_entry_is_served_without_a_second_fetch(client, monkeypatch):
    calls = _stub_hourly_fetch(monkeypatch, _provider())
    first = client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)
    second = client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)

    assert first.status_code == second.status_code == 200
    assert len(calls) == 1, "مدخلة طازجة ومع ذلك جُلبت ثانيةً — المخبّأ بلا أثر"
    assert second.json()["cache_state"] == "fresh"
    assert second.json()["hours"] == first.json()["hours"]


def test_hourly_etc_stale_entry_is_refetched_not_served(client, monkeypatch):
    calls = _stub_hourly_fetch(monkeypatch, _provider())
    client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)
    older = monotonic() - (cache.TTL_S + 60.0)
    for key, (_ts, value) in list(cache._CACHE.items()):
        cache._CACHE[key] = (older, value)
    again = client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)

    assert again.status_code == 200
    assert len(calls) == 2, "مدخلة بائتة خُدِمت بلا تجديد"
    assert again.json()["cache_state"] == "refreshed"


def test_hourly_etc_rejects_out_of_range_coordinates_before_any_fetch(client, monkeypatch):
    calls = _stub_hourly_fetch(monkeypatch, _provider())
    response = client.post("/v1/weather/agro/etc/hourly", json={**_ETC_BODY, "lat": 91.0})
    assert response.status_code == 422
    assert calls == []


def test_hourly_etc_upstream_failure_is_502_not_a_fabricated_product(client, monkeypatch):
    _stub_hourly_fetch(monkeypatch, error=RuntimeError("open-meteo down"))
    response = client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY)
    assert response.status_code == 502
    assert "open-meteo down" in response.json()["detail"]
    assert cache._CACHE == {}, "فشلُ المنبع لا يُخزَّن"


def test_hourly_etc_blocked_product_is_424_and_is_not_cached(client, monkeypatch):
    """Kc ناقص ⇒ النواة تُعيد `blocked`؛ والمسارُ يجب أن يُعلنه 424 ولا يخبّئه فيُخدَم لاحقاً."""
    calls = _stub_hourly_fetch(monkeypatch, _provider())
    body = {**_ETC_BODY, "daily_kc_by_date": {}}
    first = client.post("/v1/weather/agro/etc/hourly", json=body)
    second = client.post("/v1/weather/agro/etc/hourly", json=body)

    assert first.status_code == second.status_code == 424
    assert first.json()["detail"]["reason"] == "canonical_hourly_etc_input_incomplete"
    assert len(calls) == 2, "منتَجٌ محجوب خُبِّئ فخُدِم بلا جلب"


# ── الحالة الموحَّدة وتقريرها: الجوابُ هو النواةُ نفسُها بلا تحويرٍ في الطريق ──────

_FULL = {
    "t_max_c": 34.0,
    "t_min_c": 18.0,
    "rh_mean_pct": 45.0,
    "wind_2m_ms": 2.0,
    "solar_rad_mj_m2": 22.0,
    "lat_deg": 15.5,
    "elevation_m": 2000.0,
    "day_of_year": 100,
    "gdd_daily_t_min": [16.0, 18.0],
    "gdd_daily_t_max": [30.0, 32.0],
    "gdd_base_c": 10.0,
    "valid_time": "2026-07-11T09:00:00Z",
}


def _core_state(**overrides) -> dict:
    request = rt.CanonicalWeatherStateRequest(**{**_FULL, **overrides})
    return build_canonical_weather_state(**request.model_dump())


def test_canonical_state_route_answers_exactly_what_the_core_builds(client):
    response = client.post("/v1/weather/agro/canonical-state", json=_FULL)
    assert response.status_code == 200, response.text
    # الموازنةُ مع النواة لا مع قيمٍ منسوخة: الاختبارُ يشهد للطريق لا للحساب، فلا ينكسر
    # حين تتغيّر النواةُ بحقّ — ويحمرّ حين يُسقِط الطريقُ حقلاً من الجسم.
    assert response.json() == json.loads(json.dumps(_core_state()))
    assert response.json()["generated_at"] == _FULL["valid_time"]


def test_canonical_state_route_does_not_drop_a_body_field_on_the_way(client):
    """حقلٌ واحد يُغيّر الحالة ⇒ يجب أن يُغيّر جوابَ المسار أيضاً (يقتل إسقاطَه في `_build_state`)."""
    base = client.post("/v1/weather/agro/canonical-state", json=_FULL).json()
    for field, value in (
        ("t_max_c", 40.0),
        ("gdd_base_c", 5.0),
        ("valid_time", "2026-07-12T09:00:00Z"),
    ):
        changed = client.post("/v1/weather/agro/canonical-state", json={**_FULL, field: value})
        assert changed.status_code == 200
        # الجوابُ كلُّه لا `state_id` وحده: سياسةُ GDD لا تدخل مُعرِّفَ اللقطة (مقيس).
        assert changed.json() != base, f"{field} لم يبلغ النواة"
        assert changed.json() == json.loads(json.dumps(_core_state(**{field: value})))


def test_canonical_state_rejects_a_malformed_body_with_422(client):
    assert (
        client.post("/v1/weather/agro/canonical-state", json={"t_max_c": "hot"}).status_code == 422
    )


def test_state_report_route_reads_the_state_not_the_engine(client):
    response = client.post("/v1/weather/agro/state-report", json=_FULL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == json.loads(json.dumps(weather_state_report(_core_state())))
    assert body["state_id"] == _core_state()["state_id"]
    assert (
        client.post("/v1/weather/agro/state-report", json={"day_of_year": "x"}).status_code == 422
    )


# ── إحصاءُ المخبّأ: يعكس المخبّأ الذي تُكتب فيه المسارات الأخرى فعلاً ───────────────


def test_cache_stats_reports_the_backend_and_counts_real_entries(client, monkeypatch):
    before = client.get("/v1/weather/cache-stats")
    assert before.status_code == 200
    assert before.json() == {
        "backend": "memory",
        "ttl_s": int(cache.TTL_S),
        "stale_ttl_s": int(cache.STALE_TTL_S),
        "redis_configured": False,
        "entries": 0,
    }
    _stub_hourly_fetch(monkeypatch, _provider())
    assert client.post("/v1/weather/agro/etc/hourly", json=_ETC_BODY).status_code == 200
    assert client.get("/v1/weather/cache-stats").json()["entries"] == 1
