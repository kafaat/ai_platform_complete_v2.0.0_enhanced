from datetime import UTC, datetime

import pytest
from api.canonical_root_zone_profile import build_canonical_root_zone_profile
from api.canonical_sprinkler_runoff_capability import (
    build_canonical_sprinkler_runoff_capability,
)

pytestmark = pytest.mark.unit


def _hv(value, *, unit="m3/m3"):
    return {"value": value, "unit": unit, "origin": "measured", "confidence": 0.95}


def _real_root_zone_payload():
    soil = {
        "profile_id": "shp-contract-1",
        "tenant_id": "tenant-1",
        "field_id": "field-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "executable": True,
        "source_soil_profile_hash": "soil-hash-contract-1",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": 100,
                "field_capacity": _hv(0.30),
                "wilting_point": _hv(0.12),
                "coarse_fragments": _hv(10.0, unit="%"),
                "infiltration": _hv(15.0, unit="mm/h"),
                "ksat": _hv(20.0, unit="mm/h"),
            }
        ],
    }
    policy = {
        "policy_id": "11111111-1111-1111-1111-111111111111",
        "initial_depth_m": 0.2,
        "maximum_depth_m": 1.0,
        "effective_fraction": 0.8,
        "policy_version": "maize-roots.v1",
        "evidence_ids": ["evidence-1"],
    }
    out = build_canonical_root_zone_profile(
        tenant_id="tenant-1",
        field_id="field-1",
        season_id="season-1",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=policy,
        soil_profile=soil,
    )
    assert not isinstance(out, dict)
    return out.to_dict()


def _machine():
    return {
        "status": "verified",
        "operational_eligible": True,
        "machine_id": "machine-1",
        "capability_digest": "a" * 64,
    }


def _package():
    return {
        "package_id": "package-1",
        "certification_status": "certified",
        "tested_peak_application_mm_h": 9.0,
        "test_quality": "certified",
        "test_digest": "c" * 64,
    }


def _terrain():
    return {
        "maximum_slope_percent": 2.0,
        "quality": "certified",
        "profile_digest": "d" * 64,
    }


def _weather():
    return {
        "wind_speed_m_s": 2.0,
        "quality": "measured",
        "snapshot_digest": "e" * 64,
    }


def test_real_root_zone_product_feeds_m26_without_adapter():
    root = _real_root_zone_payload()
    assert root["quality_status"] == "verified"
    assert root["root_zone_refill_cap_mm"] == pytest.approx(root["raw_mm"])

    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability=_machine(),
        package=_package(),
        root_zone_profile=root,
        terrain=_terrain(),
        weather=_weather(),
    )

    assert out.status == "verified"
    assert out.maximum_safe_depth_mm_event == pytest.approx(root["root_zone_refill_cap_mm"])
    assert (
        out.evidence["root_zone_refill_cap_source"]
        == "canonical_root_zone_profile.root_zone_refill_cap_mm"
    )


def test_m26_rejects_legacy_status_alias():
    root = _real_root_zone_payload()
    root["status"] = root.pop("quality_status")

    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability=_machine(),
        package=_package(),
        root_zone_profile=root,
        terrain=_terrain(),
        weather=_weather(),
    )

    assert out == {
        "status": "blocked",
        "reason": "verified_root_zone_profile_required",
    }


def test_m26_does_not_rederive_refill_cap_from_raw_mm():
    root = _real_root_zone_payload()
    root.pop("root_zone_refill_cap_mm")
    assert root["raw_mm"] > 0

    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability=_machine(),
        package=_package(),
        root_zone_profile=root,
        terrain=_terrain(),
        weather=_weather(),
    )

    assert out == {
        "status": "blocked",
        "reason": "complete_runoff_evidence_required",
    }


def test_m26_fails_closed_when_root_zone_provenance_digest_is_missing():
    """قدرةٌ «verified» ونَسَبُها `None` أسوأ من الحجب.

    الارتداد إلى `capability_digest` أُزيل في هذه الشريحة وبقي الحقل بلا فحص،
    فكان مُنتَجٌ بلا `profile_digest` يُعطي قدرةً **مُتحقَّقة** وأدلّتُها تحمل
    `None` — ومن يقرأ `verified` لا يعود ينظر في الأدلّة. أمسكه فحصٌ خارجيّ
    وأُثبِت بالتنفيذ قبل الإصلاح.
    """
    root = _real_root_zone_payload()
    root.pop("profile_digest")

    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability=_machine(),
        package=_package(),
        root_zone_profile=root,
        terrain=_terrain(),
        weather=_weather(),
    )

    assert out == {
        "status": "blocked",
        "reason": "complete_runoff_evidence_required",
    }


def test_a_verified_capability_always_carries_a_root_zone_digest():
    """البند الموجب: النجاح يحمل النَّسَب، لا مجرّد أنّ الفشل يُحجَب."""
    out = build_canonical_sprinkler_runoff_capability(
        tenant_id="tenant-1",
        project_id="project-1",
        machine_capability=_machine(),
        package=_package(),
        root_zone_profile=_real_root_zone_payload(),
        terrain=_terrain(),
        weather=_weather(),
    )

    assert out.status == "verified"
    assert out.evidence["root_zone_profile_digest"]
    assert len(out.evidence["root_zone_profile_digest"]) == 64
