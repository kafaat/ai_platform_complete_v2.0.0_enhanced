"""G10: سلامة توصيات الزراعة الدقيقة (المرحلة ٦) — لا ``or``-افتراضات تُغيّر المعنى.

• ``rate_multiplier: 0`` (منطقة استثناء) كان يصير 1.0 لجرعات البذور/الريّ.
• إنتاجيّة غائبة كانت تصير 3 ط/هـ (أو ``score`` بلا وحدة) في خريطة الربحيّة.
• التقسيم كان يجمع خواصّ بوحدات مختلفة بلا تطبيع (الارتفاع بالأمتار يطغى على NDVI).
"""

from __future__ import annotations

import math

import pytest

from shared.precision_agriculture.phase6_intelligence import (
    compute_profitability_map,
    compute_yield_stability,
    generate_management_zones,
    generate_prescription_map,
)

pytestmark = pytest.mark.unit


# ── الوصفة: صفر صريح يبقى صفراً ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "zone",
    [
        {"id": "x", "zone": 2, "label": "medium", "rate_multiplier": 0},
        {"id": "x", "zone": 2, "label": "medium", "properties": {"rate_multiplier": 0}},
        {"id": "x", "zone": 1, "label": "stress", "rate_multiplier": 0.0},
    ],
)
@pytest.mark.parametrize("kind", ["seed", "irrigation"])
def test_exclusion_zone_gets_zero_dose(zone, kind):
    rx = generate_prescription_map([zone], crop="wheat", prescription_type=kind)
    props = rx["features"][0]["properties"]
    assert props["rate"] == 0.0
    assert props["properties"]["rate_multiplier"] == 0.0


def test_non_nutrient_rates_are_exact():
    rx = generate_prescription_map(
        [
            {"id": "a", "zone": 1, "label": "stress", "rate_multiplier": 1.0},
            {"id": "b", "zone": 2, "label": "medium"},
            {"id": "c", "zone": 3, "label": "high_potential", "rate_multiplier": 0.5},
        ],
        crop="wheat",
        prescription_type="irrigation",
    )
    rates = [f["properties"]["rate"] for f in rx["features"]]
    # 45 mm × 1.08 (stress) · 45 × 1.0 (absent ⇒ neutral) · 45 × 0.5.
    assert rates == [48.6, 45.0, 22.5]
    seed = generate_prescription_map(
        [{"id": "s", "zone": 1, "label": "stress", "rate_multiplier": 0.5}],
        crop="wheat",
        prescription_type="seed",
    )
    assert seed["features"][0]["properties"]["rate"] == round(160 * 0.5 * 0.92, 2) == 73.6


@pytest.mark.parametrize("multiplier", [-1, -0.01, float("nan"), float("inf"), True, "1"])
@pytest.mark.parametrize("kind", ["seed", "irrigation"])
def test_invalid_non_nutrient_multiplier_is_rejected(multiplier, kind):
    with pytest.raises(ValueError, match="rate_multiplier must be finite and nonnegative"):
        generate_prescription_map(
            [{"rate_multiplier": multiplier}], crop="wheat", prescription_type=kind
        )


# ── الربحيّة: إنتاجيّة غائبة لا تُخترَع ───────────────────────────────────────

_COSTS = {"water": 100, "fertilizer": 250}  # 350 / ha


def test_missing_yield_is_marked_not_invented():
    out = compute_profitability_map(
        [{"id": "z1", "zone": 1}, {"id": "z2", "zone": 2, "score": 0.8}],
        market_price_per_t=200,
        variable_costs_per_ha=_COSTS,
    )
    assert out["zones_missing_yield"] == ["z1", "z2"]
    assert out["yield_unit"] == "t/ha"
    for feature in out["features"]:
        assert feature["data_status"] == "missing_yield"
        assert feature["label"] == "insufficient_data"
        assert feature["gross_revenue_per_ha"] is None
        assert feature["profit_per_ha"] is None
        assert feature["roi"] is None
        assert feature["total_cost_per_ha"] == 350.0


def test_explicit_zero_yield_is_a_loss_not_three_tonnes():
    out = compute_profitability_map(
        [{"id": "z", "zone": 1, "expected_yield_t_ha": 0}],
        market_price_per_t=200,
        variable_costs_per_ha=_COSTS,
    )
    feature = out["features"][0]
    assert feature["data_status"] == "ok"
    assert feature["gross_revenue_per_ha"] == 0.0
    assert feature["profit_per_ha"] == -350.0
    assert feature["roi"] == -1.0
    assert feature["label"] == "loss_area"
    assert out["zones_missing_yield"] == []


def test_mean_yield_in_kg_per_ha_is_normalized_to_t_per_ha():
    out = compute_profitability_map(
        [
            {"id": "kg", "zone": 1, "mean_yield": 4500, "yield_unit": "kg/ha"},
            {"id": "t", "zone": 2, "mean_yield": 4.5},
        ],
        market_price_per_t=200,
        variable_costs_per_ha=_COSTS,
    )
    revenues = [f["gross_revenue_per_ha"] for f in out["features"]]
    assert revenues == [900.0, 900.0]
    assert [f["profit_per_ha"] for f in out["features"]] == [550.0, 550.0]


