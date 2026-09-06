"""`WEATHER-MODEL-IDENTITY-v1` — هويّةُ نموذج الطقس، وحسابُ القاطع، وزمنُ العيّنة.

**ثلاثةُ أعطالٍ مقيسة على `9876bd92`، لا مُتخيَّلة:**

1. **معرّفٌ متقاعد في أربعة مواضع.** `ecmwf_ifs04` في `tiles.py` والراوتر (قائمةً
   وmanifest) والواجهة. رفع Open-Meteo دقّةَ IFS إلى 0.25° وبدّل المعرّف إلى
   `ecmwf_ifs025`. هل ما يزال القديمُ يُجاب؟ **NOT_MEASURED** — الشبكةُ محجوبة في
   جلسة التأليف. لكنّ الثاني يجعل السؤالَ ثانويّاً:
2. **رفضُ الطلب كان يُحسَب عطلَ مزوّد.** كلا `_fetch_json` كان يزيد عدّادَ القاطع على
   **أيّ** استثناء. فثلاثةُ اختياراتٍ (الخدمة) أو خمسة (الموصِّل) لنموذجٍ مرفوض
   تُطفئ الطقسَ **لكلّ** المستخدمين ٣٠ ثانية — حتّى `best_match`.
3. **`+Nh` كان فهرسَ مصفوفةٍ لا طابعاً.** ومصفوفاتُ Open-Meteo الساعيّة تبدأ من
   **منتصف الليل** لا من الآن: `+1h` في الثالثة عصراً = **01:00 فجراً**. ونموذجٌ
   خطوتُه ٦ ساعات كان سيُرجِع `+36h` على أنّه `+6h` بصمت.

**أربعُ خصائصَ تُغلَق معاً:** (١) كلُّ نموذجٍ في الواجهة يقبله الخلفيّان؛ (٢) كلُّ
نموذجٍ في الخلفيّ موثَّقٌ منبعيّاً أو اسمٌ داخليّ صريح؛ (٣) أخطاءُ عقد الطلب لا تفتح
قاطعَ التوافر؛ (٤) `time_key` يُحَلّ بالطوابع الفعليّة لا بالموضع.

**حدودُ الصدق.** لا يُقاس هنا هل يُرجِع Open-Meteo لنماذج الخطوة الأطول سلسلةً
أخفّ أم سلسلةً ساعيّةً محشوّةً بالاستيفاء — الحلُّ بالطابع صحيحٌ في الحالين، لكنّ
`native_step_hours` في الكتالوج **إرشاديّ** لا مقيس.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_CATALOGUE = _ROOT / "docs/architecture/weather_model_catalogue.json"
_TILES = _ROOT / "services/weather-service/tiles.py"
_ROUTER = _ROOT / "services/sahool-platform/api/routers/weather.py"
_FRONTEND = _ROOT / "frontend/src/components/maphub/weather/weatherLayerDefinitions.ts"
_SERVICE_MODULE = _ROOT / "services/weather-service/open_meteo.py"
_CONNECTOR_MODULE = _ROOT / "services/sahool-platform/api/connectors/openmeteo.py"
_PLATFORM_ROOT = _ROOT / "services/sahool-platform"


# ─── قراءةُ الأسطح ─────────────────────────────────────────────────


def _catalogue() -> dict:
    return json.loads(_CATALOGUE.read_text(encoding="utf-8"))


def _assigned_set(path: Path, name: str) -> set[str]:
    """يقرأ ``NAME = {...}`` من الملفّ بـ``ast`` — بلا استيراد راوترٍ ثقيل."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, set), f"{name} في {path.name} ليست مجموعة"
            return set(value)
    raise AssertionError(f"لم يُعثَر على {name} في {path}")


def _manifest_model_keys() -> list[str]:
    text = _ROUTER.read_text(encoding="utf-8")
    start = text.index("def weather_layers_manifest")
    block = re.search(r'"models":\s*\[(.*?)\]', text[start:], re.DOTALL)
    assert block, "لم يُعثَر على كتلة models في manifest الراوتر"
    return re.findall(r'\{"key":\s*"([A-Za-z0-9_]+)"', block.group(1))


