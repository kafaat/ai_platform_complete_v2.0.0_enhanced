"""نسبةُ خرائط الأساس وبيانات الطقس إلى أصحابها (OpenStreetMap · CARTO · Open-Meteo).

**ما وُجِد على c9e8c15e:** خرائط CARTO (light_all في ``layerRegistry.ts`` و
``FieldIndicatorMap.tsx``، وdark_all في ``gis-overlay``) تُنسَب «© CARTO» وحدها، وصفحة
``gis-overlay`` تُطفئ شريط النسب كلّه (``attributionControl: false``). ولوحة الطقس في
``big-screen`` تقول «Open-Meteo» شارةً بلا رابط ولا رخصة، وكذلك شاشات الطقس في التطبيق.

**لماذا هو عطل لا تجميل — من المصادر الأوّليّة:**

* أنماطُ CARTO مرسومةٌ من بيانات OpenStreetMap، ومثالُ CARTO نفسه في README مستودع
  ``CartoDB/basemap-styles`` يكتب النسبة «© OpenStreetMap, © CARTO» (الأولى رابطٌ إلى
  ``openstreetmap.org/copyright``). وصفحة الحقوق في OSM (``config/locales/en.yml`` في
  ``openstreetmap/openstreetmap-website``، ``credit_2_attribution``) تشترط: «Provide credit
  to OpenStreetMap by displaying our attribution notice» وأن يُوضَّح أنّ البيانات تحت ODbL
  (``credit_4_v2025_html``: «you may link to this copyright page»).
* بيانات Open-Meteo بـCC BY 4.0، وشرطُها في README مستودع ``open-meteo/open-meteo`` (قسم
  «Data License»): «Include an attribution link next to any location where Open-Meteo
  data is displayed» بمثالٍ حرفيّ ``<a href="https://open-meteo.com/">Weather data by
  Open-Meteo.com</a>``، وCC BY نفسها تطلب «provide a link to the license».

**ما يُحرَس (خاصيّةٌ مُشتقّة من الشجرة لا قائمةُ أسطر):**

1. كلُّ سطرٍ في مصادر الواجهة يحمل رابط نسبةٍ إلى CARTO يحمل في السطر نفسه رابط حقوق
   OSM — فنسبةٌ تُكتَب في موضعٍ جديد لا تفلت لأنّها لم تُدرَج في قائمة.
2. كلُّ ملفٍّ يطلب بلاطات ``basemaps.cartocdn.com`` يحمل نسبة OSM ولا يُطفئ شريط النسب.
3. كلُّ وحدةٍ في ``frontend/src`` تستدعي خطّافاً من ``_WEATHER_DATA_FETCHERS`` إمّا تعرض
   نسبة Open-Meteo، وإمّا مُدرَجةٌ في ``NOT_A_WEATHER_DISPLAY`` **بسببٍ مكتوب**. فشاشةٌ
   جديدة تستدعي أيّاً منها تُحمِر هنا حتّى تُنسِب مصدرها أو يُكتَب لماذا لا تعرضه.

**وما لا يحرسه (حدٌّ مُعلَن):** لا يُصيِّر الصفحات — التأكيد على نصّ المصدر. التصييرُ
والأنواع في وظيفة *Frontend Typecheck* (tsc · eslint · vitest) ووظيفة E2E في CI. والقائمةُ
أسماءٌ لا اشتقاق: خطّافٌ **جديد** يجلب الطقس لا يُرى حتّى يُضاف إليها (الفحصُ المقابل
يمنع العكس فقط: اسمٌ مُدرَجٌ لم يعد معرَّفاً).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

OSM_COPYRIGHT = "https://www.openstreetmap.org/copyright"
OPEN_METEO_URL = "https://open-meteo.com/"
OPEN_METEO_TEXT = "Weather data by Open-Meteo.com"
CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"

# مجلّداتُ بناءٍ وتبعيّات — ليست مصدراً يُصيَّر للمستخدم.
_SKIP_DIRS = {
    "node_modules",
    "dist",
    "coverage",
    "playwright-report",
    "test-results",
    "__screenshots__",
}
_SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".html"}

# رابطُ نسبةٍ إلى CARTO داخل نصّ نسبة (HTML في سلسلة JS أو في صفحة ساكنة).
_CARTO_CREDIT = re.compile(r"""href=\\?["']https?://(?:www\.)?carto\.com""")

