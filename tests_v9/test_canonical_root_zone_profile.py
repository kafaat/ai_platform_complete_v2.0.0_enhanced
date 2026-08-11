from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.unit


def _hv(value, origin="measured", confidence=0.95):
    return {"value": value, "unit": "m3/m3", "origin": origin, "confidence": confidence}


def _soil(*, origin="measured", include_infiltration=True, depth_to=100):
    return {
        "profile_id": "shp-1",
        "tenant_id": "tenant-1",
        "field_id": "fld-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "executable": True,
        "source_soil_profile_hash": "soil-hash-1",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": depth_to,
                "field_capacity": _hv(0.30, origin),
                "wilting_point": _hv(0.12, origin),
                "coarse_fragments": {
                    "value": 10,
                    "unit": "%",
                    "origin": "measured",
                    "confidence": 0.9,
                },
                "infiltration": {
                    "value": 12,
                    "unit": "mm/h",
                    "origin": "measured",
                    "confidence": 0.9,
                }
                if include_infiltration
                else None,
                "ksat": {"value": 20, "unit": "mm/h", "origin": "measured", "confidence": 0.9},
            }
        ],
    }


def _policy():
    return {
        "policy_id": "11111111-1111-1111-1111-111111111111",
        "initial_depth_m": 0.2,
        "maximum_depth_m": 1.0,
        "effective_fraction": 0.8,
        "policy_version": "maize-roots.v1",
        "evidence_ids": ["evidence-1"],
    }


def test_build_profile_integrates_layers_to_current_root_depth():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=_policy(),
        soil_profile=_soil(),
    )
    # Root depth = 0.2 + (1.0-0.2)*0.5 = 0.6 m.
    assert out.root_depth_m == 0.6
    # AWC = (0.30-0.12)*(1-0.10)=0.162; TAW=1000*0.162*0.6=97.2 mm.
    assert out.taw_mm == pytest.approx(97.2)
    assert out.raw_mm == pytest.approx(48.6)
    assert out.root_zone_refill_cap_mm == pytest.approx(48.6)
    assert out.root_zone_refill_cap_mm == pytest.approx(out.raw_mm)
    assert out.evidence["root_zone_refill_cap_semantics"] == ("readily_available_water_refill_cap")
    assert out.operational_eligible is True
    assert out.quality_status == "verified"
    assert len(out.profile_digest) == 64


def test_profile_blocks_when_layers_do_not_cover_root_depth():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=1.0,
        raw_fraction=0.5,
        root_policy=_policy(),
        soil_profile=_soil(depth_to=50),
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "soil_profile_does_not_cover_root_depth"


def test_profile_degrades_pedotransfer_or_missing_infiltration():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=_policy(),
        soil_profile=_soil(origin="pedotransfer", include_infiltration=False),
    )
    assert out.operational_eligible is False
    assert out.quality_status == "degraded"
    assert "field infiltration measurement missing" in out.limitations
    assert "field capacity or wilting point includes pedotransfer evidence" in out.limitations


def test_profile_blocks_without_validated_root_policy():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    policy = _policy()
    policy["policy_version"] = None
    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=policy,
        soil_profile=_soil(),
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "validated_root_policy_and_phenology_required"


def test_profile_degrades_when_stale():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    soil = _soil()
    soil["generated_at"] = (datetime.now(UTC) - timedelta(days=800)).isoformat()
    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=_policy(),
        soil_profile=soil,
    )
    assert out.operational_eligible is False
    assert "soil hydraulic profile is stale" in out.limitations


def test_persist_uses_digest_idempotency():
    import asyncio

    from api.canonical_root_zone_profile import (
        build_canonical_root_zone_profile,
        persist_canonical_root_zone_profile,
    )

    out = build_canonical_root_zone_profile(
        tenant_id="11111111-1111-1111-1111-111111111111",
        field_id="fld-1",
        season_id="sea-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=_policy(),
        soil_profile=_soil(),
    )

    class Conn:
        def __init__(self):
            self.calls = []

        async def execute(self, sql, *args):
            self.calls.append((sql, args))

    conn = Conn()
    asyncio.run(persist_canonical_root_zone_profile(conn, out))
    assert len(conn.calls) == 1
    sql, args = conn.calls[0]
    assert "ON CONFLICT(tenant_id,field_id,season_id,profile_digest) DO NOTHING" in sql
    assert args[0].startswith("rzp_")
    assert args[-2] == out.profile_digest
    persisted_payload = __import__("json").loads(args[-1])
    assert persisted_payload["root_zone_refill_cap_mm"] == pytest.approx(48.6)