def _frontend_model_keys() -> list[str]:
    text = _FRONTEND.read_text(encoding="utf-8")
    block = re.search(r"WEATHER_MODELS[^=]*=\s*\[(.*?)\];", text, re.DOTALL)
    assert block, "لم يُعثَر على WEATHER_MODELS في الواجهة"
    return re.findall(r"key:\s*'([A-Za-z0-9_]+)'", block.group(1))


# ─── تحميلُ الوحدتين بلا حزمة مشتركة ─────────────────────────────────


def _load(path: Path, name: str, *, sys_path: Path | None = None):
    inserted = False
    if sys_path is not None and str(sys_path) not in sys.path:
        sys.path.insert(0, str(sys_path))
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # `@dataclass` يبحث عن الوحدة في `sys.modules` باسمها — فتُسجَّل قبل التنفيذ.
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(str(sys_path))


@pytest.fixture(scope="module")
def ws():
    return _load(_SERVICE_MODULE, "wmi_weather_service_open_meteo")


@pytest.fixture(scope="module")
def om():
    return _load(_CONNECTOR_MODULE, "wmi_platform_openmeteo", sys_path=_PLATFORM_ROOT)


@pytest.fixture
def reset_breakers(ws, om):
    ws._BREAKER_FAILURES = 0
    ws._BREAKER_OPEN_UNTIL = 0.0
    ws._LAST_REQUEST_ERROR = None
    ws._LAST_ACCESS_ERROR = None
    om._OPENMETEO_BREAKER.reset()
    om._circuit_open_warned = False
    om._last_request_error = None
    om._last_access_error = None
    yield
    ws._BREAKER_FAILURES = 0
    ws._BREAKER_OPEN_UNTIL = 0.0
    om._OPENMETEO_BREAKER.reset()


#: الصنفُ الحقيقيّ يُلتقَط مرّةً عند الاستيراد — وإلّا لفّ الاستبدالُ الثاني الأوّلَ.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_upstream(monkeypatch, handler):
    """يستبدل ``httpx.AsyncClient`` بعميلٍ على ``MockTransport`` — بلا شبكة."""
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _always(status: int, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {})

    return handler


# ─── (١) + (٢): الأسطحُ الأربعة مقابل الكتالوج ─────────────────────────


def test_every_backend_allowlist_equals_the_catalogue():
    catalogue = set(_catalogue()["models"])
    tiles = _assigned_set(_TILES, "ALLOWED_MODELS")
    router = _assigned_set(_ROUTER, "_ALLOWED_WEATHER_MODELS")
    assert len(catalogue) >= 3, "الكتالوجُ فارغٌ أو شبهُ فارغ — القراءةُ لا تقيس شيئاً"
    assert tiles == catalogue, f"weather-service ≠ الكتالوج: {tiles ^ catalogue}"
    assert router == catalogue, f"الراوتر ≠ الكتالوج: {router ^ catalogue}"


def test_every_model_the_ui_offers_is_accepted_by_both_backends():
    catalogue = _catalogue()["models"]
    ui_visible = {k for k, v in catalogue.items() if v.get("ui_visible")}
    frontend = _frontend_model_keys()
    manifest = _manifest_model_keys()
    assert len(frontend) >= 3 and len(manifest) >= 3, "قراءةُ الواجهة/manifest لم تبلغ شيئاً"
    assert set(frontend) == ui_visible, (
        f"الواجهة ≠ المرئيّ في الكتالوج: {set(frontend) ^ ui_visible}"
    )
    assert set(manifest) == ui_visible, (
        f"manifest ≠ المرئيّ في الكتالوج: {set(manifest) ^ ui_visible}"
    )
    both_backends = _assigned_set(_TILES, "ALLOWED_MODELS") & _assigned_set(
        _ROUTER, "_ALLOWED_WEATHER_MODELS"
    )
    assert set(frontend) <= both_backends, (
        f"الواجهةُ تعرض ما يرفضه خلفيّ: {set(frontend) - both_backends}"
    )


