"""توجيه محاكاة المحصول في supervisor إلى agriai-engine — وسم المحرّك صادق، ولا رقم بلا مصدر.

العطل المُغلَق (مراجعة Sahool v25، البند 7 / النتيجة 3): ``crop_model_skill`` كان ينادي أداة MCP
``run_wofost_simulation`` التي تردّ 501 بالتصميم (``services/mcp_servers/wofost_server.py``)، فكان
«توقّع المحصول» ميتاً دائماً بينما المحرّك (PCSE) وبديله الحتميّ يعيشان في agriai-engine.

يُثبِت هنا سلوكيّاً:
  • المهارة تنادي ``POST /v1/simulate`` بتوكن ``X-Agent-Token`` — ضدّ تطبيق agriai **الحقيقيّ**
    (ASGI داخل العمليّة) لا ضدّ نسخة مُتخيَّلة من عقده.
  • ``provenance`` يُنقَل حرفيّاً ويُسمّي المحرّك: PCSE ⇒ «غير مُعايَر»، البديل ⇒ «ليس WOFOST».
  • وسمٌ مجهول/غائب ⇒ ``unavailable`` لا رقم. agriai متعطّل ⇒ استثناء httpx يُحوّله المسار إلى
    ``degraded`` (لا أرقام). فشل agriai المُغلَق (503) ⇒ ``unavailable`` بسببه المُصنَّف.
  • لا مدخلات مُختلَقة: بلا محصول أو طقس ⇒ ``unavailable`` دون نداء.
منطق صرف بلا خدمات — ``pytest -m unit``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

pytestmark = pytest.mark.unit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUPERVISOR = os.path.join(ROOT, "services", "supervisor-agent")
AGRIAI = os.path.join(ROOT, "services", "agriai-engine")
for _p in (SUPERVISOR, AGRIAI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcp_client import classify_mcp_error  # noqa: E402
from skills.crop_model_skill import CropModelSkill  # noqa: E402

TOKEN = "crop-model-routing-token"
_WEATHER = {"gdd": 1600.0, "total_rain_mm": 300.0}


def _load_agriai(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    spec = importlib.util.spec_from_file_location(
        "agriai_main_under_crop_model_test", os.path.join(AGRIAI, "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _route_to(monkeypatch, transport):
    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: factory(transport=transport, **kwargs)
    )


def _simulate(context):
    skill = CropModelSkill(mcp_client=None)
    return asyncio.run(skill.execute("simulate_current", context=context))


def test_fallback_from_real_agriai_is_labelled_fallback_not_wofost(monkeypatch):
    monkeypatch.setenv("SIM_PCSE_ENABLED", "0")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "0")
    agriai = _load_agriai(monkeypatch)
    seen = []

    class Spy(httpx.ASGITransport):
        async def handle_async_request(self, request):
            seen.append(request)
            return await super().handle_async_request(request)

    _route_to(monkeypatch, Spy(app=agriai.app))
    out = _simulate({"crop": "Wheat", "weather": _WEATHER, "soil": {"available_water_mm": 80.0}})

    assert [r.url.path for r in seen] == ["/v1/simulate"]
    assert seen[0].headers["x-agent-token"] == TOKEN
    assert out["type"] == "crop_simulation"
    assert out["provenance"] == "deterministic_fallback"  # حرفيّاً كما أعاده agriai
    assert out["engine"] == "deterministic_fallback"
    assert out["calibrated"] is False
    assert "ليس WOFOST" in out["response"] and "ليس WOFOST" in out["engine_label_ar"]
    assert "agriai deterministic fallback (not WOFOST)" in out["sources"]
    assert out["yield_kg_ha"] > 0
    interval = out["yield_interval"]
    assert interval["low_kg_ha"] <= out["yield_kg_ha"] <= interval["high_kg_ha"]
    # {"name": "wheat"} ليس معاملات: الموجِّه يُسمّي الافتراضات بدل إخفائها.
    assert "default_crop_params" in interval["drivers"]
    assert "deterministic_fallback_model" in interval["drivers"]
    assert out["actionable"] is False


def test_pcse_provenance_is_propagated_as_uncalibrated_pcse(monkeypatch):
    body = {
        "yield_kg_ha": 5400.0,
        "biomass": 12000.0,
        # ملّيمتر: المُحوِّل يُحوّل CTRAT (سم) ×10 بنفسه الآن. كانت المهارة تضرب ×10 هنا،
        # فبقاء الضرب بعد إصلاح المُحوِّل كان سيُعيد 300 ملم لنتح 30 ملم.
        "water_use": 30.0,
        "stages": [{"stage": "maturity", "reached": True, "date": "2006-07-21", "at_dvs": 2.0}],
        "provenance": "pcse_wofost_uncalibrated",
        "yield_interval": {"low_kg_ha": 4700.0, "high_kg_ha": 6100.0, "confidence": "high"},
        "diagnostics": {"defaults_applied": ["soil.SM0", "site.WAV", "weather.angstrom_ab"]},
    }
    _route_to(monkeypatch, httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    out = _simulate({"crop": "wheat", "weather": {"daily": [{"tmax": 25, "tmin": 10}]}})

    assert out["type"] == "crop_simulation"
    assert out["provenance"] == "pcse_wofost_uncalibrated"
    assert out["engine"] == "pcse_wofost72_wlp_fd"
    assert out["calibrated"] is False and "غير مُعايَر" in out["response"]
    assert out["structured"]["provenance"] == "pcse_wofost_uncalibrated"
    assert out["total_water_mm"] == 30.0  # عقد المخطّط ملّيمتر في المحرّكين — لا ضرب ثانٍ
    assert "PCSE Wofost72_WLP_FD (uncalibrated)" in out["sources"]
    # الغلّة TWSO مادّة جافّة، والافتراضات المُعلَنة تُقال في النصّ وتُنقَل في structured.
    assert "مادّة جافّة" in out["response"]
    assert "تربة افتراضيّة" in out["response"] and "السعة الحقليّة" in out["response"]
    assert out["structured"]["defaults_applied"] == ["soil.SM0", "site.WAV", "weather.angstrom_ab"]


def test_pcse_input_rejection_422_carries_the_named_reason(monkeypatch):
    """بُناة PCSE يُسمّون النقص؛ كانت المهارة تختزل 422 إلى «مرفوض» بلا سبب."""
    detail = {
        "error": "simulation_inputs_invalid",
        "reason": "weather_day_missing",
        "detail": "0:vapour_pressure_hpa|vapour_pressure_kpa",
    }
    _route_to(
        monkeypatch,
        httpx.MockTransport(lambda request: httpx.Response(422, json={"detail": detail})),
    )
    out = _simulate({"crop": "wheat", "weather": _WEATHER})
    assert out["type"] == "unavailable"
    assert out["structured"]["reason"] == "crop_model_inputs_rejected"
    assert out["structured"]["engine_reason"] == "weather_day_missing"
    assert out["structured"]["engine_detail"] == "0:vapour_pressure_hpa|vapour_pressure_kpa"
    assert "yield_kg_ha" not in out


@pytest.mark.parametrize("provenance", [None, "", "wofost_rue", "pcse_wofost"])
def test_unknown_or_missing_provenance_yields_no_number(monkeypatch, provenance):
    body = {"yield_kg_ha": 9999.0, "biomass": 1.0, "water_use": 1.0}
    if provenance is not None:
        body["provenance"] = provenance
    _route_to(monkeypatch, httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    out = _simulate({"crop": "wheat", "weather": _WEATHER})
    assert out["type"] == "unavailable"
    assert out["structured"]["reason"] == "crop_model_provenance_unrecognized"
    assert "yield_kg_ha" not in out and "9999" not in out["response"]


def test_agriai_unreachable_raises_for_degraded_path_not_numbers(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("agriai down", request=request)

    _route_to(monkeypatch, httpx.MockTransport(refuse))
    with pytest.raises(httpx.HTTPError) as exc:
        _simulate({"crop": "wheat", "weather": _WEATHER})
    # هذا ما تلتقطه routers/agent.py فتُعيد ``degraded`` بـconfidence=0.
    assert classify_mcp_error(exc.value) == "network_error"


def test_agriai_unclassified_5xx_raises(monkeypatch):
    _route_to(monkeypatch, httpx.MockTransport(lambda request: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        _simulate({"crop": "wheat", "weather": _WEATHER})


def test_agriai_fail_closed_503_is_unavailable_with_reason(monkeypatch):
    """agriai الحقيقيّ في وضع الإنتاج بلا محرّك ⇒ 503 مُصنَّف ⇒ ``unavailable`` لا بديل صامت."""
    monkeypatch.setenv("SIM_PCSE_ENABLED", "0")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "1")
    agriai = _load_agriai(monkeypatch)
    _route_to(monkeypatch, httpx.ASGITransport(app=agriai.app))
    out = _simulate({"crop": "wheat", "weather": _WEATHER})
    assert out["type"] == "unavailable"
    assert out["structured"]["reason"] == "crop_simulation_unavailable"
    assert out["structured"]["engine_reason"] == (
        "agriai_production_simulation_unavailable:sim_pcse_disabled"
    )
    assert "yield_kg_ha" not in out


def test_agriai_flag_on_without_pcse_returns_classified_503(monkeypatch):
    """كانت RuntimeError المُحوِّل تتسرّب 500 عارية؛ الآن 503 برمزها المُصنَّف."""
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "0")
    agriai = _load_agriai(monkeypatch)
    if agriai.wa.pcse_available():  # pragma: no cover - بيئة بها pcse
        pytest.skip("pcse مُركَّب هنا؛ الحالة تخصّ غيابه")
    from fastapi.testclient import TestClient

    resp = TestClient(agriai.app).post(
        "/v1/simulate",
        json={
            "crop": {"name": "wheat"},
            "weather": {"daily": [{"tmax": 25, "tmin": 10}]},
            "soil": {"available_water_mm": 80},
            "agromanagement": {"irrigation_mm": 20},
        },
        headers={"x-agent-token": TOKEN},
    )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["error"] == "simulation_unavailable"
    assert detail["reason"] == "simulation_unavailable:pcse_unavailable"


@pytest.mark.parametrize(
    "context, reason",
    [
        ({"weather": _WEATHER}, "crop_required"),
        ({"crop": "wheat"}, "crop_model_weather_required"),
        ({"crop": "wheat", "weather": {"total_rain_mm": 100}}, "crop_model_weather_required"),
    ],
)
def test_missing_inputs_are_not_invented_and_no_call_is_made(monkeypatch, context, reason):
    def never(request):
        raise AssertionError("لا نداء بلا مدخلات — كانت تُختلَق wheat/2026-01-15/medium")

    _route_to(monkeypatch, httpx.MockTransport(never))
    out = _simulate(context)
    assert out["type"] == "unavailable" and out["structured"]["reason"] == reason


def test_pcse_band_no_longer_carries_fallback_driver():
    """``_pcse_run`` يوسم ``pcse_wofost_uncalibrated``؛ المساواة الحرفيّة بـ``pcse_wofost`` كانت
    تُلصِق ``deterministic_fallback_model`` بمُخرَج PCSE — وسم محرّك كاذب في الموجِّهات."""
    import wofost_adapter as wa

    band = wa._yield_uncertainty(
        {"yield_kg_ha": 5000.0, "provenance": "pcse_wofost_uncalibrated"},
        {"name": "wheat"},
        {"daily": [{"tmax": 25, "tmin": 10}], "total_rain_mm": 100},
        {"available_water_mm": 80},
        {"irrigation_mm": 20},
    )
    assert "deterministic_fallback_model" not in band["drivers"]
    assert "default_crop_params" not in band["drivers"]  # PCSE يأخذ معاملاته بالاسم
    assert band["relative_uncertainty"] < 0.25


def test_mcp_wofost_501_points_to_the_single_owner():
    """مسار MCP يبقى 501 نهائيّاً ويُسمّي المالك — لا مساران متناقضان بلا تفسير."""
    src = open(
        os.path.join(ROOT, "services", "mcp_servers", "wofost_server.py"), encoding="utf-8"
    ).read()
    skill = open(os.path.join(SUPERVISOR, "skills", "crop_model_skill.py"), encoding="utf-8").read()
    assert "status_code=501" in src and "agriai-engine" in src and "/v1/simulate" in src
    assert "run_wofost_simulation" not in skill.split('"""', 2)[2]  # لا نداء MCP بعد الوثيقة
    assert "/v1/simulate" in skill and "X-Agent-Token" in skill
