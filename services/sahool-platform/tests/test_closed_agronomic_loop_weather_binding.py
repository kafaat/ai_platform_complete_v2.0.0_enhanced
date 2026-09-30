from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
sys.path.insert(0, str(API))

import weather_service_client as wc  # noqa: E402 — يتطلّب sys.path أعلاه

pytestmark = pytest.mark.unit


# قيمُ النَّسَب كما يُصدِرها المالكُ فعلاً (``canonical_weather_state.current_view``): إصدارُ الحالة
# semver، وهويّةُ المخطَّط حقلٌ مستقلّ. كان هذا الشاهد يضع اسمَ العائلة في ``canonical_state_version``
# — قيمةٌ لم يُصدِرها المالكُ قطّ — فمرّ بينما رُفِض الطقسُ حيّاً (2026-09-29). الشاهدُ المبنيّ من
# ناتج المُنتِج نفسِه في ``tests_v9/test_weather_views_survive_the_hop_to_the_platform.py``.
_OWNER_LINEAGE = {
    "derived_from": "canonical_weather_state",
    "canonical_state_id": "abc123",
    "canonical_state_version": "1.0.0",
    "canonical_schema_version": "wx10/canonical-weather-state/1.0.0",
}


def test_weather_binding_accepts_only_owner_canonical_lineage(monkeypatch):
    async def fake_get(*args, **kwargs):
        return {
            "temperature_c": 24.0,
            "quality_status": "validated",
            "limitations": [],
            "observed_at": "2026-08-17T12:00:00+00:00",
            **_OWNER_LINEAGE,
            "source_snapshot_id": "wx-snapshot-1",
            "observed_fields": ["temperature_c"],
        }

    monkeypatch.setattr(wc, "weather_get_json", fake_get)
    state = asyncio.run(wc.get_canonical_field_weather(15.0, 44.0, tenant_id="t"))
    assert state is not None
    assert state["schema_version"] == "wx10/canonical-weather-state/1.0.0"
    assert state["state_version"] == "1.0.0"
    assert state["quality_status"] == "validated"
    assert state["evidence"]["source_snapshot_id"] == "wx-snapshot-1"


def test_a_state_version_is_never_promoted_to_a_schema_identity(monkeypatch):
    """مالكٌ لا يُعلن هويّةَ مخطَّطه ⇒ غيابٌ مُعلَن، لا ``1.0.0`` في مكان العائلة."""

    async def without_schema(*args, **kwargs):
        lineage = {k: v for k, v in _OWNER_LINEAGE.items() if k != "canonical_schema_version"}
        return {"quality_status": "validated", **lineage, "source_snapshot_id": "wx-snapshot-1"}

    monkeypatch.setattr(wc, "weather_get_json", without_schema)
    assert asyncio.run(wc.get_canonical_field_weather(15.0, 44.0, tenant_id="t")) is None


def test_weather_binding_rejects_raw_or_unprovenanced_weather(monkeypatch):
    async def raw(*args, **kwargs):
        return {"temperature_c": 24.0, "quality_status": "validated"}

    monkeypatch.setattr(wc, "weather_get_json", raw)
    assert asyncio.run(wc.get_canonical_field_weather(15.0, 44.0)) is None

    async def missing_snapshot(*args, **kwargs):
        return {**_OWNER_LINEAGE, "quality_status": "validated"}

    monkeypatch.setattr(wc, "weather_get_json", missing_snapshot)
    assert asyncio.run(wc.get_canonical_field_weather(15.0, 44.0)) is None


def test_weather_binding_fails_closed_on_transport_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("weather unavailable")

    monkeypatch.setattr(wc, "weather_get_json", boom)
    assert asyncio.run(wc.get_canonical_field_weather(15.0, 44.0)) is None


def test_soil_quality_gate_is_not_promoted_when_non_executable():
    # Structural assertion on the strict adapter: a diagnostic profile may be present
    # but cannot become proposal-healthy merely because quality_gate.passed is true.
    source = (API / "canonical_soil_state.py").read_text(encoding="utf-8")
    assert "passed is True and executable is True" in source
    assert 'normalized["operational_eligible"] = False' in source


def test_internal_field_state_resolves_weather_from_owner_not_local_math():
    source = (API / "routers" / "internal_service.py").read_text(encoding="utf-8")
    assert "get_canonical_field_weather" in source
    assert "weather=weather_payload" in source
    assert "weather=None" not in source, (
        "حقل الطقس لا يُصفَّر محليّاً — غيابه يأتي من فشل المالك المغلق لا من ثابت"
    )
    assert "build_canonical_weather_state" not in source, (
        "المنصّة لا تبني حالة طقس قانونيّة — البناء حكر على weather-service المالك"
    )