def test_retired_identifiers_survive_nowhere():
    retired = set(_catalogue()["retired"])
    assert retired, "قائمةُ المتقاعدين فارغة — الحارسُ لا يحرس شيئاً"
    surfaces = {
        "tiles": _assigned_set(_TILES, "ALLOWED_MODELS"),
        "router": _assigned_set(_ROUTER, "_ALLOWED_WEATHER_MODELS"),
        "manifest": set(_manifest_model_keys()),
        "frontend": set(_frontend_model_keys()),
        "catalogue.models": set(_catalogue()["models"]),
    }
    leaks = {name: keys & retired for name, keys in surfaces.items() if keys & retired}
    assert not leaks, f"معرّفٌ متقاعد ما يزال معروضاً: {leaks}"


def test_every_catalogue_model_is_upstream_documented_or_an_explicit_alias():
    models = _catalogue()["models"]
    for key, spec in models.items():
        has_upstream = "upstream_id" in spec
        has_alias = "internal_alias_of" in spec
        assert has_upstream != has_alias, (
            f"{key}: إمّا upstream_id أو internal_alias_of — لا كلاهما ولا لا شيء"
        )
        assert spec.get("source"), f"{key}: بلا مصدر"
        if has_alias:
            assert spec["internal_alias_of"] in models, f"{key}: اسمٌ داخليّ لهدفٍ غيرِ موجود"
            assert spec.get("sent_upstream") is False, f"{key}: اسمٌ داخليّ لا يُرسَل للمزوّد"
        if spec.get("sent_upstream"):
            assert spec["upstream_id"] == key, f"{key}: ما يُرسَل يجب أن يكون المعرّفَ نفسَه"


# ─── (٣): تصنيفُ القاطع — في الخدمة وفي الموصِّل ─────────────────────


async def test_three_rejected_model_requests_leave_the_weather_service_breaker_closed(
    ws, monkeypatch, reset_breakers
):
    """400 لمعرّفٍ مرفوض ثلاثَ مرّات (= العتبة) — والقاطعُ يبقى مغلقاً لـbest_match."""
    _mock_upstream(monkeypatch, _always(400, {"error": True, "reason": "Cannot initialize model"}))
    for _ in range(ws.BREAKER_FAILURE_THRESHOLD):
        with pytest.raises(httpx.HTTPStatusError):
            await ws.fetch_current(15.37, 44.19, model="ecmwf_ifs04")
    state = ws.circuit_breaker_state()
    assert state["state"] == "closed", "رفضُ طلبنا فتح قاطعَ المزوّد"
    assert state["failure_count"] == 0
    assert state["last_request_error"]["status_code"] == 400
    assert state["last_request_error"]["reason"] == "Cannot initialize model"

    # والدليلُ العمليّ: best_match يمرّ فوراً بعدها.
    _mock_upstream(
        monkeypatch, _always(200, {"current": {"temperature_2m": 30.0, "time": "2026-09-05T15:00"}})
    )
    out = await ws.fetch_current(15.37, 44.19)
    assert out["temperature_c"] == 30.0


async def test_three_upstream_outages_do_open_the_weather_service_breaker(
    ws, monkeypatch, reset_breakers
):
    """الاتّجاهُ المقابل: 503 ثلاثَ مرّات يفتحه — التصنيفُ لا يُعطّل القاطع."""
    _mock_upstream(monkeypatch, _always(503))
    for _ in range(ws.BREAKER_FAILURE_THRESHOLD):
        with pytest.raises(httpx.HTTPStatusError):
            await ws.fetch_current(15.37, 44.19)
    assert ws.circuit_breaker_state()["state"] == "open"
    with pytest.raises(RuntimeError, match="circuit breaker is open"):
        await ws.fetch_current(15.37, 44.19)


