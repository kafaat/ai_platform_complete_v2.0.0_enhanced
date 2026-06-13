"""بوّابة الحالة القانونيّة الموحّدة للحقل (Canonical Field State — Phase 1).

يثبّت أنّ طبقة الجمع (field_state_gateway) تحوّل مصادر النضارة القانونيّة إلى
مدخلات resolve_field_state بصدق: نضارة طازجة ⇒ ثقة عالية + حالة معقولة؛ غياب
المصادر ⇒ أعمار None + ثقة None (لا اختلاق) ⇒ resolve_field_state يعلن INSUFFICIENT.
وأنّ نقطة /api/v1/fields/{id}/state مُسجَّلة (GET) بعقدها. دالّات نقيّة بلا قاعدة.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def test_fresh_sources_yield_high_confidence(core_on_path):
    from api.field_state_gateway import build_state_inputs

    today = date(2026, 6, 13)
    out = build_state_inputs(
        last_image_date=date(2026, 6, 11),  # NDVI عمره يومان
        latest_soil_sampled_on=date(2026, 6, 1),
        weather_age_hours=3.0,
        today=today,
    )
    assert out["ndvi_age_days"] == 2.0
    assert out["soil_age_days"] == 12.0
    assert out["weather_age_hours"] == 3.0
    assert out["confidence_level"] == "high"  # صورة حديثة ⇒ ثقة عالية


def test_missing_sources_are_honest_none(core_on_path):
    from api.field_state_gateway import build_state_inputs

    out = build_state_inputs(
        last_image_date=None,
        latest_soil_sampled_on=None,
        weather_age_hours=None,
        today=date(2026, 6, 13),
    )
    # صدق: لا مصدر ⇒ لا عمر ولا ثقة مُلفَّقة
    assert out == {
        "confidence_level": None,
        "ndvi_age_days": None,
        "soil_age_days": None,
        "weather_age_hours": None,
    }


def test_stale_ndvi_lowers_confidence(core_on_path):
    from api.field_state_gateway import derive_confidence_level

    assert derive_confidence_level(2.0) == "high"
    assert derive_confidence_level(30.0) in {"low", "very_low"}
    assert derive_confidence_level(None) is None


def test_gateway_inputs_compose_into_resolve_field_state(core_on_path):
    """التكامل: مدخلات البوّابة تُمرَّر لـresolve_field_state وتنتج حالة رسميّة."""
    from api.field_operational_state import resolve_field_state
    from api.field_state_gateway import build_state_inputs

    # كلّ المصادر غائبة ⇒ بيانات ناقصة ⇒ INSUFFICIENT (صدق لا VALID مُلفَّق)
    inputs = build_state_inputs(
        last_image_date=None,
        latest_soil_sampled_on=None,
        weather_age_hours=None,
        today=date.today(),
    )
    state = resolve_field_state("fld_x", **inputs)
    assert state.validity.value == "insufficient"


def test_canonical_state_endpoint_registered(core_on_path):
    """نقطة /api/v1/fields/{field_id}/state مُسجَّلة GET (بوّابة مصدر الحقيقة)."""
    import api.main as m

    routes = {
        (getattr(r, "path", None), tuple(sorted(getattr(r, "methods", set()) or [])))
        for r in m.app.routes
    }
    path = "/api/v1/fields/{field_id}/state"
    methods = {meth for (p, ms) in routes if p == path for meth in ms}
    assert path in {p for (p, _) in routes}, "canonical state route غير مُسجَّلة"
    assert "GET" in methods
