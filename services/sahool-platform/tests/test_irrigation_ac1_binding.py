"""EX-WATER-01 path B — AC-1/AC-6 lineage for the field irrigation candidate.

decision-service refuses a governed decision without its agronomic lineage when AC-1 is
enforced (always in production). These tests fix:

1. the compose body is built by the existing server-side assembler from the route's own inputs
   and passes decision-service's own point-in-time policy;
2. identities come from their owners, the context references bind all-or-none, and anything
   missing is named — never filled in;
3. with the composer flag off nothing is composed: non-enforced environments behave as before,
   enforced ones get a named block instead of decision-service's unexplained 422;
4. the route sends the bound lineage, and maps decision-service's own AC-1 refusal to the same
   named block instead of a server error.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import api.decision_service_client as client
import api.routers.irrigation_recommendation as mod
import pytest
from api.agronomic_context_composer import (
    REQUIRED_LINEAGE_FIELDS,
    irrigation_candidate_compose_payload,
    irrigation_candidate_features,
    lineage_binding,
)
from fastapi import HTTPException

pytestmark = [pytest.mark.unit]

_REPO = Path(__file__).resolve().parents[3]
CUTOFF = datetime(2026, 7, 10, 6, 0, tzinfo=UTC)
INPUTS = {
    "depletion_mm": 60.0,
    "taw_mm": 120.0,
    "taw_source": "lab_texture",
    "soil_provenance": {
        "texture": {"value": "loam", "source": "lab_measured", "sampled_on": "2026-05-01"}
    },
    "ledger_age_hours": 5.0,
    "applied_water_status": "recorded",
    "crop": "wheat",
    "stage": "mid",
}
WX = {"source": "weather-engine-forecast", "valid_time": "2026-07-10"}
ET0 = {
    "et0_mm": 5.1,
    "method": "fao56_penman_monteith",
    "quality_status": "validated",
    "formula_version": "et0/fao56-pm/1.0.0",
    "weather_snapshot_id": "wsnap/sha1/1:deadbeefcafef00d",
}
SEASON = {"season_id": "season_2026", "cultivar": "yecora", "irrigation_type": "drip"}


def _features(**over):
    kw = dict(
        cutoff=CUTOFF,
        field_id="fld_1",
        crop_id="wheat",
        cultivar_id="yecora",
        days_since_sowing=40,
        inputs=INPUTS,
        ledger_date="2026-07-09",
        weather=WX,
        et0=ET0,
    )
    kw.update(over)
    return irrigation_candidate_features(**kw)


def _payload(features=None):
    return irrigation_candidate_compose_payload(
        tenant_id="t-1",
        field_id="fld_1",
        season_id="season_2026",
        cutoff=CUTOFF,
        features=_features() if features is None else features,
        inputs=INPUTS,
        ledger_date="2026-07-09",
    )


# ── 1) the compose body (existing assembler) ─────────────────────────────────────
def test_the_compose_body_passes_decision_services_point_in_time_policy(monkeypatch):
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.delenv("DECISION_REQUIRE_SOIL_PROFILE", raising=False)
    monkeypatch.syspath_prepend(str(_REPO / "services" / "decision-service"))
    for name in [
        m for m in sys.modules if m == "agronomic_context" or m.startswith("agronomic_context.")
    ]:
        monkeypatch.delitem(sys.modules, name)
    from agronomic_context.contracts import ContextComposeIn
    from agronomic_context.point_in_time import validate_composition

    assert validate_composition(ContextComposeIn(**_payload())) == []


def test_groups_the_route_does_not_hold_are_declared_missing_with_a_reason():
    ctx = _payload()["context"]
    for name in ("climate", "terrain", "operations"):
        assert ctx[name]["quality"] == "missing"
        assert ctx[name]["reason"] == "not composed by the field irrigation route"
    for name in ("crop", "soil", "irrigation", "weather"):
        assert ctx[name]["feature_count"] >= 1


def test_features_are_never_observed_or_available_after_the_cutoff():
    for f in _payload()["features"]:
        observed = datetime.fromisoformat(f["observed_at"])
        available = datetime.fromisoformat(f["available_at"])
        assert observed <= available <= CUTOFF, f


def test_a_derived_ledger_value_is_never_labelled_verified():
    depletion = next(f for f in _features() if f["name"] == "root_zone_depletion_mm")
    assert depletion["quality_status"] == "accepted_with_warning"


def test_an_absent_value_produces_no_feature_instead_of_a_zero():
    feats = _features(
        crop_id=None,
        cultivar_id=None,
        days_since_sowing=None,
        inputs={**INPUTS, "depletion_mm": None, "taw_mm": None},
        et0={"et0_mm": None},
    )
    assert feats == []
    assert _payload(feats)["context"]["irrigation"]["quality"] == "missing"


def test_a_naive_cutoff_is_refused():
    with pytest.raises(ValueError):
        _features(cutoff=datetime(2026, 7, 10, 6, 0))


# ── 2) binding decisions (pure) ──────────────────────────────────────────────────
_CTX_OK = {
    "persisted": True,
    "snapshot_id": "agctx_1",
    "historical_snapshot_id": "fhist_1",
    "feature_manifest_id": "fmanif_1",
    "feature_manifest_hash": "a" * 64,
}
_VEG_OK = {"snapshot_id": "veg_1", "quality_gate": {"executable": True, "reasons": []}}


def _bind(**over):
    kw = dict(
        season_id="season_2026",
        crop_id="wheat",
        cultivar_id="yecora",
        context=_CTX_OK,
        vegetation=_VEG_OK,
        required=True,
        detail={},
    )
    kw.update(over)
    return lineage_binding(**kw)


def test_a_complete_binding_carries_every_field_decision_service_requires():
    b = _bind()
    assert not b.missing and not b.blocked
    assert set(REQUIRED_LINEAGE_FIELDS) <= set(b.record_fields)
    assert b.report()["status"] == "bound"


def test_a_composer_answer_without_the_manifest_hash_binds_no_context_reference():
    partial = {k: v for k, v in _CTX_OK.items() if k != "feature_manifest_hash"}
    b = _bind(context=partial)
    assert not {
        "agronomic_context_snapshot_id",
        "field_historical_context_snapshot_id",
        "feature_manifest_id",
        "feature_manifest_hash",
    } & set(b.record_fields)
    assert b.blocked


def test_a_vegetation_snapshot_whose_gate_is_not_executable_is_not_bound():
    gated = {
        "snapshot_id": "veg_9",
        "quality_gate": {"executable": False, "reasons": ["ndvi_quality_below_threshold"]},
    }
    b = _bind(vegetation=gated)
    assert b.missing == ("vegetation_snapshot_id",)
    assert b.detail["vegetation"]["gate_reasons"] == ["ndvi_quality_below_threshold"]


def test_a_season_without_cultivar_is_reported_never_filled():
    b = _bind(cultivar_id="  ")
    assert b.missing == ("cultivar_id",)
    assert "cultivar_id" not in b.record_fields


def test_where_ac1_is_not_enforced_a_gap_does_not_block():
    b = _bind(context=None, vegetation=None, required=False)
    assert not b.blocked and b.report()["status"] == "partially_bound"


# ── 3) the network half and the composer flag ────────────────────────────────────
def _calls(result=None, raises=None):
    seen = []

    async def _f(*args, **kwargs):
        seen.append((args, kwargs))
        if raises is not None:
            raise raises
        return result

    return _f, seen


@pytest.mark.asyncio
async def test_with_the_composer_flag_off_nothing_is_composed(monkeypatch):
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    compose, seen = _calls(_CTX_OK)
    monkeypatch.setattr(client, "compose_context_snapshot", compose)
    b = await client.irrigation_candidate_lineage(
        object(), "fld_1", SEASON, INPUTS, WX, ET0, "2026-07-09", 40
    )
    assert seen == []
    assert b.blocked and "AGRONOMIC_CONTEXT_COMPOSE_ENABLED" in b.detail["composer"]


@pytest.mark.asyncio
async def test_the_cultivar_and_crop_come_from_their_owners_and_the_cutoff_bounds_vegetation(
    monkeypatch,
):
    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    compose, composed = _calls(_CTX_OK)
    vegetation, veg_seen = _calls(_VEG_OK)
    monkeypatch.setattr(client, "compose_context_snapshot", compose)
    monkeypatch.setattr(client, "latest_vegetation_snapshot", vegetation)
    b = await client.irrigation_candidate_lineage(
        object(), "fld_1", SEASON, INPUTS, WX, ET0, "2026-07-09", 40
    )
    assert not b.blocked
    assert b.record_fields["cultivar_id"] == "yecora"
    assert b.record_fields["crop_id"] == mod.resolve_crop_id("wheat")
    payload = composed[0][0][0]
    assert veg_seen[0][1]["available_before"] == payload["decision_cutoff_time"]


@pytest.mark.asyncio
async def test_composer_violations_are_reported_not_hidden(monkeypatch):
    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    refused = HTTPException(
        status_code=422,
        detail={
            "reason": "point_in_time_policy",
            "violations": [{"code": "canonical_soil_profile_required"}],
        },
    )
    compose, _ = _calls(raises=refused)
    vegetation, _ = _calls(raises=HTTPException(status_code=404, detail="none"))
    monkeypatch.setattr(client, "compose_context_snapshot", compose)
    monkeypatch.setattr(client, "latest_vegetation_snapshot", vegetation)
    b = await client.irrigation_candidate_lineage(
        object(), "fld_1", SEASON, INPUTS, WX, ET0, "2026-07-09", 40
    )
    assert b.blocked
    assert b.detail["context_violations"] == [{"code": "canonical_soil_profile_required"}]
    assert b.detail["vegetation"] == "no snapshot available by the cutoff"


# ── 3b) the canonical soil profile must reach context.soil intact ────────────────
def _canonical_profile(*, available_at="2026-07-09T06:00:00+00:00", gate_passed=True):
    from shared.contracts.soil.profile import canonical_soil_profile_hash

    body = {
        "contract_version": "soil-profile.v1",
        "profile_id": "soilprof_1",
        "tenant_id": "t-1",
        "field_id": "fld_1",
        "zone_id": None,
        "effective_at": "2026-07-01T00:00:00+00:00",
        "data_available_at": available_at,
        "status": "field_guided",
        "evidence_level": "lab_verified",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": 30,
                "properties": {
                    "texture_class": {
                        "value": "loam",
                        "evidence_class": "measured",
                        "selected_source": "soil_lab_test",
                        "confidence": 0.9,
                    }
                },
            }
        ],
        "completeness_score": 0.8,
        "quality_gate": {"passed": gate_passed, "executable": gate_passed, "reasons": []},
        "selection_policy_version": "soil-selection.v1",
    }
    body["profile_hash"] = canonical_soil_profile_hash(body)
    return body


def _decision_service_validate(payload, monkeypatch):
    """decision-service's own point-in-time policy, in production mode (soil profile required)."""
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.syspath_prepend(str(_REPO / "services" / "decision-service"))
    for name in [
        m for m in sys.modules if m == "agronomic_context" or m.startswith("agronomic_context.")
    ]:
        monkeypatch.delitem(sys.modules, name)
    from agronomic_context.contracts import ContextComposeIn
    from agronomic_context.point_in_time import validate_composition

    return [v["code"] for v in validate_composition(ContextComposeIn(**payload))]


