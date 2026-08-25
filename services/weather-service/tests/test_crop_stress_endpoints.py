"""عقد النقاط الأربع للإجهاد المحصوليّ عبر **مسار الطلب**، لا عبر النوى النقيّة.

``test_crop_stress_products.py`` يستورد ``compute_*`` مباشرة، فيقيس المنطق ويترك
المُعالِج بلا شاهد. وبين المُعالِج والنواة كان يقبع سطرٌ ميّت:

    series = cache_get(key)      # cache.get تُعيد ثلاثيّة (value, state, age)
    if series is None:           # ثلاثيّةٌ ليست None أبداً ⇒ لا جلب ولا تخزين
    ...
    series.get("daily_max_c")    # ‹tuple› object has no attribute 'get' ⇒ 500

الثلاثيّة قائمة منذ ``017c035b``، والنقاط كُتبت بعدها (``b614b3ee`` و``ca91905f``،
2026-07-10) بالاصطلاح القديم — فلم تُعِد أيٌّ منها 200 قطّ منذ يوم كتابتها. مقيسٌ
بالتنفيذ لا بالقراءة، ولم يمسكه حارس: الأربعة كانت خارج كلّ اختبارٍ يبني ``TestClient``.

فالحارس هنا يقيس ثلاثة أشياء لا واحداً، لأنّ الإصلاح ثلاثة فروع لا فرعٌ واحد:
  (أ) مخبّأ بارد ⇒ 200 ومنتَجٌ حقيقيّ (يقتل عودة الاصطلاح القديم).
  (ب) مدخلة **طازجة** تُخدَم بلا جلبٍ ثانٍ (يقتل إسقاط شرط المخبّأ كلّه).
  (ج) مدخلة **بائتة** تُجدَّد ولا تُخدَم (يقتل ``if series is None`` وحدها — وهي
      الطفرة الوحيدة التي تنجو من (أ) و(ب) معاً: البائت ليس None فيُخدَم صامتاً).
"""

from __future__ import annotations

import importlib
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

pytestmark = pytest.mark.unit


# (المُعرِّف، المسار، المعاملات، اسم دالّة الجلب، حمولتان تُنتجان منتَجَين **مختلفَين**)
# اختلاف الحمولتين متعمَّد: عدّاد النداءات وحده لا يُثبِت أيّ سلسلةٍ استُهلكت فعلاً.
_CASES = [
    pytest.param(
        "/v1/weather/thermal-stress",
        {"lat": 15.0, "lon": 44.0, "crop": "tomato", "stage": "flowering", "days": 3},
        "fetch_thermal_series",
        (
            {"daily_max_c": [24.0, 25.0, 24.5], "daily_min_c": [18.0, 17.5, 18.2]},
            {"daily_max_c": [41.0, 42.0, 40.0], "daily_min_c": [6.0, 5.0, 7.0]},
        ),
        id="thermal-stress",
    ),
    pytest.param(
        "/v1/weather/lodging-risk",
        {"lat": 15.0, "lon": 44.0, "crop": "wheat", "stage": "grain_filling", "days": 3},
        "fetch_daily_wind_temp_rain",
        (
            {
                "wind_gust_max_mps": [3.0],
                "wind_speed_max_mps": [2.0],
                "precip_sum_mm": [0.0],
                "daily_max_c": [26.0],
                "daily_min_c": [15.0],
            },
            {
                "wind_gust_max_mps": [25.0],
                "wind_speed_max_mps": [18.0],
                "precip_sum_mm": [30.0],
                "daily_max_c": [26.0],
                "daily_min_c": [15.0],
            },
        ),
        id="lodging-risk",
    ),
    pytest.param(
        "/v1/weather/pollination-risk",
        {"lat": 15.0, "lon": 44.0, "crop": "maize", "stage": "flowering", "days": 3},
        "fetch_daily_wind_temp_rain",
        (
            {
                "daily_max_c": [26.0],
                "daily_min_c": [15.0],
                "wind_speed_max_mps": [2.0],
                "wind_gust_max_mps": [3.0],
                "precip_sum_mm": [0.0],
            },
            {
                "daily_max_c": [42.0],
                "daily_min_c": [6.0],
                "wind_speed_max_mps": [14.0],
                "wind_gust_max_mps": [20.0],
                "precip_sum_mm": [25.0],
            },
        ),
        id="pollination-risk",
    ),
    pytest.param(
        "/v1/weather/chill-accumulation",
        {
            "lat": 36.0,
            "lon": 44.0,
            "crop": "almond",
            "start_date": "2025-12-01",
            "end_date": "2025-12-02",
        },
        "fetch_archive_hourly_temps",
        ({"hourly_temp_c": [20.0] * 48}, {"hourly_temp_c": [5.0] * 48}),
        id="chill-accumulation",
    ),
]


