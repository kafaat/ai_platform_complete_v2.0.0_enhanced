"""Manual UI source producer: explicit declaration + current server water, not execution."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import api.main  # noqa: F401
import pytest
from api.canonical_water_state import CanonicalWaterState
from api.irrigation_engineering_workspace import ManualIrrigationIntent, build_manual_source
from api.routers import irrigation_recommendation as route
from fastapi import HTTPException
from pydantic import ValidationError
from test_field_irrigation_recommendation_endpoint import _FakeConn, _patch

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-1111-1111-111111111111"
USER = SimpleNamespace(
    tenant_id=TENANT, user_id="22222222-2222-2222-2222-222222222222", username="operator"
)


def intent(**changes):
    now = datetime.now(UTC)
    data = dict(
        season_id="season_2026",
        system_id="pivot-1",
        irrigated_area_ha=4.0,
        application_efficiency=0.8,
        source_reference="Reviewed farm survey reference 17",
        observed_at=now - timedelta(days=1),
        valid_from=now,
        valid_until=now + timedelta(hours=1),
    )
    data.update(changes)
    return ManualIrrigationIntent(**data)


def canonical(**changes):
    data = dict(
        schema_version="1",
        tenant_id=TENANT,
        field_id="fld_1",
        season_id="season_2026",
        crop="wheat",
        growth_stage="mid",
        depletion_mm=60.0,
        depletion_confidence=0.9,
        ledger_date=date.today().isoformat(),
        ledger_age_hours=6.0,
        taw_mm=100.0,
        raw_fraction=0.5,
        raw_mm=50.0,
        root_depth_m=1.0,
        soil_texture="governed",
        forecast=[],
        evidence={
            "source": "fixture",
            "location": {"elevation_m": 123.0, "lat": 17.0, "lon": 45.0},
        },
        quality_status="verified",
        operational_eligible=True,
        limitations=[],
        water_state_digest="a" * 64,
        weather_snapshot_digest="b" * 64,
        soil_profile_digest="c" * 64,
        season_state_digest="d" * 64,
    )
    data.update(changes)
    return CanonicalWaterState(**data)


def source(**changes):
    c = canonical().to_dict()
    c["valid_until"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    data = dict(
        intent=intent(),
        tenant_id=TENANT,
        field_id="fld_1",
        season_id="season_2026",
        canonical=c,
        applied_status="recorded",
        recommendation={"should_irrigate": True, "target_refill_mm": 10},
        weather={"rain_recent_mm": 0},
        et0={"et0_mm": 5},
    )
    data.update(changes)
    return build_manual_source(**data)


def test_source_distinguishes_net_gross_volume_and_declared_evidence():
    value = source()
    assert (value["net_depth_mm"], value["target_depth_mm"], value["target_volume_m3"]) == (
        10,
        12.5,
        500,
    )
    assert value["specification"]["evidence_level"] == "user_declared"
    assert value["water_truth"]["applied_water_status"] == "recorded"
    assert (
        source(intent=intent(application_efficiency=0.9))["specification_digest"]
        != value["specification_digest"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("application_efficiency", True),
        ("application_efficiency", 0),
        ("application_efficiency", 1.1),
        ("irrigated_area_ha", float("nan")),
        ("irrigated_area_ha", float("inf")),
        ("irrigated_area_ha", 0),
        ("source_reference", " "),
        ("system_id", " "),
    ],
)
def test_spec_never_defaults_or_coerces_invalid_quantities(field, value):
    with pytest.raises(ValidationError):
        intent(**{field: value})


@pytest.mark.parametrize("status", [None, "unrecorded", "volume_untracked"])
def test_unknown_applied_water_never_becomes_plan_source(status):
    with pytest.raises(ValueError, match="applied_unknown"):
        source(applied_status=status)


def test_window_cannot_outlive_current_water_evidence():
    with pytest.raises(ValueError, match="validity"):
        source(intent=intent(valid_until=datetime.now(UTC) + timedelta(days=2)))


async def setup_route(monkeypatch, *, decision="auto:daily_balance", operational=True):
    conn = _FakeConn(depletion_mm=60, decision=decision)
    fetchrow = conn.fetchrow

    async def fetch(sql, *args):
        row = await fetchrow(sql, *args)
        if row and "FROM water_ledger" in sql:
            row["ledger_date"] = date.today()
        return row

    conn.fetchrow = fetch
    conn.execute = AsyncMock()
    _patch(monkeypatch, conn)
    monkeypatch.setattr(route, "has_permission", lambda *_: True)
    import api.canonical_water_state as water

    monkeypatch.setattr(
        water,
        "resolve_canonical_water_state",
        AsyncMock(return_value=canonical(operational_eligible=operational)),
    )
    monkeypatch.setattr(
        route,
        "_field_weather_snapshot",
        AsyncMock(
            return_value=dict(
                t_min_c=18,
                t_max_c=34,
                source="weather-engine-forecast",
                valid_time=date.today().isoformat(),
                day_of_year=date.today().timetuple().tm_yday,
                rain_recent_mm=0,
                forecast_rain_mm=0,
            )
        ),
    )
    submit = AsyncMock(
        return_value={
            "authoritative": True,
            "persisted": True,
            "stage": "candidate",
            "decision_id": "dec-test",
        }
    )
    monkeypatch.setattr(route, "_submit_candidate_to_decision", submit)
    return conn, submit


async def test_route_persists_explicit_spec_and_binds_current_canonical_source_before_submit(
    monkeypatch,
):
    conn, submit = await setup_route(monkeypatch)
    result = await route.field_irrigation_recommendation(
        "fld_1",
        route.FieldIrrigationRequest(submit_to_decision=True, manual_execution=intent()),
        USER,
    )
    assert result["approval_state"] == "pending_approval"
    payload = submit.await_args.args[0]["decision_value"]
    snapshot = payload["manual_execution_source"]
    assert snapshot["water_truth"]["canonical"]["taw_mm"] == 100
    assert snapshot["water_truth"]["canonical"]["depletion_mm"] == 60
    assert snapshot["net_depth_mm"] == payload["recommendation"]["target_refill_mm"]
    assert snapshot["target_depth_mm"] == pytest.approx(snapshot["net_depth_mm"] / 0.8)
    assert snapshot["target_volume_m3"] == pytest.approx(snapshot["target_depth_mm"] * 4 * 10)
    assert "INSERT INTO irrigation_system_specifications" in conn.execute.await_args.args[0]
    assert payload["candidate_lineage_id"]


@pytest.mark.parametrize(
    "decision,operational",
    [(None, True), ("auto:irrigation_unobserved", True), ("auto:daily_balance", False)],
)
async def test_producer_blocks_unknown_water_before_persist_or_submit(
    monkeypatch, decision, operational
):
    conn, submit = await setup_route(monkeypatch, decision=decision, operational=operational)
    with pytest.raises(HTTPException) as exc:
        await route.field_irrigation_recommendation(
            "fld_1",
            route.FieldIrrigationRequest(submit_to_decision=True, manual_execution=intent()),
            USER,
        )
    assert exc.value.status_code == 409
    conn.execute.assert_not_called()
    submit.assert_not_called()


async def test_failed_spec_save_never_reports_candidate_submission(monkeypatch):
    conn, submit = await setup_route(monkeypatch)
    conn.execute.side_effect = RuntimeError("write unavailable")
    with pytest.raises(RuntimeError, match="write unavailable"):
        await route.field_irrigation_recommendation(
            "fld_1",
            route.FieldIrrigationRequest(submit_to_decision=True, manual_execution=intent()),
            USER,
        )
    submit.assert_not_called()


async def test_manual_source_forbids_client_weather_or_root_override(monkeypatch):
    conn, submit = await setup_route(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await route.field_irrigation_recommendation(
            "fld_1",
            route.FieldIrrigationRequest(
                submit_to_decision=True, manual_execution=intent(), root_depth_m=1
            ),
            USER,
        )
    assert exc.value.status_code == 422
    conn.execute.assert_not_called()
    submit.assert_not_called()


async def test_spec_scope_and_rollback_use_actual_tenant_connection(monkeypatch):
    """Exercise production context manager; SQL/transaction driver is mocked, not live PG."""
    from contextlib import asynccontextmanager

    from api import main
    from api.routers.irrigation_recommendation import persist_manual_specification

    events = []
    active = False
    conn = _FakeConn(depletion_mm=60)

    @asynccontextmanager
    async def transaction():
        nonlocal active
        active = True
        events.append("begin")
        try:
            yield
        except RuntimeError:
            events.append("rollback")
            raise
        else:
            events.append("commit")
        finally:
            active = False

    async def execute(sql, *args):
        assert active
        if "set_config" in sql:
            assert args == (TENANT, USER.user_id, "manager")
            events.append("scope")
        else:
            assert "INSERT INTO irrigation_system_specifications" in sql
            assert args[1] == TENANT
            events.append("spec")
            raise RuntimeError("storage failure")

    conn.transaction = transaction
    conn.execute = execute

    @asynccontextmanager
    async def acquire():
        yield conn

    monkeypatch.setattr(main, "get_pool", lambda: SimpleNamespace(acquire=acquire))
    user = SimpleNamespace(**vars(USER), role="manager")
    with pytest.raises(RuntimeError, match="storage failure"):
        async with main.tenant_connection(user) as scoped:
            await persist_manual_specification(scoped, source(), USER.user_id)
    assert events == ["begin", "scope", "spec", "rollback"]
    assert active is False


async def test_plan_source_retry_preserves_authoritative_id_and_typed_timestamps(monkeypatch):
    from contextlib import asynccontextmanager

    from api import decision_service_client
    from api.routers import decision_review

    seen = []
    conn = _FakeConn(depletion_mm=60)

    async def execute(sql, *args):
        assert "ON CONFLICT (tenant_id,execution_plan_id) DO NOTHING" in sql
        assert args[0] == TENANT and args[1] == "plan-1"
        assert isinstance(args[11], datetime) and isinstance(args[12], datetime)
        seen.append(args)
        if len(seen) == 1:
            raise RuntimeError("source persistence failed")

    conn.execute = execute

    @asynccontextmanager
    async def tenant_connection(user):
        assert user.tenant_id == TENANT
        yield conn

    monkeypatch.setattr(decision_review, "tenant_connection", tenant_connection)
    persisted = dict(
        authoritative=True,
        persisted=True,
        decision_id="dec-1",
        review_id="review-1",
        candidate_lineage_id="lineage-1",
        plan_state="planned",
        execution_plan_id="plan-1",
        created_by=USER.user_id,
        created_at=datetime.now(UTC).isoformat(),
        plan_digest="a" * 64,
    )
    remote = AsyncMock(return_value=persisted)
    monkeypatch.setattr(decision_service_client, "create_execution_plan", remote)
    value = source()
    constraints = {k: v for k, v in value.items() if k not in ("specification", "water_truth")}
    req = decision_review.ExecutionPlanRequest(
        review_id="review-1",
        candidate_lineage_id="lineage-1",
        operation_type="manual_irrigation",
        planned_start=value["valid_from"],
        planned_end=value["valid_until"],
        constraints=constraints,
        idempotency_key="manual-plan:dec-1:review-1",
    )
    with pytest.raises(RuntimeError, match="persistence failed"):
        await decision_review.create_decision_execution_plan("dec-1", req, USER)
    result = await decision_review.create_decision_execution_plan("dec-1", req, USER)
    assert result["execution_plan_id"] == "plan-1"
    assert seen[0] == seen[1]
    assert remote.await_args_list[0] == remote.await_args_list[1]


async def test_manual_et0_uses_canonical_elevation_and_current_weather_day(monkeypatch):
    conn, submit = await setup_route(monkeypatch)
    engine = AsyncMock(wraps=route._engine_et0)
    monkeypatch.setattr(route, "_engine_et0", engine)
    await route.field_irrigation_recommendation(
        "fld_1",
        route.FieldIrrigationRequest(submit_to_decision=True, manual_execution=intent()),
        USER,
    )
    assert engine.await_args.kwargs["elevation_m"] == 123.0
    assert engine.await_args.kwargs["latitude_deg"] == 17.0
    route._field_weather_snapshot.assert_awaited_once_with(17.0, 45.0)
    assert engine.await_args.kwargs["day_of_year"] == date.today().timetuple().tm_yday
    submit.assert_awaited_once()


async def test_manual_current_weather_date_cannot_be_defaulted(monkeypatch):
    conn, submit = await setup_route(monkeypatch)
    weather = await route._field_weather_snapshot(0, 0)
    weather["day_of_year"] = None
    monkeypatch.setattr(route, "_field_weather_snapshot", AsyncMock(return_value=weather))
    with pytest.raises(HTTPException) as exc:
        await route.field_irrigation_recommendation(
            "fld_1",
            route.FieldIrrigationRequest(submit_to_decision=True, manual_execution=intent()),
            USER,
        )
    assert exc.value.status_code == 409
    submit.assert_not_called()