async def _lineage_with_soil(monkeypatch, raw_profile):
    import api.canonical_soil_state as soil_state

    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")

    async def _soil(**_kw):
        return raw_profile

    monkeypatch.setattr(soil_state, "resolve_canonical_soil_state", _soil)
    compose, composed = _calls(_CTX_OK)
    vegetation, _ = _calls(_VEG_OK)
    monkeypatch.setattr(client, "compose_context_snapshot", compose)
    monkeypatch.setattr(client, "latest_vegetation_snapshot", vegetation)
    b = await client.irrigation_candidate_lineage(
        object(), "fld_1", SEASON, INPUTS, WX, ET0, "2026-07-09", 40
    )
    return b, composed[0][0][0]


@pytest.mark.asyncio
async def test_a_valid_canonical_profile_reaches_context_soil_and_passes_the_production_check(
    monkeypatch,
):
    profile = _canonical_profile()
    # the strict platform client adds normalisation keys the contract forbids
    raw = {**profile, "schema_version": "soil-profile.v1", "quality_status": "verified"}
    b, payload = await _lineage_with_soil(monkeypatch, raw)
    assert payload["context"]["soil"] == profile, "the canonical snapshot must travel verbatim"
    assert "soil_profile" not in b.detail
    assert _decision_service_validate(payload, monkeypatch) == []