@pytest.fixture(autouse=True)
def memory_cache_only(monkeypatch):
    """مخبّأ الذاكرة حصراً ومُفرَغ: بوّابة CI بلا Redis، والإبقاء صريحٌ لا مصادفة.

    (لو تُرك للبيئة، لصار (ج) — تعتيقُ المدخلات — بلا أثرٍ حين يوجد Redis، فيمرّ
    الاختبار بلا أن يقيس شيئاً.)
    """
    monkeypatch.setattr(cache, "REDIS_URL", None)
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    cache._CACHE.clear()
    yield
    cache._CACHE.clear()


def _stub_fetch(monkeypatch, attr: str, payloads: tuple[dict, ...]) -> list[int]:
    """يستبدل الجلب الشبكيّ بحمولاتٍ متتابعة، ويُعيد عدّاداً بنداءٍ واحدٍ لكلّ عنصر."""
    calls = [0]

    async def fake(*_args, **_kwargs):
        payload = payloads[min(calls[0], len(payloads) - 1)]
        calls[0] += 1
        return dict(payload)

    monkeypatch.setattr(rt, attr, fake)
    return calls


def _age_every_entry_past_ttl() -> None:
    """يُعتِّق كلّ مدخلة إلى ما بعد TTL وقبل STALE_TTL ⇒ الحالة ``stale``.

    التعتيق يقع على المخبّأ لا على المفاتيح: نسخُ صيغة المفتاح إلى الاختبار يجعله
    مرآةً للإنتاج تنكسر بصمت عند أوّل تغيير في الصيغة.
    """
    older = monotonic() - (cache.TTL_S + 60.0)
    for key, (_ts, value) in list(cache._CACHE.items()):
        cache._CACHE[key] = (older, value)


@pytest.mark.parametrize(("path", "params", "fetch_attr", "payloads"), _CASES)
def test_endpoint_answers_with_a_product_on_a_cold_cache(
    monkeypatch, path, params, fetch_attr, payloads
):
    """العطل الأصليّ: 500 على **كلّ** نداء لأنّ الثلاثيّة لا تُفكَّك."""
    calls = _stub_fetch(monkeypatch, fetch_attr, payloads)
    with TestClient(main.app) as client:
        response = client.get(path, params=params)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert "provenance" in body
    assert calls[0] == 1, "مخبّأ بارد ⇒ جلبٌ واحد بالضبط"


@pytest.mark.parametrize(("path", "params", "fetch_attr", "payloads"), _CASES)
def test_a_fresh_entry_is_served_without_a_second_fetch(
    monkeypatch, path, params, fetch_attr, payloads
):
    """الحمولة الثانية مختلفة عمداً: تطابقُ الجسمين يُثبِت أنّ المخبّأ هو من أجاب."""
    calls = _stub_fetch(monkeypatch, fetch_attr, payloads)
    with TestClient(main.app) as client:
        first = client.get(path, params=params)
        second = client.get(path, params=params)

    assert first.status_code == second.status_code == 200
    assert calls[0] == 1, "مدخلة طازجة ومع ذلك جُلبت ثانيةً — المخبّأ بلا أثر"
    assert second.json() == first.json()


@pytest.mark.parametrize(("path", "params", "fetch_attr", "payloads"), _CASES)
def test_a_stale_entry_is_refreshed_and_not_served(monkeypatch, path, params, fetch_attr, payloads):
    """البائت ليس ``None`` — فحصُ ``series is None`` وحده يخدمه صامتاً بلا تجديد."""
    calls = _stub_fetch(monkeypatch, fetch_attr, payloads)
    with TestClient(main.app) as client:
        first = client.get(path, params=params)
        _age_every_entry_past_ttl()
        second = client.get(path, params=params)

    assert first.status_code == second.status_code == 200
    assert calls[0] == 2, "مدخلة بائتة خُدِمت بلا تجديد"
    assert second.json() != first.json(), "الجواب الثاني لم يُبنَ على السلسلة المُجدَّدة"
