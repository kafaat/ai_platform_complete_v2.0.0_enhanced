"""ما تُنتِجه خدمةُ الطقس تقرؤه المنصّةُ فعلاً — الطرفُ الثالث للقفزة نفسِها.

**العطلُ المُتَّقى (P6):** مساران في مساحة الحقل (`irrigation-advice` ·
`disease-risk`) كانا يستوردان موصّلَ Open-Meteo **داخل الدالّة** فيخرجان إلى
المزوّد مباشرةً، بينما بقيّةُ مسارات الملفّ نفسِه تمرّ بـ`weather_service_client`.
والقاطعُ لم يكن متجاوَزاً (`open_meteo._fetch_json` يفحصه قبل كلّ طلب) — المتجاوَزُ
**عقدُ الواجهة P3.4** و**مخبّأُ خدمة الطقس** المشترك.

**ولمَ لزِم مُحوِّلٌ مُختبَر:** الموصّلُ يُعيد كائناتٍ مُصنَّفة (`CurrentWeather` ·
`list[DailyForecast]`) والعميلُ يُعيد **مشاهدةَ `CanonicalWeatherState` قاموساً**.
المفاتيحُ متطابقةٌ حرفيّاً، لكنّ **شكلَ الوصول يتغيّر** ومعه موضعُ القائمة:
أيّامُ التوقّع تحت `days` في غلافٍ يحمل الجودةَ والنَّسَب، لا في جذر الردّ.
والقيمةُ الناقصةُ تصل `None` مُسمّاةً في `missing_fields` — فتُقرَأ صفراً إن
جُمِعت بلا فحص.

**والصنفُ الذي يحرسه هذا الملفّ** هو الذي أصابنا مرّتين في أسبوع
(`WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-DECLARED-01` ·
`AN-ACCEPTED-HORIZON-IS-QUANTISED-TO-TWO-BUCKETS-01`): عقدٌ طرفاه في خدمتين، كلٌّ
مختبَرٌ وحدَه، والقفزةُ بلا شاهد. فلا يزيّف هذا الملفُّ استجابةً: يُشغّل **مُنتِجَ
الخدمة الحقيقيّ** (`normalize_current`/`normalize_daily` ⇒ `build_canonical_weather_state`
⇒ `current_view`/`forecast_view`) ويُطعِم ناتجَه **مُستهلِكَ المنصّة الحقيقيّ**.

**وحدُّ صدقٍ يُقال:** المُستهلِكُ يُستخرَج من الراوتر بـ`ast` لأنّ استيرادَه يجرّ
`fastapi` و`api.main`. فالمقيسُ هو **دالّتا التحويل** لا تصييرُ المسار كاملاً.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ROUTER = _ROOT / "services" / "sahool-platform" / "api" / "routers" / "field_workspace_weather.py"
_SERVICE = _ROOT / "services" / "weather-service"

# حمولةُ المزوّد كما تصل الخدمةَ فعلاً — بأسماء Open-Meteo الخام لا بأسمائنا.
_PROVIDER_CURRENT = {
    "temperature_2m": 33.4,
    "relative_humidity_2m": 61.0,
    "wind_speed_10m": 12.0,
    "precipitation": 0.6,
    "cloud_cover": 20,
    "surface_pressure": 1002.0,
    "time": "2026-08-27T09:00",
}
_PROVIDER_DAILY = {
    "daily": {
        "time": ["2026-08-27", "2026-08-28", "2026-08-29"],
        "et0_fao_evapotranspiration": [6.4, 6.1, 5.9],
        "precipitation_sum": [0.0, 2.5, 1.5],
        "temperature_2m_max": [41.0, 40.2, 39.8],
        "temperature_2m_min": [27.0, 26.4, 26.1],
    }
}


@pytest.fixture(scope="module")
def platform_adapter() -> dict[str, Any]:
    """مُحوِّلا المنصّة مُستخرَجان من الراوتر — بلا `fastapi` ولا `api.main`."""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    wanted = ("_forecast_days", "_reading")
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert len(body) == len(wanted), (
        f"لم يُعثَر على مُحوِّلَي المنصّة {wanted} في الراوتر — تغيّر شكلُهما والفحصُ صار أعمى"
    )
    ns: dict[str, Any] = {"Any": Any}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<router>", "exec"), ns)  # noqa: S102
    return ns


@pytest.fixture(scope="module")
def service_views():
    """مُنتِجُ الخدمة الحقيقيّ — لا استجابةٌ مُزيَّفة."""
    sys.path.insert(0, str(_SERVICE))
    from canonical_weather_state import build_canonical_weather_state, current_view, forecast_view
    from open_meteo import normalize_current, normalize_daily

    def current(payload: dict[str, Any]) -> dict[str, Any]:
        observation = normalize_current(payload, lat=24.7, lon=46.7)
        state = build_canonical_weather_state(
            lat_deg=24.7, valid_time=observation.get("time"), current_observation=observation
        )
        return current_view(state)

    def forecast(payload: dict[str, Any]) -> dict[str, Any]:
        series = normalize_daily(
            payload, lat=24.7, lon=46.7, source="open-meteo", model="best_match"
        )
        state = build_canonical_weather_state(
            lat_deg=24.7,
            valid_time=(series.get("range") or {}).get("start"),
            forecast_series=series,
        )
        return forecast_view(state)

    return {"current": current, "forecast": forecast}


def test_both_ends_were_actually_loaded(platform_adapter, service_views) -> None:
    """فحصٌ يقرأ صفراً يمرّ أخضر عن سؤالٍ لم يطرحه — يُغلَق قبل الفحص نفسه."""
    assert callable(platform_adapter["_forecast_days"])
    assert callable(platform_adapter["_reading"])
    assert service_views["forecast"](_PROVIDER_DAILY).get("days"), "المُنتِجُ لم يُنتِج أيّاماً"


def test_the_platform_finds_the_forecast_days_where_the_service_puts_them(
    platform_adapter, service_views
) -> None:
    """`forecast_view` غلافٌ: القائمةُ تحت `days` لا في الجذر — وقراءةُ الجذر فراغٌ صامت."""
    view = service_views["forecast"](_PROVIDER_DAILY)
    days = platform_adapter["_forecast_days"](view)

    assert len(days) == 3, (
        f"ضاعت أيّامٌ في القفزة: أنتجت الخدمةُ {view.get('day_count')} وقُرِئ {len(days)}"
    )
    assert [d["date"] for d in days] == ["2026-08-27", "2026-08-28", "2026-08-29"]


def test_the_irrigation_inputs_arrive_with_their_values(platform_adapter, service_views) -> None:
    """ET₀ ومطرُ التوقّع — المُدخَلان اللذان يبني عليهما `irrigation_advice` كمّيّةَ الريّ."""
    reading = platform_adapter["_reading"]
    days = platform_adapter["_forecast_days"](service_views["forecast"](_PROVIDER_DAILY))

    assert reading(days[0], "et0_mm") == pytest.approx(6.4)
    # نفسُ الشريحة التي يجمعها المسار: `days[1:3]`.
    forecast_rain = sum(reading(day, "precipitation_mm") or 0.0 for day in days[1:3])
    assert forecast_rain == pytest.approx(4.0)

    current = service_views["current"](_PROVIDER_CURRENT)
    assert reading(current, "precipitation_mm") == pytest.approx(0.6)


def test_the_disease_risk_inputs_arrive_with_their_values(platform_adapter, service_views) -> None:
    reading = platform_adapter["_reading"]
    current = service_views["current"](_PROVIDER_CURRENT)

    assert reading(current, "temperature_c") == pytest.approx(33.4)
    assert reading(current, "humidity_pct") == pytest.approx(61.0)


def test_an_unobserved_field_reads_as_missing_not_as_zero(platform_adapter, service_views) -> None:
    """الحقلُ غيرُ المرصود يصل **`None` مُسمّى في `missing_fields`** — لا صفراً.

    **وتصحيحٌ لقياسٍ لي:** ظننتُ أوّلاً أنّ المفتاحَ **يغيب** من القاموس، وبنيتُ
    عليه حُجّةَ الفحص. القياسُ على المسار الحقيقيّ نقضه: `normalize_current` يُصدِر
    تسعةَ عشرَ مفتاحاً **دائماً** بـ`.get()`، فالمفتاحُ حاضرٌ وقيمتُه `None`. وأصلُ
    الخطأ أنّني قِستُ على قاموسٍ بنيتُه بيدي فتخطّيتُ المُطبِّعَ نفسَه — وهو حرفيّاً
    الصنفُ الذي يحرسه هذا الملفّ: **قياسُ طرفٍ وحدَه ليس قياسَ القفزة**.

    وصفرٌ هنا كذبٌ مُكلِف: `humidity_pct = 0` رطوبةٌ معدومة تخفض خطرَ الأمراض،
    و`precipitation_mm = 0` «لا مطر» ترفع كمّيّةَ الريّ الموصى بها. فالمُحوِّلُ
    يُعيد `None` ويقرّر المسارُ (٥٠٣ صريح) بدل أن يُحسَب الغيابُ قيمةً.
    """
    degraded = {k: v for k, v in _PROVIDER_CURRENT.items() if k != "relative_humidity_2m"}
    view = service_views["current"](degraded)

    assert view.get("humidity_pct") is None
    assert "humidity_pct" in (view.get("missing_fields") or []), (
        "الخدمةُ لا تُسمّي المفقود — فيصير الغيابُ استنتاجاً لا تصريحاً"
    )
    assert view.get("quality_status") == "degraded"
    assert platform_adapter["_reading"](view, "humidity_pct") is None
    # والمرصودُ بجانبه يبقى مقروءاً — الغيابُ لا يُعمي القراءةَ كلَّها.
    assert platform_adapter["_reading"](view, "temperature_c") == pytest.approx(33.4)


def test_the_adapter_also_survives_a_key_that_is_absent_entirely(platform_adapter) -> None:
    """`None` هو الشكلُ المقيس اليوم، والغيابُ الكاملُ شكلٌ ثانٍ لا يُستبعَد.

    `current_view` يُمرّر ما في خانة الحالة كما هو، فمُنتِجٌ أضيقُ (أو تغيّرٌ في
    المُطبِّع) يُسقِط المفتاحَ رأساً. والمُحوِّلُ يُعطي الجوابَ نفسَه في الحالتين،
    فلا يعتمد المسارُ على أيّهما وقع.
    """
    reading = platform_adapter["_reading"]

    assert reading({"temperature_c": 30.0}, "humidity_pct") is None
    assert reading({"humidity_pct": None}, "humidity_pct") is None
    assert reading(None, "humidity_pct") is None
    assert reading({"humidity_pct": "غير رقميّ"}, "humidity_pct") is None


def test_a_real_zero_is_not_confused_with_absence(platform_adapter, service_views) -> None:
    """`0.0 mm` قراءةٌ فيزيائيّة مشروعة — تمييزُها من الغياب هو كلُّ الفائدة."""
    reading = platform_adapter["_reading"]
    days = platform_adapter["_forecast_days"](service_views["forecast"](_PROVIDER_DAILY))

    assert reading(days[0], "precipitation_mm") == 0.0
    assert reading(days[0], "precipitation_mm") is not None


def test_a_malformed_envelope_yields_no_days_rather_than_raising(platform_adapter) -> None:
    """تدهورُ الخدمة لا يصير `TypeError` عند المستهلك — يصير صفرَ أيّامٍ ثمّ ٥٠٣ صريحاً."""
    forecast_days = platform_adapter["_forecast_days"]

    assert forecast_days({}) == []
    assert forecast_days({"days": None}) == []
    assert forecast_days({"days": ["not-a-day", {"date": "2026-08-27"}]}) == [
        {"date": "2026-08-27"}
    ]