# خطّافاتُ/دوالُّ الواجهة التي تجلب قيمَ طقسٍ من Open-Meteo (عبر weather-service) —
# مُعدَّدةٌ بالبحث عن ``/weather`` في ``frontend/src/hooks`` و``services`` على الشجرة التي
# كُتِبت عليها. ويفحص ``test_every_listed_weather_fetcher_is_still_defined`` أنّ كلّ اسمٍ هنا
# ما زال معرَّفاً، فإعادةُ تسميةِ خطّافٍ لا تُخرِجه من الحراسة صامتةً.
_WEATHER_DATA_FETCHERS = (
    # /api/v1/weather/{current,forecast,historical}
    "useWeatherForecast",
    "useWeatherWofost",
    "useWeatherHistory",
    "fetchCurrentWeather",
    "fetchWeatherForecast",
    "fetchWeatherHistorical",
    "fetchWofostFormat",
    # ملخّص طقس الحقل وسلاسل البلاطات وبلاطاتها
    "useFieldWeatherSummary",
    "useWeatherTileSeries",
    "getWeatherTileData",
    # /api/v1/fields/{id}/weather/operation-windows
    "getFieldWeatherOperationWindows",
    # /api/v1/fields/{id}/weather/disease-risk — temperature_c · humidity_pct · rain_mm_3d،
    # ونصُّ advice_ar يقتبسها في الخطر المتوسّط والمرتفع (api/weather_advice.py).
    "useDiseaseRisk",
    "fetchDiseaseRisk",
    "getFieldDiseaseRisk",
    # /api/v1/fields/{id}/weather/irrigation-advice — et0 من توقّع Open-Meteo.
    "useIrrigationAdvice",
    "fetchIrrigationAdvice",
    "getFieldIrrigationAdvice",
    # WS-D.2: بلا طقسٍ في الجسم يجلب الخادمُ التوقّع بنفسه (weather-engine-forecast).
    "useFieldIrrigationRecommendation",
    # /api/v1/weather/alerts — نصُّ التنبيه يحمل سرعة الريح والحرارة.
    "useWeatherAlerts",
    # مسبار الخريطة: عيّنةُ النقطة ونافذةُ العمليّة وخطّتُها وتوصيتُها.
    "getWeatherProbe",
    "getWeatherOperationWindow",
    "getWeatherOperationPlan",
    "getWeatherActionRecommendation",
)
# وخارجَ القائمة عمداً: ``useWeatherLayers`` (manifest أسماء الطبقات ووحداتها، لا قيم)،
# و``useWeatherAnalysis``/``useWeatherPlantingGuide`` (تحلّل سجلّاً يُدخِله المستخدم، لا بيانات
# Open-Meteo)، و``createWeather*FromOperationPlan`` (كتابةُ مهمّةٍ/توصية).

# الاستدعاء لا التعريف (``function name(`` تعريفٌ في وحدة الخدمة/الخطّاف، فيُستثنى بالنظر الخلفيّ).
_WEATHER_DATA_CALL = re.compile(
    r"(?<!function )\b(?:" + "|".join(_WEATHER_DATA_FETCHERS) + r")\s*(?:<[^>]*>)?\("
)

# وحداتٌ تستدعي خطّاف طقسٍ ولا تحتاج نسبةً في ملفّها — لكلٍّ سببُه.
NOT_A_WEATHER_DISPLAY = {
    "frontend/src/hooks/useApi.ts": (
        "وحدةُ الخطّافات: تلفّ fetchDiseaseRisk/fetchIrrigationAdvice في خطّافات وتركّب "
        "useDashboardData — لا تُصيِّر شيئاً؛ الشاشاتُ التي تعرض القيم تنسب."
    ),
    "frontend/src/sections/ChatbotPage.tsx": "الطقس يُمرَّر سياقاً للنموذج ولا يُعرَض قيماً في الصفحة.",
    "frontend/src/sections/MapHub.tsx": (
        "يبني WeatherMarker ويمرّره إلى محرّكي الخريطة؛ العرضُ هناك: HubMap (Leaflet) تنسب عبر "
        "طبقة WeatherTileLayer في شريط النسب، وHubMapGL يعرض النسبة مع تراكب الطقس."
    ),
    "frontend/src/components/fieldview/IrrigationDecisionCard.tsx": (
        "الحرارتان يُدخِلهما المستخدم من قياسه (manual_override)، ولا تُعرَض نتيجةٌ قبل إدخالهما؛ "
        "وما يُعرَض مشتقّاتُ ريّ (Dr · TAW · صافي الريّ) لا قيمُ طقسٍ من Open-Meteo."
    ),
    "frontend/src/components/maphub/weather/WeatherProbePopup.ts": (
        "نافذةٌ على خريطة Leaflet تُسجَّل في WeatherRasterOverlay بشرط طبقة الطقس نفسه، وطبقةُ "
        "WeatherTileLayer تضع النسبة في شريط نسب تلك الخريطة (يُفحَص أدناه)."
    ),
    "frontend/src/components/maphub/weather/WeatherHoverReadout.ts": (
        "قراءةُ تحويمٍ على خريطة Leaflet تُسجَّل في WeatherRasterOverlay بشرط طبقة الطقس نفسه، "
        "وطبقةُ WeatherTileLayer تضع النسبة في شريط نسب تلك الخريطة (يُفحَص أدناه)."
    ),
}