@pytest.mark.asyncio
async def test_without_a_profile_production_names_the_soil_gap(monkeypatch):
    b, payload = await _lineage_with_soil(monkeypatch, None)
    assert b.detail["soil_profile"] == "no canonical soil profile for the field"
    assert _decision_service_validate(payload, monkeypatch) == ["canonical_soil_profile_required"]


@pytest.mark.asyncio
async def test_a_profile_whose_gate_failed_is_carried_and_refused_by_name(monkeypatch):
    b, payload = await _lineage_with_soil(monkeypatch, _canonical_profile(gate_passed=False))
    assert payload["context"]["soil"]["quality_gate"]["passed"] is False
    assert _decision_service_validate(payload, monkeypatch) == ["soil_profile_quality_gate_failed"]


@pytest.mark.asyncio
async def test_a_profile_published_after_the_cutoff_is_not_attached(monkeypatch):
    b, payload = await _lineage_with_soil(
        monkeypatch, _canonical_profile(available_at="2099-01-01T00:00:00+00:00")
    )
    assert b.detail["soil_profile"] == "soil profile became available after the decision cutoff"
    assert payload["context"]["soil"].get("profile_id") is None


def test_a_new_profile_never_reuses_the_idempotency_key_of_an_older_one():
    first = irrigation_candidate_compose_payload(
        tenant_id="t-1",
        field_id="fld_1",
        season_id="season_2026",
        cutoff=CUTOFF,
        features=_features(),
        inputs=INPUTS,
        ledger_date="2026-07-09",
        soil_profile=_canonical_profile(),
    )
    second_profile = {**_canonical_profile(), "completeness_score": 0.9}
    from shared.contracts.soil.profile import canonical_soil_profile_hash

    second_profile["profile_hash"] = canonical_soil_profile_hash(second_profile)
    second = irrigation_candidate_compose_payload(
        tenant_id="t-1",
        field_id="fld_1",
        season_id="season_2026",
        cutoff=CUTOFF,
        features=_features(),
        inputs=INPUTS,
        ledger_date="2026-07-09",
        soil_profile=second_profile,
    )
    assert first["idempotency_key"] != second["idempotency_key"]
    assert first["idempotency_key"] != _payload()["idempotency_key"]


