"""Real consumer functions with DB/weather/raster transport doubles, no live services."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from api.canonical_water_stress import canonical_water_stress

pytestmark = pytest.mark.unit


def _row():
    return dict(
        depletion_mm=90,
        taw_mm=100,
        depletion_confidence=0.9,
        ndmi=-0.1,
        msi=1.222222,
        ndmi_date="2026-10-28",
        msi_date="2026-10-28",
        quality_status="validated",
    )


def test_missing_age_policy_is_not_confirmation():
    result = canonical_water_stress(_row())
    assert result["spectral_confirmation_available"] is False
    assert result["escalation_eligible"] is False
    assert result["spectral_freshness"]["reason"] == "freshness_policy_not_configured"


@pytest.mark.parametrize("age,expected", [(0, True), (12, True), (13, False), (-1, False)])
def test_explicit_age_boundary_and_future(age, expected):
    row = _row()
    row["ndmi_date"] = row["msi_date"] = (date(2026, 10, 29) - timedelta(days=age)).isoformat()
    result = canonical_water_stress(row, as_of="2026-10-29", max_spectral_age_days=12)
    assert result["spectral_confirmation_available"] is expected
    assert result["escalation_eligible"] is expected


@pytest.mark.parametrize(
    "quality,age,available",
    [
        ("validated", 0, True),
        ("unknown", 0, False),
        ("validated", 13, False),
        ("validated", -1, False),
    ],
)
@pytest.mark.parametrize("consumer", ["projection", "recommendation"])
def test_actual_consumers_use_per_index_qa_and_explicit_age(
    monkeypatch, quality, age, available, consumer
):
    import api.field_state_projection as projection
    import api.raster_service_client as transport
    import api.routers.irrigation_recommendation as recommendation
    from api.irrigation_models import FieldIrrigationRequest

    calls = []
    day = (date.today() - timedelta(days=age)).isoformat()

    async def grid(field_id, **kwargs):
        calls.append((field_id, kwargs["tenant_id"], kwargs["index"]))
        ix = kwargs["index"]
        return dict(
            field_id=field_id,
            tenant_id=kwargs["tenant_id"],
            real_data=True,
            source="sentinel-2",
            quality_status=quality,
            date=day,
            stats={"mean": {"ndvi": 0.4, "ndre": 0.2, "ndmi": -0.1, "msi": 1.222222}[ix]},
            product_id="product:" + ix,
            scene_id="scene-1",
        )

    monkeypatch.setattr(transport, "get_indicator_grid", grid)

    class Conn:
        def transaction(self):
            @contextlib.asynccontextmanager
            async def tx():
                yield self

            return tx()

        async def fetchval(self, sql, *args):
            if "tenant_id FROM fields" in sql:
                return "tenant-1"
            return None

        async def fetchrow(self, sql, *args):
            if "FROM seasons" in sql:
                return {"season_id": "season-1"}
            if "FROM water_ledger" in sql:
                return dict(
                    depletion_mm=90.0,
                    confidence=0.9,
                    soil_moisture_pct=None,
                    ledger_date=date.today(),
                    age_hours=1.0,
                    decision="manual:measured",
                )
            return None

        async def fetch(self, sql, *args):
            return []

        async def execute(self, *args):
            return None

    conn = Conn()
    if consumer == "projection":

        async def freshness(*args):
            return dict(last_image_date=None, latest_soil_sampled_on=None, weather_age_hours=None)

        monkeypatch.setattr(projection, "gather_field_freshness", freshness)
        monkeypatch.setattr(projection, "_compose_agronomic", lambda *a, **kw: None)
        # Physical state is real; only TAW/RAW are an explicit fixture.
        import api.soil_water as soil

        monkeypatch.setattr(
            soil, "soil_water_params", lambda **kw: {"taw_mm": 100.0, "raw_fraction": 0.5}
        )
        result = asyncio.run(projection.recompute_field_state(conn, "field-1"))["state"][
            "water_stress"
        ]
        assert result["spectral_confirmation_available"] is available
        assert result["spectral_freshness"]["policy_applied"] is True
        assert result["spectral_freshness"]["max_age_days"] == 12
        assert result["escalation_eligible"] is available
    else:

        @contextlib.asynccontextmanager
        async def tc(user):
            yield conn

        async def context(*args):
            return (16.0, 44.9, "wheat", "mid", 40)

        async def engine(**kw):
            return dict(
                product="et0",
                et0_mm=5.0,
                method="fao56_penman_monteith",
                quality_status="validated",
                formula_version="fixture",
                unit="mm/day",
                valid_time=None,
                weather_snapshot_id="fixture",
                input_completeness=1.0,
                missing_inputs=[],
                invalid_inputs=[],
                limitations=[],
            )

        import api.water_ledger_auto as ledger

        # Existing status parser receives a known bootstrap observation, not a fabricated field source.
        async def applied(*args):
            return "recorded"

        monkeypatch.setattr(recommendation, "tenant_connection", tc)
        monkeypatch.setattr(recommendation, "_field_weather_context", context)
        monkeypatch.setattr(recommendation, "_engine_et0", engine)
        monkeypatch.setattr(ledger, "resolve_applied_water_status", applied)
        request = FieldIrrigationRequest(
            t_min_c=18.0,
            t_max_c=34.0,
            policy="water_saving",
            rain_recent_mm=0.0,
            forecast_rain_mm=3.0,
        )
        captured = []
        original = recommendation.canonical_water_stress

        def capture(*args, **kwargs):
            value = original(*args, **kwargs)
            captured.append(value)
            return value

        monkeypatch.setattr(recommendation, "canonical_water_stress", capture)
        result = asyncio.run(
            recommendation.field_irrigation_recommendation(
                "field-1", request, user=SimpleNamespace(tenant_id="tenant-1")
            )
        )
        assert result["status"] == "recommendation_ready"
        assert captured and captured[0]["spectral_confirmation_available"] is available
        assert captured[0]["spectral_freshness"]["policy_applied"] is True
        assert ("product:ndmi" in result["evidence_ids"]) is available
    assert len(calls) == 4
    assert {(f, t) for f, t, ix in calls} == {("field-1", "tenant-1")}


@pytest.mark.parametrize(
    "corruption", ["missing_record", "unknown_qa", "changed_value", "wrong_authority"]
)
def test_product_adapter_cannot_upgrade_unverified_pair(corruption):
    from api.canonical_water_stress import water_stress_spectral_inputs

    product = dict(
        schema="canonical_spectral_state.v1",
        source_authority="raster-service",
        quality_status="validated",
        indices={"ndmi": -0.1, "msi": 1.22},
        index_provenance={
            name: dict(
                value=value,
                quality_status="validated",
                acquisition_date="2026-10-28",
                product_id="product:" + name,
            )
            for name, value in [("ndmi", -0.1), ("msi", 1.22)]
        },
    )
    if corruption == "missing_record":
        del product["index_provenance"]["msi"]
    elif corruption == "unknown_qa":
        product["index_provenance"]["msi"]["quality_status"] = "unknown"
    elif corruption == "changed_value":
        product["indices"]["msi"] = 2.0
    else:
        product["source_authority"] = "client"
    result = canonical_water_stress(
        {**_row(), **water_stress_spectral_inputs(product)},
        as_of="2026-10-29",
        max_spectral_age_days=12,
    )
    assert result["spectral_confirmation_available"] is False
    assert result["escalation_eligible"] is False
