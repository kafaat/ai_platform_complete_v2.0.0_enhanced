"""عرضُ التغطية على نقطة الأرشيف: المطلوبُ يُقارَن بالمرصود، لا بنفسه.

`range` في السلسلة المُطبَّعة مُشتقٌّ من **أوقات المزوّد** (`open_meteo.normalize_daily`).
فسلسلةٌ مبتورة تصف مداها الخاصّ وتبدو كاملة، ولا شيءَ في الجواب يقول إنّ ما طُلِب أوسع.

مقيسٌ بالتنفيذ قبل الإصلاح: **عشرةُ أيّام مطلوبة · ثلاثةٌ مُعادة ⇒ `quality_status:
validated`** ولا حقلَ تغطيةٍ إطلاقاً. والمُعالِج يعرف المطلوب (`start_date`/`end_date`
معاملان في التوقيع) ولم يكن يُمرّره — **فالفجوةُ في التمرير لا في الحساب**.

والحسابُ مبنيٌّ في الشجرة منذ WX-10.4: `gdd_view` يُخرِج
`period/expected/observed/missing/coverage_ratio` بنصّه «لا يُحتسَب يوم مفقود صفراً؛
لا سلسلة ناقصة تُعطى validated». وهذه الشريحة **تعرضه على النقطة** ولا تبني حساباً
ثانياً: نفسُ `_expected_days_inclusive` ونفسُ المفاتيح ونفسُ مفردة الجودة
(`degraded_incomplete_coverage`) — لا مفردةَ ثانية لنفس المعنى.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

from canonical_weather_state import build_canonical_weather_state, historical_view  # noqa: E402
from open_meteo import normalize_daily  # noqa: E402

main = importlib.import_module("main")
rt = importlib.import_module("weather_runtime")

pytestmark = pytest.mark.unit


def _archive_series(day_count: int) -> dict:
    days = [f"2026-03-{i + 1:02d}" for i in range(day_count)]
    payload = {
        "daily": {
            "time": days,
            "temperature_2m_max": [30.0] * day_count,
            "temperature_2m_min": [18.0] * day_count,
            "precipitation_sum": [0.0] * day_count,
            "et0_fao_evapotranspiration": [4.1] * day_count,
            "wind_speed_10m_max": [10.0] * day_count,
            "weather_code": [0] * day_count,
        },
        "timezone": "Asia/Aden",
    }
    return normalize_daily(payload, lat=15.0, lon=44.0, source="open-meteo-archive", model="ERA5")


def _view(day_count: int, start: str | None, end: str | None) -> dict:
    series = _archive_series(day_count)
    state = build_canonical_weather_state(
        lat_deg=15.0,
        valid_time=(series.get("range") or {}).get("start"),
        historical_series=series,
    )
    return historical_view(state, requested_start=start, requested_end=end)


# ── ① الفجوة المقيسة: سلسلةٌ مبتورة كانت تُعلَن validated ──────────────
def test_a_truncated_archive_series_is_no_longer_declared_validated():
    view = _view(3, "2026-03-01", "2026-03-10")

    assert view["quality_status"] == "degraded_incomplete_coverage"
    assert view["coverage"]["expected_days"] == 10
    assert view["coverage"]["observed_days"] == 3
    assert view["coverage"]["missing_days"] == 7
    assert view["coverage"]["coverage_ratio"] == 0.3


def test_the_gap_is_named_in_the_limitations_not_left_to_inference():
    """`coverage_ratio` رقمٌ يقرؤه آلة؛ والقيدُ يقرؤه إنسانٌ يُشخِّص حادثة."""
    view = _view(3, "2026-03-01", "2026-03-10")

    named = [lim for lim in view["limitations"] if "requested 10 day(s)" in lim]
    assert named, "الفجوةُ رقمٌ بلا جملةٍ تصفه"
    assert "observed 3" in named[0]
    assert "7 day(s) absent" in named[0]


def test_a_complete_series_keeps_its_quality_and_reports_full_coverage():
    """ضبطٌ: لولاه لمرّ «degraded دائماً» بوصفه إصلاحاً."""
    view = _view(10, "2026-03-01", "2026-03-10")

    assert view["quality_status"] == "validated"
    assert view["coverage"]["coverage_ratio"] == 1.0
    assert view["coverage"]["missing_days"] == 0
    assert not [lim for lim in view.get("limitations", []) if "absent from the provider" in lim]


# ── ② بلا تصريحٍ بالمطلوب لا تُختلَق مقارنة ──────────────────────────
def test_without_a_declared_request_no_coverage_is_claimed():
    """المطلوبُ لا يُخمَّن من السلسلة نفسها — وإلّا قارنّاها بذاتها فخرجت كاملةً دوماً.

    وهذا يحفظ التوافقَ للخلف لكلّ مُستدعٍ لا يُمرّر المدى.
    """
    view = _view(3, None, None)

    assert "coverage" not in view
    assert view["quality_status"] == "validated"


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-03-10", "2026-03-01"), ("ليس تاريخاً", "2026-03-10"), ("2026-03-01", None)],
)
def test_an_unusable_requested_range_yields_no_fabricated_coverage(start, end):
    """مدًى مقلوبٌ أو فاسدٌ أو ناقصٌ ⇒ لا تغطية. لا صفرٌ ولا واحد — لا ادّعاء."""
    view = _view(3, start, end)

    assert "coverage" not in view


# ── ③ لا مفردةَ ثانية لنفس المعنى ────────────────────────────────────
def test_the_quality_vocabulary_matches_the_one_gdd_view_already_uses():
    """`degraded_incomplete_coverage` مفردةُ `gdd_view` نفسُها.

    مفردةٌ ثانية لنفس المعنى تُجبِر كلَّ مستهلكٍ على معرفة **أيّ** منتَجٍ أجابه قبل أن
    يفهم الجواب — وهو ما تمنعه الحقيقةُ الموحّدة.
    """
    import canonical_daily_weather_series as cdws

    source = __import__("inspect").getsource(cdws.gdd_view)
    assert "degraded_incomplete_coverage" in source
    assert _view(3, "2026-03-01", "2026-03-10")["quality_status"] == "degraded_incomplete_coverage"


def test_the_coverage_keys_match_the_existing_product():
    """نفسُ المفاتيح لا مرادفاتٍ لها — التغطيةُ عقدٌ واحد عبر المنتجَين."""
    coverage = _view(3, "2026-03-01", "2026-03-10")["coverage"]

    for key in (
        "period_start",
        "period_end",
        "expected_days",
        "observed_days",
        "missing_days",
        "coverage_ratio",
        "inclusive_dates",
    ):
        assert key in coverage, f"مفتاح التغطية {key} غائب — العقدُ افترق عن gdd_view"
    assert coverage["inclusive_dates"] is True


# ── ④ النقطة نفسها لا الغلاف وحده ────────────────────────────────────
def test_the_endpoint_carries_the_coverage_through_to_the_response(monkeypatch):
    """الفجوةُ كانت **في التمرير**: المُعالِج يعرف المطلوب ولا يُمرّره.

    فاختبارُ الغلاف وحده كان سيمرّ أخضرَ بينما النقطةُ صامتة — وهو نفسُ صنف
    `SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01`.
    """

    async def fake_fetch_historical(lat, lon, *, start_date, end_date):
        return _archive_series(3)

    monkeypatch.setattr(rt, "fetch_historical", fake_fetch_historical)
    monkeypatch.setitem(sys.modules, "main", main)
    monkeypatch.setattr(main, "fetch_historical", fake_fetch_historical, raising=False)

    with TestClient(main.app) as client:
        response = client.get(
            "/v1/weather/historical",
            params={
                "lat": 15.0,
                "lon": 44.0,
                "start_date": "2026-03-01",
                "end_date": "2026-03-10",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["coverage"]["expected_days"] == 10, "المطلوبُ لم يبلغ الجواب"
    assert body["coverage"]["observed_days"] == 3
    assert body["quality_status"] == "degraded_incomplete_coverage"