# ── 4) the route ─────────────────────────────────────────────────────────────────
_endpoint_path = Path(__file__).with_name("test_field_irrigation_recommendation_endpoint.py")
_spec = importlib.util.spec_from_file_location("_ac1_endpoint_harness", _endpoint_path)
_endpoint = importlib.util.module_from_spec(_spec)
sys.modules["_ac1_endpoint_harness"] = _endpoint
_spec.loader.exec_module(_endpoint)


async def _snap(_lat, _lon):
    return {
        "t_min_c": 17.0,
        "t_max_c": 33.0,
        "wind_2m_ms": 2.0,
        "solar_rad_mj_m2": 22.0,
        "rh_mean_pct": 50.0,
        "rain_recent_mm": 0.0,
        "forecast_rain_mm": 3.0,
        "day_of_year": 191,
        "valid_time": "2026-07-10",
        "source": "weather-engine-forecast",
    }


def _route(monkeypatch, submit):
    _endpoint._patch(
        monkeypatch, _endpoint._FakeConn(depletion_mm=60.0), engine=_endpoint._pm_et0_product()
    )
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
    monkeypatch.setattr(mod, "_submit_candidate_to_decision", submit)
    return mod.FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)


_PERSISTED = {
    "decision_id": "dec_1",
    "authoritative": True,
    "persisted": True,
    "stage": "candidate",
}