async def test_quota_and_auth_are_a_separate_state_not_an_outage(ws, monkeypatch, reset_breakers):
    _mock_upstream(monkeypatch, _always(429, {"reason": "Daily API request limit exceeded"}))
    for _ in range(ws.BREAKER_FAILURE_THRESHOLD):
        with pytest.raises(httpx.HTTPStatusError):
            await ws.fetch_current(15.37, 44.19)
    state = ws.circuit_breaker_state()
    assert state["state"] == "closed"
    assert state["last_access_error"]["status_code"] == 429
    assert state["last_request_error"] is None


def test_the_classifier_draws_the_three_lines_where_the_contract_says(ws, om):
    def http_error(code: int) -> httpx.HTTPStatusError:
        req = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
        return httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))

    for module in (ws, om):
        assert module.classify_upstream_error(http_error(400)) == "request"
        assert module.classify_upstream_error(http_error(404)) == "request"
        assert module.classify_upstream_error(http_error(422)) == "request"
        assert module.classify_upstream_error(http_error(401)) == "access"
        assert module.classify_upstream_error(http_error(403)) == "access"
        assert module.classify_upstream_error(http_error(429)) == "access"
        assert module.classify_upstream_error(http_error(500)) == "provider"
        assert module.classify_upstream_error(http_error(503)) == "provider"
        assert module.classify_upstream_error(httpx.ConnectError("x")) == "provider"
        assert module.classify_upstream_error(httpx.ReadTimeout("x")) == "provider"


async def test_five_rejected_model_requests_leave_the_platform_connector_breaker_closed(
    om, monkeypatch, reset_breakers
):
    _mock_upstream(monkeypatch, _always(400, {"error": True, "reason": "Cannot initialize model"}))
    for _ in range(om._OPENMETEO_BREAKER.failure_threshold):
        with pytest.raises(httpx.HTTPStatusError):
            await om.fetch_current(15.37, 44.19)
    snap = om.openmeteo_breaker_state()
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 0
    assert snap["last_request_error"] == {"status_code": 400, "reason": "Cannot initialize model"}


async def test_five_upstream_outages_do_open_the_platform_connector_breaker(
    om, monkeypatch, reset_breakers
):
    _mock_upstream(monkeypatch, _always(503))
    for _ in range(om._OPENMETEO_BREAKER.failure_threshold):
        with pytest.raises(httpx.HTTPStatusError):
            await om.fetch_current(15.37, 44.19)
    assert om.openmeteo_breaker_state()["state"] == "open"


# ─── (٤): زمنُ العيّنة بالطابع لا بالموضع ────────────────────────────

_DAY = "2026-09-05"


def _hourly_from_midnight(step_hours: int = 1, hours: int = 48) -> dict:
    """سلسلةٌ كما يُرجِعها Open-Meteo: تبدأ 00:00 — والقيمةُ تحمل ساعتَها ليُقرأ الخطأُ فوراً."""
    times, temps, winds = [], [], []
    for h in range(0, hours, step_hours):
        day_offset, hour = divmod(h, 24)
        times.append(f"2026-09-{5 + day_offset:02d}T{hour:02d}:00")
        temps.append(float(h))  # القيمةُ = عددُ الساعات منذ منتصف الليل
        winds.append(10.0 + h)
    return {
        "time": times,
        "temperature_2m": temps,
        "relative_humidity_2m": [50.0] * len(times),
        "precipitation": [0.0] * len(times),
        "cloud_cover": [0.0] * len(times),
        "wind_speed_10m": winds,
        "wind_direction_10m": [90.0] * len(times),
        "wind_gusts_10m": winds,
        "surface_pressure": [1000.0] * len(times),
    }


