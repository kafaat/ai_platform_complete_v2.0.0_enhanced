"""W2-02 (decision-2, routes-3, decision-9) — one AC-1 path for every governed bridge.

The crop, water-ledger and MPC bridges recorded candidates with no agronomic lineage, so with
AC-1 enforced (always in production) decision-service answered each with a bare 422. These
tests fix, for each bridge, the acceptance rule: it either SENDS the full AC-1 lineage or
RETURNS ``blocked:lineage_missing`` — never a 422 (and never a raised HTTPException for it).

They also fix the deployment half: the composer flag is set in compose, the production overlay
and the Helm values, and both the platform and the water-ledger worker refuse to boot with AC-1
required and the composer off.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import api.crop_decision_bridge as crop_bridge
import api.decision_service_client as client
import pytest
import yaml
from api.agronomic_context_composer import (
    LINEAGE_MISSING_STATE,
    LINEAGE_REJECTED_STATE,
    REQUIRED_LINEAGE_FIELDS,
    agronomic_context_startup_error,
)
from api.lexicographic_irrigation_mpc import ForecastDay, solve_lexicographic_irrigation
from api.lexicographic_mpc_bridge import emit_mpc_candidate
from api.water_decision_bridge import process_water_deficit
from fastapi import HTTPException

pytestmark = [pytest.mark.unit]

_REPO = Path(__file__).resolve().parents[3]

_CTX_OK = {
    "persisted": True,
    "snapshot_id": "agctx_1",
    "historical_snapshot_id": "fhist_1",
    "feature_manifest_id": "fmanif_1",
    "feature_manifest_hash": "a" * 64,
}
_VEG_OK = {"snapshot_id": "veg_1", "quality_gate": {"executable": True, "reasons": []}}
_AC1_422 = HTTPException(
    status_code=422,
    detail={"code": "agronomic_context_required", "missing": ["vegetation_snapshot_id"]},
)


# ── fixtures: a stubbed decision-service (store-function level, no network) ──────────────
class _DecisionService:
    """Stands in for the three decision-service calls the bridges make."""

    def __init__(self, *, vegetation=_VEG_OK, record_raises=None):
        self.vegetation = vegetation
        self.record_raises = record_raises
        self.composed: list[dict] = []
        self.recorded: list[dict] = []

    async def compose(self, payload, *, tenant_id, requested_by):
        self.composed.append(payload)
        return _CTX_OK

    async def latest_vegetation(self, **_kw):
        if self.vegetation is None:
            raise HTTPException(status_code=404, detail="no vegetation snapshot available")
        return self.vegetation

    async def record(self, payload, *, tenant_id=None):
        self.recorded.append(payload)
        if self.record_raises is not None:
            raise self.record_raises
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "decision_id": payload.get("decision_id") or "dec_1",
            "stage": payload.get("stage"),
            "decision_value_digest": "b" * 64,
        }


@pytest.fixture
def ds(monkeypatch):
    import api.canonical_soil_state as soil_state

    async def _no_soil(**_kw):
        return None

    monkeypatch.setattr(soil_state, "resolve_canonical_soil_state", _no_soil)
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", "true")
    monkeypatch.delenv("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", raising=False)
    service = _DecisionService()
    monkeypatch.setattr(client, "compose_context_snapshot", service.compose)
    monkeypatch.setattr(client, "latest_vegetation_snapshot", service.latest_vegetation)
    monkeypatch.setattr(client, "record_decision", service.record)
    monkeypatch.setattr(crop_bridge, "record_decision", service.record)
    return service


def _crop_intelligence():
    return {
        "schema": "crop_intelligence_state.v2",
        "engine_version": "crop-intelligence/5.0.0",
        "field_id": "f1",
        "season_id": "s1",
        "confidence": "medium",
        "calibrated": False,
        "evidence_ids": ["e1"],
        "phenology": {"stage": "flowering", "gdd_cumulative": 500.0},
        "stress_flags": [{"code": "water_deficit", "source": "water"}],
        "stress_memory": {"product_version": "crop-stress-memory/2.0.0"},
        "limitations": [],
        "recommendation_context": {
            "schema": "crop_recommendation_context.v1",
            "stage": "flowering",
            "active_stress_codes": ["water_deficit"],
            "urgency": "high",
            "urgent_factors": [],
            "evidence_ids": ["e2"],
            "decision_boundary": {
                "is_decision": False,
                "consumer": "decision-service",
                "approval_required": True,
            },
        },
    }


async def _crop(cultivar="yecora"):
    return await crop_bridge.submit_crop_decision_candidate(
        _crop_intelligence(),
        gdd_product={
            "accumulated_gdd": 26.0,
            "gdd_lineage_id": "gddseq/abc123",
            "contributing_state_ids": ["snap-1"],
            "limitations": [],
            "calculation_version": "gdd/daily/1.0.0",
            "series_quality_status": "validated",
        },
        tenant_id="t1",
        submit=True,
        created_by="u1",
        crop="wheat",
        cultivar_id=cultivar,
    )


async def _water(cultivar="yecora"):
    return await process_water_deficit(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        ledger_date=date(2026, 7, 12),
        entry={"deficit_mm": 20.0, "depletion_mm": 55.0, "taw_mm": 120.0, "raw_mm": 60.0},
        crop="wheat",
        cultivar_id=cultivar,
    )


async def _mpc(cultivar="yecora"):
    decision = solve_lexicographic_irrigation(
        forecast=[ForecastDay(et0_mm=7.0, kc=1.1) for _ in range(5)],
        taw_mm=100.0,
        raw_fraction=0.5,
        initial_depletion_mm=45.0,
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        crop="wheat",
        growth_stage="flowering",
    )
    return await emit_mpc_candidate(decision, tenant_id="t1", cultivar_id=cultivar)


def _status(bridge: str, out: dict) -> str:
    return out["approval_state"] if bridge == "crop" else out["status"]


BRIDGES = {"crop": _crop, "water": _water, "mpc": _mpc}
RECORDED = {"crop": "pending_approval", "water": "candidate_created", "mpc": "candidate_created"}


# ── acceptance: each bridge sends AC-1, or returns blocked:lineage_missing ───────────────
@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_with_lineage_available_each_bridge_sends_the_full_ac1_lineage(ds, bridge):
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == RECORDED[bridge], f"{bridge}: not recorded: {out}"
    assert len(ds.recorded) == 1, f"{bridge}: expected exactly one record call, got {ds.recorded}"
    sent = ds.recorded[0]
    missing = [k for k in REQUIRED_LINEAGE_FIELDS if not sent.get(k)]
    assert missing == [], f"{bridge}: record payload lacks AC-1 fields {missing}"
    assert sent["vegetation_snapshot_id"] == "veg_1", f"{bridge}: vegetation not bound: {sent}"
    assert sent["agronomic_context_snapshot_id"] == "agctx_1", f"{bridge}: context not bound"
    assert sent["cultivar_id"] == "yecora", f"{bridge}: cultivar not from its owner: {sent}"


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_a_composed_context_carries_the_producers_identity_and_cutoff(ds, bridge):
    asyncio.run(BRIDGES[bridge]())
    assert len(ds.composed) == 1, f"{bridge}: the context must be composed exactly once"
    payload = ds.composed[0]
    assert payload["field_id"] == "f1" and payload["season_id"] == "s1", (
        f"{bridge}: composed for the wrong field/season: {payload}"
    )
    names = {f["name"] for f in payload["features"]}
    assert "crop_id" in names, f"{bridge}: crop identity missing from the composed features"
    assert payload["as_of_time"] == payload["decision_cutoff_time"], (
        f"{bridge}: as_of and cutoff differ: {payload}"
    )


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_without_a_vegetation_snapshot_each_bridge_is_blocked_by_name_and_records_nothing(
    ds, bridge
):
    ds.vegetation = None
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == LINEAGE_MISSING_STATE, f"{bridge}: not blocked: {out}"
    assert "vegetation_snapshot_id" in out["missing"], f"{bridge}: gap not named: {out}"
    assert ds.recorded == [], f"{bridge}: a blocked candidate must not be recorded"


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_a_season_without_cultivar_is_named_missing_never_filled(ds, bridge):
    out = asyncio.run(BRIDGES[bridge](cultivar=None))
    assert _status(bridge, out) == LINEAGE_MISSING_STATE, f"{bridge}: not blocked: {out}"
    assert out["missing"] == ["cultivar_id"], f"{bridge}: unexpected gap list: {out}"
    assert ds.recorded == [], f"{bridge}: nothing may be recorded without a cultivar"


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_decision_services_own_ac1_422_becomes_the_named_block_not_an_error(
    ds, monkeypatch, bridge
):
    # This process does not enforce AC-1 (staged), decision-service does: its 422 is mapped.
    monkeypatch.delenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    ds.record_raises = _AC1_422
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == LINEAGE_MISSING_STATE, f"{bridge}: 422 not mapped: {out}"
    assert out["missing"] == ["vegetation_snapshot_id"], f"{bridge}: service gap lost: {out}"


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_a_422_that_is_not_the_ac1_refusal_is_not_hidden(ds, bridge):
    ds.record_raises = HTTPException(status_code=422, detail="decision_value is malformed")
    with pytest.raises(HTTPException) as caught:
        asyncio.run(BRIDGES[bridge]())
    assert caught.value.status_code == 422, f"{bridge}: unrelated 422 was rewritten"


@pytest.mark.parametrize(
    "reason",
    [
        "vegetation_unavailable_at_cutoff",
        "decision_season_mismatch",
        "lineage_integrity_violation:x",
    ],
)
@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_decision_services_lineage_refusal_is_named_not_a_bare_422(ds, bridge, reason):
    # SoR path: decision-service refuses the lineage itself with a string reason code.
    ds.record_raises = HTTPException(status_code=422, detail=reason)
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == LINEAGE_REJECTED_STATE, f"{bridge}: refusal not named: {out}"
    assert out["reason"] == reason, f"{bridge}: refusal code lost: {out}"


# ── the MPC route binds the canonical season, never the client's ─────────────────────────
def _canonical_water(season_id="s1"):
    from api.canonical_water_state import CanonicalWaterState

    return CanonicalWaterState(
        schema_version="sahool.canonical_water_state.v1",
        tenant_id="t1",
        field_id="f1",
        season_id=season_id,
        crop="wheat",
        growth_stage="flowering",
        depletion_mm=45.0,
        depletion_confidence=0.9,
        ledger_date="2026-07-13",
        ledger_age_hours=3.0,
        taw_mm=100.0,
        raw_fraction=0.5,
        raw_mm=50.0,
        root_depth_m=0.9,
        soil_texture="governed_hydraulic_profile",
        forecast=[
            {"date": f"2026-07-{13 + i}", "et0_mm": 7.0, "kc": 1.1, "rain_mm": 0.0}
            for i in range(5)
        ],
        evidence={},
        quality_status="verified",
        operational_eligible=True,
        limitations=[],
        water_state_digest="a" * 64,
        weather_snapshot_digest="b" * 64,
        soil_profile_digest="c" * 64,
        season_state_digest="d" * 64,
    )


class _RouteUser:
    tenant_id = "t1"


@pytest.fixture
def mpc_route(ds, monkeypatch):
    import api.routers.irrigation_mpc as route

    async def _owned(_u, _f):
        return True

    async def _no_bindings(_u, _f):
        return []

    async def _canonical(_u, _f, _h):
        return _canonical_water("s1")

    cultivar_reads: list = []

    async def _cultivar(_u, season_id):
        cultivar_reads.append(season_id)
        return "yecora" if season_id == "s1" else "other-season-cultivar"

    monkeypatch.setattr(route, "_field_belongs_to_tenant", _owned)
    monkeypatch.setattr(route, "_active_field_source_bindings", _no_bindings)
    monkeypatch.setattr(route, "_source_canonical_water", _canonical)
    monkeypatch.setattr(route, "_season_cultivar", _cultivar)
    route_under_test = type("RouteUnderTest", (), {})()
    route_under_test.module = route
    route_under_test.cultivar_reads = cultivar_reads
    return route_under_test


def test_the_mpc_route_without_a_client_season_sends_ac1_for_the_canonical_season(ds, mpc_route):
    req = mpc_route.module.RecommendationRequest(horizon_days=5, submit=True)
    out = asyncio.run(mpc_route.module.irrigation_mpc_recommendation("f1", req, user=_RouteUser()))
    assert out["emit"]["status"] == "candidate_created", f"MPC route did not send AC-1: {out}"
    assert len(ds.recorded) == 1, f"exactly one candidate must be recorded: {ds.recorded}"
    sent = ds.recorded[0]
    assert sent["season_id"] == "s1", f"binding season is not the canonical one: {sent}"
    assert sent["cultivar_id"] == "yecora", f"cultivar not from the canonical season: {sent}"
    assert sent["decision_value"]["season_id"] == "s1", f"embedded season drifted: {sent}"
    assert mpc_route.cultivar_reads == ["s1"], f"cultivar read: {mpc_route.cultivar_reads}"


def test_the_mpc_route_refuses_a_client_season_other_than_the_canonical_one(ds, mpc_route):
    req = mpc_route.module.RecommendationRequest(horizon_days=5, submit=True, season_id="s2")
    out = asyncio.run(mpc_route.module.irrigation_mpc_recommendation("f1", req, user=_RouteUser()))
    assert out["status"] == "blocked", f"mismatched season was not refused: {out}"
    assert out["reason"] == "season_mismatch", f"unexpected reason: {out}"
    assert out["season_id"] == "s1", f"canonical season not named: {out}"
    assert ds.recorded == [] and ds.composed == [], "nothing may be composed or recorded"
    assert mpc_route.cultivar_reads == [], "no cultivar may be read for a refused season"


def test_the_mpc_route_accepts_a_client_season_equal_to_the_canonical_one(ds, mpc_route):
    req = mpc_route.module.RecommendationRequest(horizon_days=5, submit=True, season_id="s1")
    out = asyncio.run(mpc_route.module.irrigation_mpc_recommendation("f1", req, user=_RouteUser()))
    assert out["emit"]["status"] == "candidate_created", f"matching season was refused: {out}"
    assert ds.recorded[0]["season_id"] == "s1", f"wrong season recorded: {ds.recorded}"


# ── water-ledger worker: a blocked outcome does not take the day's event key ─────────────
def test_a_blocked_water_outcome_keeps_its_own_event_dedup_key():
    from api.phase_runtime_workers import _water_deficit_dedup_key

    day = date(2026, 7, 12)
    blocked = _water_deficit_dedup_key("t1", "f1", day, {"status": LINEAGE_MISSING_STATE})
    created = _water_deficit_dedup_key("t1", "f1", day, {"status": "candidate_created"})
    assert blocked != created, "a morning block would drop the later candidate's event"
    assert created == "water-deficit:t1:f1:2026-07-12", f"success key changed: {created}"
    again = _water_deficit_dedup_key("t1", "f1", day, {"status": LINEAGE_MISSING_STATE})
    assert blocked == again, "the same blocked outcome must still dedupe within the day"


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_enforced_with_the_composer_off_nothing_is_composed_or_recorded(ds, monkeypatch, bridge):
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == LINEAGE_MISSING_STATE, f"{bridge}: not blocked: {out}"
    assert ds.composed == [] and ds.recorded == [], f"{bridge}: composer off must call nothing"
    assert "AGRONOMIC_CONTEXT_COMPOSE_ENABLED" in out["lineage"]["detail"]["composer"], (
        f"{bridge}: the reason is not named: {out}"
    )


@pytest.mark.parametrize("bridge", sorted(BRIDGES))
def test_not_enforced_and_composer_off_the_bridge_records_exactly_as_before(
    ds, monkeypatch, bridge
):
    for name in (
        "DECISION_REQUIRE_AGRONOMIC_CONTEXT",
        "AGRONOMIC_CONTEXT_COMPOSE_ENABLED",
        "SAHOOL_ENV",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    out = asyncio.run(BRIDGES[bridge]())
    assert _status(bridge, out) == RECORDED[bridge], f"{bridge}: staged path changed: {out}"
    sent = ds.recorded[0]
    bound = [k for k in REQUIRED_LINEAGE_FIELDS if k in sent and k != "season_id"]
    assert bound == [], f"{bridge}: lineage fields attached with the composer off: {bound}"


# ── boot refusal (decision-9) ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "env,compose,refused",
    [
        ({"SAHOOL_ENV": "production"}, None, True),
        ({"SAHOOL_ENV": "production"}, "false", True),
        ({"SAHOOL_ENV": "production"}, "true", False),
        ({"DECISION_REQUIRE_AGRONOMIC_CONTEXT": "true"}, None, True),
        ({}, None, False),
    ],
)
def test_the_boot_check_refuses_ac1_required_with_the_composer_off(
    monkeypatch, env, compose, refused
):
    for name in (
        "SAHOOL_ENV",
        "ENVIRONMENT",
        "DECISION_REQUIRE_AGRONOMIC_CONTEXT",
        "AGRONOMIC_CONTEXT_COMPOSE_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if compose is not None:
        monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", compose)
    error = agronomic_context_startup_error()
    assert (error is not None) is refused, f"env={env} compose={compose}: got {error!r}"
    if refused:
        assert "AGRONOMIC_CONTEXT_COMPOSE_ENABLED" in error, f"flag not named: {error}"


def test_the_platform_lifespan_refuses_to_start_before_touching_the_database(monkeypatch):
    import api.main as main

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    touched = []

    async def _db():
        touched.append("db")

    monkeypatch.setattr(main, "_init_db_pool", _db)

    async def _start():
        async with main._lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="AGRONOMIC_CONTEXT_COMPOSE_ENABLED"):
        asyncio.run(_start())
    assert touched == [], "the database pool was opened before the AC-1 boot check refused"


def test_the_water_ledger_worker_refuses_to_start_with_the_bridge_on_and_composer_off(
    monkeypatch,
):
    import api.phase_runtime_workers as workers

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "x" * 40)
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    # No database URL: had the worker reached its connection step first, it would fail with
    # "JOBS_DATABASE_URL is required" instead — so the message proves the order.
    monkeypatch.delenv("JOBS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError) as refused:
        asyncio.run(workers.loop_worker("water_ledger"))
    message = str(refused.value)
    assert "AGRONOMIC_CONTEXT_COMPOSE_ENABLED" in message, f"refused for another reason: {message}"
    assert "JOBS_DATABASE_URL" not in message, "the worker reached its connection step first"


# ── deployment manifests (routes-3) ──────────────────────────────────────────────────────
def _compose_env(path: str, service: str) -> dict:
    data = yaml.safe_load((_REPO / path).read_text(encoding="utf-8"))
    return (data["services"][service] or {}).get("environment") or {}


def test_compose_passes_the_composer_flag_on_by_default_to_platform_and_worker():
    for service in ("sahool-platform", "sahool-water-ledger-worker"):
        env = _compose_env("docker-compose.v9.yml", service)
        assert env.get("AGRONOMIC_CONTEXT_COMPOSE_ENABLED") == (
            "${AGRONOMIC_CONTEXT_COMPOSE_ENABLED:-true}"
        ), f"{service}: composer flag not passed with a true default: {env}"


def test_the_production_overlay_pins_the_composer_on():
    env = _compose_env("docker-compose.production.yml", "sahool-platform")
    assert env.get("AGRONOMIC_CONTEXT_COMPOSE_ENABLED") == "true", f"overlay env: {env}"


@pytest.mark.parametrize("values", ["values.yaml", "values-production.yaml"])
def test_helm_values_set_the_composer_on_for_the_platform(values):
    data = yaml.safe_load((_REPO / "helm" / "sahool" / values).read_text(encoding="utf-8"))
    env = data["workloads"]["sahool-platform"].get("env") or {}
    assert env.get("AGRONOMIC_CONTEXT_COMPOSE_ENABLED") == "true", f"{values}: env {env}"
