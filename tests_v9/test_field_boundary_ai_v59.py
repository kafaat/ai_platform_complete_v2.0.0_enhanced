"""V59 Field Boundary AI guards."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_executor as EX  # noqa: E402
from services.ai_agronomist.field_boundary_ai import (  # noqa: E402
    area_ha_for_bbox,
    propose_boundaries,
)
from shared.ai import tool_schema as SCH  # noqa: E402


def test_detect_field_boundaries_proposes_geojson_without_persistence():
    out = propose_boundaries(
        {
            "bbox": [44.18, 16.16, 44.19, 16.17],
            "source": "truecolor",
            "date": "2026-06-25",
            "crop_hint": "wheat",
        },
        field_id="field-1",
        imagery_context={"total_dates": 8},
    )

    assert out["requires_user_confirmation"] is True
    assert out["persistence"] == "proposal_only_until_user_confirms"
    proposal = out["proposed_boundaries"][0]
    assert proposal["geometry"]["type"] == "Polygon"
    assert proposal["confidence"] >= 0.7
    assert proposal["area_ha"] == area_ha_for_bbox([44.18, 16.16, 44.19, 16.17])


def test_invalid_bbox_fails_closed_as_empty_proposal():
    out = propose_boundaries({"bbox": [44, 16, 43, 17]})
    assert out["error"] == "invalid_bbox"
    assert out["proposed_boundaries"] == []
    assert out["requires_user_confirmation"] is True


def test_boundary_tools_are_governed_by_read_then_approval_write():
    detect = EX.plan_tool_call(
        "detect_field_boundaries", {"bbox": [44, 16, 45, 17]}, ["can_read_historical_imagery"]
    )
    assert detect["outcome"] == "allowed"
    assert detect["risk"] == "low"

    save = EX.plan_tool_call(
        "save_detected_boundary",
        {"field_id": "f", "proposal_id": "p"},
        ["can_manage_field_boundaries"],
    )
    assert save["outcome"] == "pending_approval"
    assert save["risk"] == "high"
    assert save["requires_approval"] is True


def test_provider_schema_exposes_bbox_array_for_detection_tool():
    defs = SCH.tool_definitions(["can_read_historical_imagery"])
    detect = next(d for d in defs if d["name"] == "detect_field_boundaries")
    bbox = detect["parameters"]["properties"]["bbox"]
    assert bbox["type"] == "array"
    assert bbox["minItems"] == 4 and bbox["maxItems"] == 4