def test_plus_one_hour_resolves_to_the_next_hour_not_to_one_am(ws):
    """الشكلُ الذي شُحِن: `+1h` في 15:10 كان يُرجِع القيمةَ عند الفهرس 1 = 01:00 فجراً."""
    hourly = _hourly_from_midnight()
    resolution = ws.resolve_hourly_index(hourly["time"], f"{_DAY}T15:10", 1)
    assert resolution["policy"] == "exact"
    assert resolution["resolved"] == f"{_DAY}T16:00"
    assert resolution["index"] == 16
    assert resolution["limitations"] == []
    # التكذيبُ الصريح: القاعدةُ القديمة (idx = offset) كانت تُعطي 1.
    assert resolution["index"] != 1


def test_weather_service_tile_sample_carries_the_resolved_hour_value(ws):
    data = {"current": {"time": f"{_DAY}T15:10"}, "hourly": _hourly_from_midnight()}
    sample = ws.normalize_tile_sample(data, lat=15.0, lon=44.0, time_key="+3h", model="best_match")
    assert sample["time"] == f"{_DAY}T18:00"
    assert sample["temperature_c"] == 18.0, (
        "القيمةُ من 03:00 فجراً لا من 18:00 — الفهرسُ ما زال موضعيّاً"
    )
    assert sample["time_resolution"]["policy"] == "exact"


def test_a_six_hourly_series_never_returns_plus_six_as_plus_one(ws):
    """+6h يُختار **بطابعه**؛ و+1h في سلسلةٍ ٦-ساعيّة يُعلَن قيداً لا يُستبدَل بصمت."""
    hourly = _hourly_from_midnight(step_hours=6, hours=48)  # 00, 06, 12, 18, 00, …
    anchor = f"{_DAY}T12:05"

    six = ws.resolve_hourly_index(hourly["time"], anchor, 6)
    assert six["policy"] == "exact"
    assert six["resolved"] == f"{_DAY}T18:00"
    assert hourly["temperature_2m"][six["index"]] == 18.0  # لا 36.0 (الفهرس 6 بالموضع)

    one = ws.resolve_hourly_index(hourly["time"], anchor, 1)
    assert one["policy"] == "nearest"
    assert one["resolved"] == f"{_DAY}T12:00", "الأقربُ لـ13:00 هو 12:00 لا 18:00"
    assert one["delta_hours"] == -1.0
    assert any(lim.startswith("requested_time_not_in_series") for lim in one["limitations"])
    # وأبداً لا يُقرأ +6h على أنّه +1h:
    assert hourly["temperature_2m"][one["index"]] != 18.0


def test_no_anchor_means_no_index_and_honest_none_values(ws):
    hourly = _hourly_from_midnight()
    unanchored = ws.resolve_hourly_index(hourly["time"], None, 3)
    assert unanchored["policy"] == "unanchored"
    assert unanchored["index"] is None
    assert "sampling_anchor_unavailable" in unanchored["limitations"]
    sample = ws.normalize_tile_sample(
        {"hourly": hourly}, lat=15.0, lon=44.0, time_key="+3h", model="x"
    )
    assert sample["temperature_c"] is None, "بلا مرساةٍ كانت القيمةُ تُؤخَذ من منتصف الليل + 3"
    assert sample["time_resolution"]["policy"] == "unanchored"


def test_the_two_services_resolve_identically(ws, om):
    """نسختان في خدمتين لا تتشاركان حزمة — فالتطابقُ يُقاس لا يُفترَض."""
    hourly = _hourly_from_midnight(step_hours=3, hours=72)
    for anchor, offset in (
        (f"{_DAY}T15:10", 1),
        (f"{_DAY}T15:10", 3),
        (f"{_DAY}T23:59", 24),
        (None, 6),
    ):
        assert ws.resolve_hourly_index(hourly["time"], anchor, offset) == om.resolve_hourly_index(
            hourly["time"], anchor, offset
        )


