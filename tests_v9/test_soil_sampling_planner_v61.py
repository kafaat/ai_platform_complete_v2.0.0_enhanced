"""V61 Soil Sampling Planner guards."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_executor as EX  # noqa: E402
from services.ai_agronomist.soil_sampling_planner import plan_soil_sampling  # noqa: E402
from shared.ai import tool_schema as SCH  # noqa: E402


def _zones():
    return [
        {
            "zone_id": "pz-1",
            "productivity_class": "high",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.18, 16.16], [44.19, 16.16], [44.19, 16.18], [44.18, 16.18], [44.18, 16.16]]
                ],
            },
        },
        {
            "zone_id": "pz-2",
            "productivity_class": "medium",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.19, 16.16], [44.20, 16.16], [44.20, 16.18], [44.19, 16.18], [44.19, 16.16]]
                ],
            },
        },
        {
            "zone_id": "pz-3",
            "productivity_class": "low",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.20, 16.16], [44.21, 16.16], [44.21, 16.18], [44.20, 16.18], [44.20, 16.16]]
                ],
            },
        },
    ]


def test_plan_soil_sampling_from_productivity_zones_is_confirmable():
    out = plan_soil_sampling(
        {"zones": _zones(), "samples_per_zone": 2, "lab_panel": "standard"},
        field_id="field-1",
        evidence_context={"imagery_timeline": {"total_dates": 18}},
    )

    assert out["requires_user_confirmation"] is True
    assert out["persistence"] == "proposal_only_until_user_confirms"
    assert out["next_step"] == "v62_vra_prescription_engine"
    assert out["soil_sampling_plan"]["total_samples"] == 7  # low zone gets one extra sample
    assert out["soil_sampling_plan"]["source_evidence_dates"] == 18
    assert all(p["point"]["type"] == "Point" for p in out["sample_points"])
    assert any(p["priority"] == "high" for p in out["sample_points"])


def test_plan_soil_sampling_fail_closed_without_zones_or_boundary():
    out = plan_soil_sampling({"samples_per_zone": 2})
    assert out["error"] == "missing_productivity_zones_or_boundary"
    assert out["sample_points"] == []
    assert out["requires_user_confirmation"] is True


def test_soil_sampling_tools_are_proposal_then_approval_write():
    plan = EX.plan_tool_call(
        "plan_soil_sampling",
        {"zones": _zones()},
        ["can_read_historical_imagery"],
    )
    assert plan["outcome"] == "allowed"
    assert plan["risk"] == "low"

    save = EX.plan_tool_call(
        "save_soil_sampling_plan",
        {"field_id": "f", "plan_id": "ssp"},
        ["can_manage_soil_sampling"],
    )
    assert save["outcome"] == "pending_approval"
    assert save["risk"] == "high"
    assert save["requires_approval"] is True


def test_provider_schema_exposes_soil_sampling_inputs():
    defs = SCH.tool_definitions(["can_read_historical_imagery"])
    plan = next(d for d in defs if d["name"] == "plan_soil_sampling")
    props = plan["parameters"]["properties"]
    assert props["zones"]["type"] == "array"
    assert props["bbox"]["type"] == "array"
    assert props["boundary"]["type"] == "object"
    assert props["samples_per_zone"]["type"] == "integer"


# ── polygon geometry, not its bounding box ──────────────────────────────────
# Right triangle with legs along the axes: its bbox is ~118 ha, the zone itself ~59 ha.
_TRIANGLE = {
    "type": "Polygon",
    "coordinates": [[[44.18, 16.16], [44.19, 16.16], [44.18, 16.17], [44.18, 16.16]]],
}


def _inside_triangle(lon: float, lat: float) -> bool:
    # Independent of the planner: below the hypotenuse lat = 16.17 - (lon - 44.18).
    return lon > 44.18 and lat > 16.16 and lat < 16.17 - (lon - 44.18)


def test_zone_area_uses_polygon_not_bbox():
    from services.ai_agronomist.field_boundary_ai import area_ha_for_bbox

    bbox_area = area_ha_for_bbox([44.18, 16.16, 44.19, 16.17])
    out = plan_soil_sampling(
        {"zones": [{"zone_id": "tri", "productivity_class": "low", "geometry": _TRIANGLE}]}
    )
    area = out["soil_sampling_plan"]["strata"][0]["area_ha"]
    assert abs(area - bbox_area / 2) < 0.5, (area, bbox_area)


def test_zone_sample_points_stay_inside_the_polygon():
    for samples in (1, 2, 3, 5, 8):
        out = plan_soil_sampling(
            {
                "zones": [
                    {
                        "zone_id": "tri",
                        "productivity_class": "high",
                        "geometry": _TRIANGLE,
                        "samples": samples,
                    }
                ]
            }
        )
        points = [p["point"]["coordinates"] for p in out["sample_points"]]
        assert len(points) == samples
        assert len({tuple(p) for p in points}) == samples
        outside = [p for p in points if not _inside_triangle(*p)]
        assert outside == [], (samples, outside)


def test_boundary_fallback_strata_follow_the_boundary_polygon():
    out = plan_soil_sampling({"boundary": _TRIANGLE, "samples_per_zone": 2})
    assert out["method"] == "geometry_seeded_sampling_fallback"
    points = [p["point"]["coordinates"] for p in out["sample_points"]]
    assert points
    assert [p for p in points if not _inside_triangle(*p)] == []
    total = sum(s["area_ha"] for s in out["soil_sampling_plan"]["strata"])
    assert 58.0 < total < 60.0, total
