"""Guard: the lodging/pollination/chill weather facades wire to real producers.

يضمن أنّ كلّ منتج من عائلة إجهاد المحصول له **مستهلِك حقيقيّ** (façade حول field_id)
يستدعي weather-service عبر العميل، لا نقطة يتيمة؛ ويثبت عقود الصدق للمنتِجات.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_client_exposes_crop_stress_calls():
    client = _read("services/sahool-platform/api/weather_service_client.py")
    for fn, path in (
        ("get_lodging_risk", "/v1/weather/lodging-risk"),
        ("get_pollination_risk", "/v1/weather/pollination-risk"),
        ("get_chill_accumulation", "/v1/weather/chill-accumulation"),
    ):
        assert f"async def {fn}(" in client, fn
        assert f'"{path}"' in client, path


def test_aggregate_facade_consumes_all_producers():
    # مُجمَّع في راوتر واحد (فلسفة التفكيك: لا نموّ راوترات المنصّة) يستهلك الثلاثة.
    facade = _read("services/sahool-platform/api/routers/field_workspace_weather.py")
    assert '@router.get("/api/v1/fields/{field_id}/weather/crop-stress")' in facade
    for call in ("get_lodging_risk(", "get_pollination_risk(", "get_chill_accumulation("):
        assert call in facade, call


def test_producer_endpoints_registered():
    main = _read("services/weather-service/main.py")
    for reg in (
        'app.get("/v1/weather/lodging-risk")(rt.lodging_risk)',
        'app.get("/v1/weather/pollination-risk")(rt.pollination_risk)',
        'app.get("/v1/weather/chill-accumulation")(rt.chill_accumulation)',
    ):
        assert reg in main, reg


def test_producers_are_honest():
    lodging = _read("services/weather-service/lodging_risk.py")
    pollination = _read("services/weather-service/pollination_risk.py")
    chill = _read("services/weather-service/chill_accumulation.py")
    # fail-closed + supporting role in each
    for src in (lodging, pollination, chill):
        assert '"evidence_role": "supporting"' in src
    assert '"status": "insufficient_context"' in lodging
    # pollination is fail-closed OUTSIDE flowering (not fabricated risk)
    assert '"status": "not_applicable"' in pollination
    assert "outside_flowering_window" in pollination
    # chill does not fake the Dynamic model
    assert '"dynamic_model": "not_implemented"' in chill