@pytest.mark.asyncio
async def test_enforced_without_the_composer_the_route_blocks_by_name_and_submits_nothing(
    monkeypatch,
):
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    submit, submitted = _calls(_PERSISTED)
    out = await mod.field_irrigation_recommendation(
        "fld_1", _route(monkeypatch, submit), user=object()
    )
    assert out["approval_state"] == "blocked_agronomic_context_incomplete"
    assert submitted == [] and out["decision_id"] is None
    assert out["agronomic_context"]["status"] == "blocked"
    assert any("agronomic_context_incomplete" in lim for lim in out["limitations"])


@pytest.mark.asyncio
async def test_not_enforced_and_composer_off_the_route_behaves_as_before(monkeypatch):
    monkeypatch.delenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", raising=False)
    monkeypatch.delenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    submit, submitted = _calls(_PERSISTED)
    out = await mod.field_irrigation_recommendation(
        "fld_1", _route(monkeypatch, submit), user=object()
    )
    assert out["approval_state"] == "pending_approval"
    payload = submitted[0][0][0]
    assert not {"agronomic_context_snapshot_id", "vegetation_snapshot_id"} & set(payload)
    assert out["agronomic_context"]["status"] == "unbound"


@pytest.mark.asyncio
async def test_the_route_sends_the_bound_lineage_with_the_candidate(monkeypatch):
    async def _lineage(*_a, **_kw):
        return _bind()

    monkeypatch.setattr(mod, "irrigation_candidate_lineage", _lineage)
    submit, submitted = _calls(_PERSISTED)
    out = await mod.field_irrigation_recommendation(
        "fld_1", _route(monkeypatch, submit), user=object()
    )
    assert out["approval_state"] == "pending_approval"
    payload = submitted[0][0][0]
    for k in REQUIRED_LINEAGE_FIELDS:
        assert payload[k], k
    # the candidate itself is unchanged by the move into the policy module
    assert payload["decision_value"]["status"] == "pending_approval"
    assert payload["decision_value"]["approval_required"] is True


@pytest.mark.asyncio
async def test_decision_services_ac1_refusal_is_a_named_block_not_a_server_error(monkeypatch):
    async def _lineage(*_a, **_kw):
        return _bind(context=None, vegetation=None, required=False)

    monkeypatch.setattr(mod, "irrigation_candidate_lineage", _lineage)
    refusal = HTTPException(
        status_code=422, detail={"code": "agronomic_context_required", "missing": ["cultivar_id"]}
    )
    submit, _ = _calls(raises=refusal)
    out = await mod.field_irrigation_recommendation(
        "fld_1", _route(monkeypatch, submit), user=object()
    )
    assert out["approval_state"] == "blocked_agronomic_context_incomplete"
    assert out["decision_id"] is None
    assert any("cultivar_id" in lim for lim in out["limitations"])


# ── 4) defensive branches (codecov/patch on #1373: 10 lines of this PR uncovered) ─
def _history_from(ledger_date):
    payload = irrigation_candidate_compose_payload(
        tenant_id="t-1",
        field_id="fld_1",
        season_id="season_2026",
        cutoff=CUTOFF,
        features=_features(),
        inputs=INPUTS,
        ledger_date=ledger_date,
    )
    return payload["historical"]["history_from"]


def test_a_naive_ledger_datetime_is_read_as_utc_not_refused():
    assert _history_from(datetime(2026, 7, 9, 0, 0)) == "2026-07-09T00:00:00+00:00"


