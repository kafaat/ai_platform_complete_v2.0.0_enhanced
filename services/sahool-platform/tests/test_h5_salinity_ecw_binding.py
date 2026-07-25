"""H5 (PR3): bind ECw→water_source_id + enforce maximum_allowed_ec fail-closed.

Two layers:
  1. Pure `evaluate_water_salinity_gate` — the single source of the EC rule, reused
     by `build_canonical_well_capability` and by the served MPC recommendation.
  2. Static wiring guard — asserts the served daily MPC recommendation route resolves
     ECw from the bound water source (SoR, not client) and fails closed on the limit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from api.canonical_well_capability import (
    WATER_QUALITY_REQUIRED,
    WATER_QUALITY_STALE,
    WATER_SALINITY_LIMIT_EXCEEDED,
    build_canonical_well_capability,
    evaluate_water_salinity_gate,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
ROUTE_SRC = (
    Path(__file__).resolve().parents[1] / "api" / "routers" / "irrigation_mpc.py"
).read_text(encoding="utf-8")


# ─────────────────────────── pure gate: fail-closed rule ───────────────────────────


def test_gate_clear_when_ec_below_limit():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 2.4, "sampled_at": (NOW - timedelta(days=10)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "clear"
    assert v["blocking_reasons"] == []
    assert v["water_ec_ds_m"] == 2.4
    assert v["maximum_allowed_ec_ds_m"] == 3.0


def test_gate_blocks_when_ec_exceeds_limit():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 4.1, "sampled_at": (NOW - timedelta(days=5)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "blocked"
    assert WATER_SALINITY_LIMIT_EXCEEDED in v["blocking_reasons"]


def test_gate_blocks_when_limit_set_but_no_sample():
    # A configured limit with no measured sample fails closed — the limit is unverifiable.
    v = evaluate_water_salinity_gate(maximum_allowed_ec_ds_m=3.0, water_quality=None, now=NOW)
    assert v["status"] == "blocked"
    assert WATER_QUALITY_REQUIRED in v["blocking_reasons"]


def test_gate_blocks_on_stale_sample():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 1.0, "sampled_at": (NOW - timedelta(days=800)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_STALE in v["blocking_reasons"]


def test_gate_clear_when_no_limit_configured():
    # No configured maximum ⇒ no limit to enforce ⇒ clear even without a sample.
    v = evaluate_water_salinity_gate(maximum_allowed_ec_ds_m=None, water_quality=None, now=NOW)
    assert v["status"] == "clear"
    assert v["blocking_reasons"] == []


def test_gate_boundary_equal_limit_is_clear():
    # ECw exactly at the limit is allowed (strict > blocks), matching the well-capability rule.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 3.0, "sampled_at": (NOW - timedelta(days=1)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "clear"


# ───────────── dedup regression: build_canonical_well_capability still enforces ─────────────


def _well_inputs(ec: float) -> dict:
    return {
        "tenant_id": "t1",
        "project_id": "p1",
        "water_source": {
            "id": "source-1",
            "commissioned_max_flow_lps": 50.0,
            "maximum_allowed_ec_ds_m": 3.0,
        },
        "well": {"id": "well-1", "water_source_id": "source-1", "sustainable_flow_lps": 44.0},
        "pumping_test": {
            "id": "test-1",
            "status": "certified",
            "tested_at": (NOW - timedelta(days=30)).isoformat(),
            "tested_flow_lps": 48.0,
            "recommended_sustainable_flow_lps": 42.0,
            "recovery_rate_m_h": 5.0,
        },
        "latest_measurement": {
            "id": "m1",
            "static_level_m": 10.0,
            "dynamic_level_m": 18.0,
            "measured_at": (NOW - timedelta(hours=2)).isoformat(),
        },
        "allocation": {"daily_allocation_m3": 1000.0, "daily_used_m3": 100.0},
        "water_quality": {"ec_ds_m": ec, "sampled_at": (NOW - timedelta(days=10)).isoformat()},
        "now": NOW,
    }


def test_build_capability_still_blocks_on_salinity_after_dedup():
    cap = build_canonical_well_capability(**_well_inputs(ec=4.5))
    data = cap.to_dict()
    assert data["status"] == "blocked"
    assert WATER_SALINITY_LIMIT_EXCEEDED in data["blocking_reasons"]


def test_build_capability_verified_when_salinity_clear():
    cap = build_canonical_well_capability(**_well_inputs(ec=2.0))
    data = cap.to_dict()
    assert WATER_SALINITY_LIMIT_EXCEEDED not in data["blocking_reasons"]


# ─────────────────── static wiring guard: served MPC recommendation ───────────────────


def test_recommendation_route_binds_ecw_to_source_and_enforces_fail_closed():
    # Request carries a water_source_id binding (server-authoritative EC resolution).
    assert "water_source_id: str | None" in ROUTE_SRC
    # Server resolves ECw + the limit from SoR (not from the client).
    assert "irrigation_water_sources" in ROUTE_SRC
    assert "maximum_allowed_ec_ds_m" in ROUTE_SRC
    assert "irrigation_water_quality_samples" in ROUTE_SRC
    # The served route runs the canonical fail-closed gate and blocks with expert review.
    assert "evaluate_water_salinity_gate(" in ROUTE_SRC
    assert "water_salinity_gate_blocked" in ROUTE_SRC
    assert "water_source_unresolved" in ROUTE_SRC
    assert "requires_expert_review" in ROUTE_SRC


def test_recommendation_route_does_not_trust_client_ecw():
    # No client-supplied ECw field on the operational recommendation request — the binding
    # is server-authoritative via water_source_id, resolved from SoR.
    assert "water_ec: float" not in ROUTE_SRC