# المسبار والتحويم يعتمدان على نسبة شريط الخريطة، فلا يصحّ تسجيلهما إلّا حيث تُرسَم الطبقة.
_MAP_PROBE_REGISTRARS = ("registerWeatherProbePopup", "registerWeatherHoverReadout")
_WEATHER_OVERLAY = "frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx"


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _frontend_sources(base: Path = FRONTEND) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix not in _SOURCE_SUFFIXES:
                continue
            # ملفّات الاختبار تؤكّد على النصوص ولا تُصيِّرها.
            if ".test." in name or ".spec." in name:
                continue
            out.append(p)
    return sorted(out)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_carto_credit_also_credits_openstreetmap() -> None:
    offenders: list[str] = []
    seen = 0
    for path in _frontend_sources():
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if not _CARTO_CREDIT.search(line):
                continue
            seen += 1
            if OSM_COPYRIGHT not in line or "OpenStreetMap" not in line:
                offenders.append(f"{_rel(path)}:{lineno}: {line.strip()[:160]}")
    assert not offenders, (
        "CARTO basemaps are drawn from OpenStreetMap data; ODbL requires the OSM credit with a "
        "link to its copyright page next to the CARTO credit:\n  " + "\n  ".join(offenders)
    )
    # لا أخضرَ من فراغ: نسبُ CARTO موجودة فعلاً (السجلّ + خريطة المؤشّر + احتياطُ GL + gis-overlay).
    assert seen >= 4, f"expected the CARTO credits the frontend carries, found only {seen}"


def test_every_page_that_loads_carto_tiles_shows_the_osm_credit() -> None:
    pages = [p for p in _frontend_sources() if "basemaps.cartocdn.com" in _read(p)]
    assert pages, "expected at least one frontend file that loads CARTO tiles"
    missing: list[str] = []
    hidden: list[str] = []
    for path in pages:
        src = _read(path)
        if OSM_COPYRIGHT not in src or not _CARTO_CREDIT.search(src):
            missing.append(_rel(path))
        if re.search(r"attributionControl\s*:\s*false", src):
            hidden.append(_rel(path))
    assert not missing, f"pages load CARTO/OSM tiles without the OSM + CARTO credit: {missing}"
    assert not hidden, (
        "attributionControl:false hides the credit the tile layer declares — the OSM/CARTO "
        f"credit must stay visible on a page that draws their tiles: {hidden}"
    )


def test_open_meteo_credit_constants_carry_link_text_and_licence() -> None:
    src = _read(FRONTEND / "src/lib/openMeteoAttribution.ts")
    assert f"'{OPEN_METEO_URL}'" in src
    assert f"'{OPEN_METEO_TEXT}'" in src
    assert f"'{CC_BY_4_URL}'" in src
    assert "OPEN_METEO_ATTRIBUTION_HTML" in src
    comp = _read(FRONTEND / "src/components/OpenMeteoAttribution.tsx")
    for name in ("OPEN_METEO_URL", "OPEN_METEO_CREDIT_TEXT", "CC_BY_4_URL"):
        assert name in comp, f"OpenMeteoAttribution must render {name} from the shared module"
    assert 'rel="noopener noreferrer"' in comp


def test_weather_map_layer_puts_open_meteo_credit_in_the_map_attribution() -> None:
    src = _read(FRONTEND / "src/components/maphub/weather/WeatherTileLayer.ts")
    assert "OPEN_METEO_ATTRIBUTION_HTML" in src
    assert re.search(r"attribution\s*:\s*OPEN_METEO_ATTRIBUTION_HTML", src), (
        "the weather GridLayer must declare the Open-Meteo credit so Leaflet shows it while the layer is on"
    )