def test_an_unparsable_ledger_date_falls_back_to_one_day_before_the_cutoff():
    assert _history_from("not-a-date") == "2026-07-09T06:00:00+00:00"


def test_a_ledger_date_after_the_cutoff_never_opens_the_history_window_after_it():
    """history_from > cutoff would describe a window that ends before it starts."""
    assert _history_from("2026-07-11") == "2026-07-09T06:00:00+00:00"


def test_a_profile_the_contract_rejects_is_reported_with_its_issues_and_not_attached():
    from api.agronomic_context_composer import canonical_soil_profile_for_context

    broken = {k: v for k, v in _canonical_profile().items() if k != "layers"}
    profile, issues = canonical_soil_profile_for_context(broken, cutoff=CUTOFF)
    assert profile is None
    assert issues, "a rejected profile must say why, never pass silently"


def test_a_profile_with_a_naive_availability_time_is_refused_by_the_contract():
    """No silent "assume UTC": the strict contract refuses it, and the reason travels."""
    from api.agronomic_context_composer import canonical_soil_profile_for_context

    naive = _canonical_profile(available_at="2026-07-09T06:00:00")
    profile, issues = canonical_soil_profile_for_context(naive, cutoff=CUTOFF)
    assert profile is None
    assert issues, "a naive availability time must be refused with a reason"


def test_a_422_that_is_not_the_ac1_refusal_is_not_mapped_to_the_named_block():
    b = _bind()
    assert b.refusal(422, {"code": "something_else"}) is None
    assert b.refusal(500, {"code": "agronomic_context_required"}) is None
    assert b.refusal(422, "agronomic_context_required") is None
    state, _ = b.refusal(422, {"code": "agronomic_context_required", "missing": ["crop_id"]})
    assert state == "blocked_agronomic_context_incomplete"


def test_a_crop_without_a_crop_card_is_reported_and_never_filled():
    b = _bind(crop_id=None)
    assert "crop_id" in b.missing and "crop_id" not in b.record_fields
    assert b.detail["crop_id"] == "crop not resolved to a crop card"


@pytest.mark.asyncio
async def test_the_vegetation_read_asks_decision_service_for_the_point_in_time_snapshot(
    monkeypatch,
):
    get, seen = _calls({"snapshot_id": "veg_1"})
    monkeypatch.setattr(client, "decision_get_json", get)
    out = await client.latest_vegetation_snapshot(
        tenant_id="t-1",
        field_id="fld_1",
        season_id="season_2026",
        available_before="2026-07-10T06:00:00+00:00",
    )
    assert out == {"snapshot_id": "veg_1"}
    (args, kwargs) = seen[0]
    assert args == ("/v1/evidence/vegetation-snapshots/latest",)
    assert kwargs["params"] == {
        "field_id": "fld_1",
        "available_before": "2026-07-10T06:00:00+00:00",
        "season_id": "season_2026",
    }
    # Without a season the read is not scoped to an invented one.
    await client.latest_vegetation_snapshot(
        tenant_id="t-1", field_id="fld_1", season_id=None, available_before="x"
    )
    assert "season_id" not in seen[1][1]["params"]


@pytest.mark.asyncio
async def test_without_an_active_season_nothing_is_composed_and_the_gap_is_named(monkeypatch):
    monkeypatch.setenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "1")
    monkeypatch.setenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "1")
    compose, composed = _calls(_CTX_OK)
    vegetation, veg_seen = _calls(_VEG_OK)
    monkeypatch.setattr(client, "compose_context_snapshot", compose)
    monkeypatch.setattr(client, "latest_vegetation_snapshot", vegetation)
    b = await client.irrigation_candidate_lineage(
        object(), "fld_1", {"cultivar": "yecora"}, INPUTS, WX, ET0, "2026-07-09", 40
    )
    assert composed == [] and veg_seen == []
    assert b.detail["season_id"] == "no active season for the field"
    assert b.blocked and "season_id" in b.missing
