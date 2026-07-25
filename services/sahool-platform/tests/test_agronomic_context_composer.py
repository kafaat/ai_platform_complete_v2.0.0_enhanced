"""AC-COMPOSER (الشريحة 1) — اختبار وحدة للمُجمِّع الخادميّ الذرّيّ (بلا شبكة/قاعدة).

يؤكّد الضمانات الصادقة: نَسَب كامل لكلّ ميزة · لا اختلاق للمجموعات الغائبة · استبعاد التسرّب
الزمنيّ (PIT) · وسم المدخلات غير المتماسكة زمنيّاً · حتميّة الـdigest/idempotency.
"""

from datetime import datetime, timedelta

import pytest
from api.agronomic_context_composer import (
    CONTEXT_GROUPS,
    agronomic_context_compose_enabled,
    assemble_agronomic_context,
)

pytestmark = pytest.mark.unit

_AS_OF = datetime(2026, 5, 1, 12, 0, 0)
_CUTOFF = datetime(2026, 5, 1, 12, 0, 0)


def _feat(group, name, value, *, obs, avail, service="raster-service", q="verified"):
    return {
        "group": group,
        "name": name,
        "value": value,
        "source_service": service,
        "observed_at": obs,
        "available_at": avail,
        "quality_status": q,
    }


def _base_features():
    obs = _AS_OF - timedelta(hours=2)
    return [
        _feat("weather", "et0_mm", 5.1, obs=obs, avail=obs, service="weather-service"),
        _feat("soil", "taw_mm", 120.0, obs=obs, avail=obs, service="soil-service"),
        _feat("crop", "ndvi", 0.71, obs=obs, avail=obs, service="raster-service"),
    ]


def test_provenance_carried_on_every_feature():
    out = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=_base_features(),
    )
    for f in out["payload"]["features"]:
        # كلّ ميزة تحمل النَسَب الإلزاميّ (P0-2) — لا ميزة بلا مصدر/زمن/جودة.
        for key in ("source_service", "observed_at", "available_at", "quality_status"):
            assert f.get(key), f"ميزة بلا {key}: {f}"
    assert out["payload"]["idempotency_key"].startswith("acx_")


def test_missing_groups_are_not_fabricated():
    # ثلاث مجموعات فقط لها بيانات ⇒ الأربع الباقية missing بلا قيمة مُختلَقة.
    out = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id=None,
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=_base_features(),
        empty_group_reasons={"irrigation": "rainfed_no_system"},
    )
    ctx = out["payload"]["context"]
    assert set(ctx.keys()) == set(CONTEXT_GROUPS)  # كلّ المجموعات حاضرة بنيويّاً
    assert ctx["weather"]["quality"] == "verified"
    assert ctx["irrigation"] == {"quality": "missing", "reason": "rainfed_no_system"}
    assert ctx["terrain"]["quality"] == "missing"
    assert "irrigation" in out["limitations"]["missing_groups"]
    # لا قيمة مُختلَقة لمجموعة غائبة.
    assert "value" not in ctx["terrain"]


def test_future_leakage_feature_excluded():
    obs = _AS_OF - timedelta(hours=1)
    leaky = _feat(
        "weather", "forecast_et0", 4.0, obs=obs, avail=_CUTOFF + timedelta(hours=6)
    )  # أُتيح بعد قطع القرار ⇒ تسرّب مستقبليّ
    out = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=[*_base_features(), leaky],
    )
    names = {f["name"] for f in out["payload"]["features"]}
    assert "forecast_et0" not in names  # مُستبعَد
    assert "forecast_et0" in out["limitations"]["future_leakage_excluded"]


def test_temporal_incoherence_flagged():
    old = _feat(
        "soil", "taw_mm", 120.0, obs=_AS_OF - timedelta(days=10), avail=_AS_OF - timedelta(days=10)
    )
    fresh = _feat("weather", "et0_mm", 5.0, obs=_AS_OF - timedelta(hours=1), avail=_AS_OF)
    out = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=[old, fresh],
        max_temporal_skew_hours=48.0,
    )
    assert "inconsistent_inputs" in out["limitations"]
    assert out["temporal_skew_hours"] > 48.0


def test_deterministic_digest_and_idempotency():
    a = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=_base_features(),
    )
    b = assemble_agronomic_context(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        as_of_time=_AS_OF,
        decision_cutoff_time=_CUTOFF,
        features=list(reversed(_base_features())),  # ترتيب مختلف ⇒ نفس النتيجة (فرز داخليّ)
    )
    assert a["content_digest"] == b["content_digest"]
    assert a["payload"]["idempotency_key"] == b["payload"]["idempotency_key"]


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    assert agronomic_context_compose_enabled() is False
    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")
    assert agronomic_context_compose_enabled() is True