async def test_platform_tile_sample_resolves_by_timestamp_and_declares_it(om, monkeypatch):
    payload = {
        "current": {
            "time": f"{_DAY}T15:10",
            "temperature_2m": 33.3,
            "wind_direction_10m": 90.0,
            "wind_speed_10m": 5.0,
        },
        "hourly": _hourly_from_midnight(),
    }

    async def fake_fetch(url, params, timeout_s):
        return payload

    monkeypatch.setattr(om, "_fetch_json", fake_fetch)
    sample = await om.fetch_weather_tile_data(15.0, 44.0, time_key="+3h")
    assert sample["time"] == f"{_DAY}T18:00"
    assert sample["temperature_2m_c"] == 18.0
    assert sample["time_resolution"]["policy"] == "exact"
    assert sample["time_resolution"]["requested_offset_hours"] == 3


async def test_platform_now_sample_declares_one_time_and_names_the_hourly_row(om, monkeypatch):
    """مراجعةُ Copilot على #985، مُعاد إنتاجُها: `time` بدقائقه و`resolved` صفُّ الساعة.

    عيّنةُ `now` تخلط مصدرين بحقّ — حقولُ `current` عند 15:10، والحقولُ الساعيّةُ فقط
    (ET0/VPD/التربة) من صفّ 15:00 — فيُعلَن كلاهما باسمه: `resolved` يطابق `time`،
    وصفُّ الساعة يُسمّى `hourly_row_time` مع قيدٍ مقروء، ولا تُخفي إحداهما الأخرى.
    """
    hourly = _hourly_from_midnight()
    hourly["et0_fao_evapotranspiration"] = [float(i) for i in range(len(hourly["time"]))]
    payload = {
        "current": {"time": f"{_DAY}T15:10", "temperature_2m": 33.3, "wind_direction_10m": 90.0},
        "hourly": hourly,
    }

    async def fake_fetch(url, params, timeout_s):
        return payload

    monkeypatch.setattr(om, "_fetch_json", fake_fetch)
    sample = await om.fetch_weather_tile_data(15.0, 44.0, time_key="now")
    resolution = sample["time_resolution"]
    assert sample["time"] == f"{_DAY}T15:10"
    assert resolution["resolved"] == sample["time"], (
        "وقتان لعيّنةٍ واحدة — التناقضُ الذي أمسكته المراجعة"
    )
    assert resolution["anchor"] == resolution["target"] == sample["time"]
    assert resolution["policy"] == "current"
    assert sample["temperature_2m_c"] == 33.3, "حقلُ current يبقى من current"
    assert sample["et0_fao_evapotranspiration_mm"] == 15.0, "الحقلُ الساعيّ من صفّ 15:00 لا 15:10"
    assert resolution["hourly_row_time"] == f"{_DAY}T15:00"
    assert f"hourly_only_fields_from:{_DAY}T15:00" in resolution["limitations"]


async def test_platform_now_sample_on_the_hour_declares_no_split(om, monkeypatch):
    """حين يقع `current.time` على رأس الساعة لا يوجد صفٌّ مغاير فلا قيد."""
    payload = {
        "current": {"time": f"{_DAY}T15:00", "temperature_2m": 1.0},
        "hourly": _hourly_from_midnight(),
    }

    async def fake_fetch(url, params, timeout_s):
        return payload

    monkeypatch.setattr(om, "_fetch_json", fake_fetch)
    sample = await om.fetch_weather_tile_data(15.0, 44.0, time_key="now")
    resolution = sample["time_resolution"]
    assert (
        resolution["resolved"] == sample["time"] == resolution["hourly_row_time"] == f"{_DAY}T15:00"
    )
    assert not any(lim.startswith("hourly_only_fields_from") for lim in resolution["limitations"])


def test_a_null_at_the_exact_hour_stays_null_instead_of_borrowing_a_neighbour(om):
    """الاحتياطُ القديم كان يمسح المصفوفةَ أماماً وخلفاً — استبدالٌ صامتٌ على مستوى القيمة."""
    hourly = _hourly_from_midnight()
    hourly["temperature_2m"][16] = None
    resolution = om.resolve_hourly_index(hourly["time"], f"{_DAY}T15:10", 1)
    assert resolution["index"] == 16
    assert om._hourly_value_at(hourly, "temperature_2m", resolution["index"]) is None
