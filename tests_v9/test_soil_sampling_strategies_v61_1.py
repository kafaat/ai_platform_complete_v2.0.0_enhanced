"""تحقّق V61.1 — استراتيجيّات أخذ عيّنات التربة (grid/zone/hybrid) + إرشاد العدد.

- ``recommended_samples_for_area`` (≈عيّنة/2 هكتار، أرضيّة 3، سقف 20) — إرشاديّ.
- ``grid_points`` نقاط داخليّة منتظمة داخل bbox.
- استراتيجيّة ``grid``: خطّة شبكيّة من bbox بلا حاجة لمناطق.
- استراتيجيّة ``hybrid``: طبقات المناطق + تكميل شبكيّ نحو هدف المساحة.
- الافتراضيّ ``zone`` = سلوك v61 دون تغيير.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import soil_sampling_planner as SP  # noqa: E402
from services.ai_agronomist import soil_sampling_strategies as S  # noqa: E402

_BBOX = [44.0, 16.0, 44.2, 16.2]


def test_recommended_samples_guidance_clamped():
    assert S.recommended_samples_for_area(1.0) == 3  # floor
    assert S.recommended_samples_for_area(10.0) == 5  # ceil(10*0.5)
    assert S.recommended_samples_for_area(1000.0) == 20  # cap
    assert S.recommended_samples_for_area(0) == 3  # invalid ⇒ floor


def test_grid_points_are_interior_and_counted():
    pts = S.grid_points(_BBOX, 9)
    assert len(pts) == 9
    for lon, lat in pts:
        assert 44.0 < lon < 44.2 and 16.0 < lat < 16.2  # strictly interior (cell centres)


# ── grid strategy through the tool contract ─────────────────────────────────
def test_grid_strategy_plans_from_bbox_without_zones():
    out = SP.plan_soil_sampling(
        {"bbox": _BBOX, "sampling_strategy": "grid", "samples_per_zone": 6}, field_id="f"
    )
    assert out["method"] == "regular_grid_sampling"
    assert out["sampling_strategy"] == "grid"
    assert out["soil_sampling_plan"]["total_samples"] == 6
    assert all(p["point"]["type"] == "Point" for p in out["sample_points"])
    assert out["requires_user_confirmation"] is True


def test_grid_strategy_fails_closed_without_geometry():
    out = SP.plan_soil_sampling({"sampling_strategy": "grid"}, field_id="f")
    assert out["error"] == "missing_productivity_zones_or_boundary"
    assert out["sample_points"] == []


# ── hybrid strategy tops up zone strata ─────────────────────────────────────
def test_hybrid_adds_grid_infill_beyond_zone_samples():
    zones = [
        {
            "zone_id": "z1",
            "productivity_class": "high",
            "bbox": [44.0, 16.0, 44.1, 16.2],
            "area_ha": 30.0,
        },
        {
            "zone_id": "z2",
            "productivity_class": "low",
            "bbox": [44.1, 16.0, 44.2, 16.2],
            "area_ha": 30.0,
        },
    ]
    zone_only = SP.plan_soil_sampling({"zones": zones}, field_id="f")
    hybrid = SP.plan_soil_sampling({"zones": zones, "sampling_strategy": "hybrid"}, field_id="f")
    assert hybrid["method"] == "hybrid_zone_grid_sampling"
    assert hybrid["sampling_strategy"] == "hybrid"
    # 60 ha ⇒ target 20 samples; zone-only gives far fewer ⇒ infill present.
    assert (
        hybrid["soil_sampling_plan"]["total_samples"]
        > zone_only["soil_sampling_plan"]["total_samples"]
    )
    assert any(p["zone_id"] == "grid-infill" for p in hybrid["sample_points"])


def test_default_zone_strategy_unchanged():
    zones = [
        {"zone_id": "z1", "productivity_class": "high", "bbox": [44.0, 16.0, 44.1, 16.1]},
        {"zone_id": "z2", "productivity_class": "low", "bbox": [44.1, 16.0, 44.2, 16.1]},
    ]
    out = SP.plan_soil_sampling({"zones": zones}, field_id="f")
    assert out["method"] == "productivity_zone_stratified_sampling"
    assert out["sampling_strategy"] == "zone"
    assert not any(p["zone_id"] == "grid-infill" for p in out["sample_points"])