@pytest.mark.parametrize(
    "rel",
    ["frontend/big-screen/index.html", "frontend/big-screen/keep_bigscreen/index.html"],
)
def test_big_screen_weather_panel_links_open_meteo_and_licence(rel: str) -> None:
    src = _read(ROOT / rel)
    assert f'href="{OPEN_METEO_URL}"' in src
    assert OPEN_METEO_TEXT in src
    assert f'href="{CC_BY_4_URL}"' in src


def test_every_module_that_fetches_weather_data_credits_open_meteo() -> None:
    callers = [
        p for p in _frontend_sources(FRONTEND / "src") if _WEATHER_DATA_CALL.search(_read(p))
    ]
    # لا أخضرَ من فراغ: شاشات الطقس الحاليّة تستدعي هذه الخطّافات.
    assert len(callers) >= 5, (
        f"expected the weather data callers, found {[_rel(p) for p in callers]}"
    )
    uncredited: list[str] = []
    for path in callers:
        rel = _rel(path)
        if rel in NOT_A_WEATHER_DISPLAY:
            continue
        src = _read(path)
        if "<OpenMeteoAttribution" not in src and "OPEN_METEO_ATTRIBUTION_HTML" not in src:
            uncredited.append(rel)
    assert not uncredited, (
        "Open-Meteo data is CC BY 4.0 and its terms require an attribution link next to where the "
        "data is displayed; render <OpenMeteoAttribution /> or list the module in "
        f"NOT_A_WEATHER_DISPLAY with the reason it shows no weather values: {uncredited}"
    )


def test_not_a_weather_display_allowlist_has_no_stale_entries() -> None:
    stale = [
        rel
        for rel in NOT_A_WEATHER_DISPLAY
        if not (ROOT / rel).exists() or not _WEATHER_DATA_CALL.search(_read(ROOT / rel))
    ]
    assert not stale, f"allowlist entries that no longer call a weather data hook: {stale}"


def test_every_listed_weather_fetcher_is_still_defined() -> None:
    # اسمٌ أُعيدت تسميته يُفرِغ النمطَ منه بلا إنذار: الشاشاتُ التي تستدعي الاسمَ الجديد تفلت.
    src = "\n".join(_read(p) for p in _frontend_sources(FRONTEND / "src"))
    undefined = [
        name
        for name in _WEATHER_DATA_FETCHERS
        if not re.search(rf"\b(?:function\s+{name}\b|const\s+{name}\s*=)", src)
    ]
    assert not undefined, (
        f"weather fetchers listed in this guard but no longer defined in frontend/src: {undefined}"
    )


def test_map_probe_and_hover_are_registered_only_where_the_credited_layer_is_drawn() -> None:
    # سببُ استثناء المسبار والتحويم أعلاه: شريطُ نسب الخريطة نفسها. فإن سُجِّلا في موضعٍ لا
    # تُرسَم فيه طبقةُ WeatherTileLayer (كمحرّك WebGL) صار عرضُهما بلا نسبة.
    for name in _MAP_PROBE_REGISTRARS:
        users = [
            _rel(p)
            for p in _frontend_sources(FRONTEND / "src")
            if re.search(rf"(?<!function ){name}\s*\(", _read(p))
        ]
        assert users == [_WEATHER_OVERLAY], f"{name} is called outside {_WEATHER_OVERLAY}: {users}"
    overlay = _read(ROOT / _WEATHER_OVERLAY)
    assert "createWeatherWindGridLayer(" in overlay, (
        f"{_WEATHER_OVERLAY} must draw the WeatherTileLayer whose attribution credits Open-Meteo"
    )


@pytest.mark.parametrize(
    "rel",
    [
        "frontend/src/components/fieldview/FieldIntelligenceCardView.tsx",
        "frontend/src/components/maphub/HubMapGL.tsx",
    ],
)
def test_weather_surfaces_outside_the_call_pattern_credit_open_meteo(rel: str) -> None:
    # تعرض طقس Open-Meteo بلا استدعاءٍ مباشر يلتقطه النمط أعلاه: بطاقة الحقل عبر خطّافٍ
    # مركّب، ومحرّك WebGL عبر WeatherMarker يُمرَّر إليه من MapHub — فتُسمَّى صراحةً.
    assert "<OpenMeteoAttribution" in _read(ROOT / rel)