def test_exclusion_zone_cost_uses_explicit_zero_multiplier():
    out = compute_profitability_map(
        [{"id": "z", "zone": 1, "expected_yield_t_ha": 2.0, "rate_multiplier": 0}],
        market_price_per_t=200,
        variable_costs_per_ha=_COSTS,
    )
    # 0 ⇒ floored at 0.2 × 350 = 70 (was the full 350 via ``or 1.0``).
    assert out["features"][0]["total_cost_per_ha"] == 70.0
    assert out["features"][0]["profit_per_ha"] == 330.0


@pytest.mark.parametrize(
    "zone,match",
    [
        ({"mean_yield": 4.0, "yield_unit": "bu/ac"}, "unsupported yield_unit"),
        ({"expected_yield_t_ha": 4.0, "yield_unit": "kg/ha"}, "expected_yield_t_ha is in t/ha"),
        ({"expected_yield_t_ha": -1.0}, "finite and nonnegative"),
        ({"mean_yield": float("nan")}, "finite and nonnegative"),
    ],
)
def test_unit_mismatch_or_invalid_yield_is_rejected(zone, match):
    with pytest.raises(ValueError, match=match):
        compute_profitability_map([zone], market_price_per_t=200, variable_costs_per_ha=_COSTS)


# ── التقسيم: تطبيع الخواصّ قبل الوزن ────────────────────────────────────────

_ZONING = [
    {"id": "a", "ndvi": 0.2, "elevation": 2010.0},
    {"id": "b", "ndvi": 0.5, "elevation": 2000.0},
    {"id": "c", "ndvi": 0.8, "elevation": 1990.0},
]


def test_zoning_normalizes_features_so_elevation_metres_do_not_dominate():
    out = generate_management_zones(_ZONING, n_zones=3)
    by_id = {f["id"]: f for f in out["features"]}
    # Raw weighted sum ranked "a" (highest elevation, lowest NDVI) as high potential.
    assert by_id["c"]["label"] == "high_potential"
    assert by_id["a"]["label"] == "stress"
    # z(ndvi)=±0.3/sqrt(0.06)=±1.224745; score=(1.8·z_n + 0.2·z_e)/(1.8+0.2).
    z = 0.3 / math.sqrt(0.06)
    assert by_id["a"]["score"] == round((-1.8 * z + 0.2 * z) / 2.0, 4) == -0.9798
    assert by_id["b"]["score"] == 0.0
    assert by_id["c"]["score"] == 0.9798
    assert out["normalization"] == "per_feature_zscore"


def test_zoning_is_invariant_to_a_feature_unit_change():
    metres = generate_management_zones(_ZONING, n_zones=3)
    km = generate_management_zones(
        [{**s, "elevation": s["elevation"] / 1000.0} for s in _ZONING], n_zones=3
    )
    assert [f["score"] for f in metres["features"]] == [f["score"] for f in km["features"]]
    assert [f["zone"] for f in metres["features"]] == [f["zone"] for f in km["features"]]


def test_zoning_rejects_mixed_units_within_one_feature():
    samples = [
        {"id": "a", "ndvi": 0.2, "elevation": 2010.0, "elevation_unit": "m"},
        {"id": "b", "ndvi": 0.5, "elevation": 6562.0, "elevation_unit": "ft"},
    ]
    with pytest.raises(ValueError, match="feature 'elevation' mixes units"):
        generate_management_zones(samples, n_zones=2)


def test_zoning_reports_consistent_units_and_unscored_samples():
    samples = [
        {"id": "a", "ndvi": 0.2, "elevation": 2010.0, "elevation_unit": "m"},
        {"id": "b", "ndvi": 0.5, "elevation_unit": "m"},
        {"id": "c", "ndvi": 0.8, "elevation": 1990.0, "elevation_unit": "m"},
        {"id": "empty"},
    ]
    out = generate_management_zones(samples, n_zones=2)
    assert out["feature_units"] == {"ndvi": None, "elevation": "m"}
    assert out["unscored_sample_ids"] == ["empty"]
    assert [f["id"] for f in out["features"]] == ["a", "b", "c"]
    assert sum(z["sample_count"] for z in out["zones"]) == 3
    # "b" lacks elevation: scored on NDVI alone (z=0), not as elevation=0 m.
    assert {f["id"]: f["score"] for f in out["features"]}["b"] == 0.0


# ── ثبات الإنتاجيّة: الغياب لا يدخل صفراً ────────────────────────────────────


def test_yield_stability_skips_missing_yield_rows():
    out = compute_yield_stability(
        [
            {"zone": "A", "yield": 5.0},
            {"zone": "A", "yield": None},
            {"zone": "A"},
            {"zone": "A", "yield": 5.2},
        ]
    )
    cls = out["classes"][0]
    assert cls["mean_yield"] == 5.1
    assert cls["years"] == 2
    assert cls["label"] == "stable_high"
    assert out["skipped_missing_yield"] == 2


async def test_profitability_route_maps_unit_errors_to_422():
    import sys
    from pathlib import Path

    platform = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    try:
        from api.routers import gis_cloud_native as route
        from fastapi import HTTPException
    except Exception:  # noqa: BLE001 — platform deps absent in the minimal unit env
        pytest.skip("platform/api deps unavailable")
    req = route.ProfitabilityMapRequest(
        zones=[{"mean_yield": 4.0, "yield_unit": "bu/ac"}], market_price_per_t=200
    )
    with pytest.raises(HTTPException) as exc:
        await route.phase6_profitability_map(req, user=None)
    assert exc.value.status_code == 422
    assert "unsupported yield_unit 'bu/ac'" in exc.value.detail
