"""V60 Productivity Zones guards."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_executor as EX  # noqa: E402
from services.ai_agronomist.productivity_zones import propose_productivity_zones  # noqa: E402
from shared.ai import tool_schema as SCH  # noqa: E402


def test_generate_productivity_zones_proposes_three_confirmable_zones():
    out = propose_productivity_zones(
        {
            "bbox": [44.18, 16.16, 44.21, 16.18],
            "zone_count": 3,
            "basis": "multi_index",
        },
        field_id="field-1",
        evidence_context={
            "imagery_timeline": {
                "total_dates": 18,
                "per_indicator": {"ndvi": {"total": 18}, "ndmi": {"total": 12}},
            }
        },
    )

    assert out["requires_user_confirmation"] is True
    assert out["persistence"] == "proposal_only_until_user_confirms"
    assert out["next_step"] == "v61_soil_sampling_planner"
    zones = out["productivity_zones"]
    assert [z["productivity_class"] for z in zones] == ["high", "medium", "low"]
    assert all(z["geometry"]["type"] == "Polygon" for z in zones)
    assert zones[0]["confidence"] >= 0.7


def test_productivity_zones_fail_closed_without_boundary_or_bbox():
    out = propose_productivity_zones({"zone_count": 3})
    assert out["error"] == "missing_or_invalid_boundary"
    assert out["productivity_zones"] == []
    assert out["requires_user_confirmation"] is True


def test_productivity_zone_tools_are_proposal_then_approval_write():
    generate = EX.plan_tool_call(
        "generate_productivity_zones",
        {"bbox": [44, 16, 45, 17], "zone_count": 3},
        ["can_read_historical_imagery"],
    )
    assert generate["outcome"] == "allowed"
    assert generate["risk"] == "low"

    save = EX.plan_tool_call(
        "save_productivity_zones",
        {"field_id": "f", "proposal_id": "pz"},
        ["can_manage_productivity_zones"],
    )
    assert save["outcome"] == "pending_approval"
    assert save["risk"] == "high"
    assert save["requires_approval"] is True


def test_provider_schema_exposes_productivity_zone_inputs():
    defs = SCH.tool_definitions(["can_read_historical_imagery"])
    generate = next(d for d in defs if d["name"] == "generate_productivity_zones")
    props = generate["parameters"]["properties"]
    assert props["bbox"]["type"] == "array"
    assert props["boundary"]["type"] == "object"
    assert props["zone_count"]["type"] == "integer"
