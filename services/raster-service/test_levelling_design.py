"""Levelling cut/fill design: explicit CRS/datum/nodata/holes/units, RTK evidence, no authority."""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("rasterio")

import levelling_design as ld  # noqa: E402

pytestmark = pytest.mark.unit


def _req(**over):
    # 10x10 cells of 2 m (20 m x 20 m = 400 m2), UTM 38N, tilted 1 m west->east.
    z = [[100.0 + 0.1 * c for c in range(10)] for _ in range(10)]
    r = {
        "crs_epsg": 32638,
        "vertical_datum": "EGM2008",
        "elevation_m": z,
        "nodata": -9999.0,
        "cell_size_m": [2.0, 2.0],
        "origin_xy": [500000.0, 1700020.0],
        "polygon": {
            "exterior": [
                [500000, 1700000],
                [500020, 1700000],
                [500020, 1700020],
                [500000, 1700020],
                [500000, 1700000],
            ]
        },
        "design": {"mode": "flat", "shrink_factor": 1.0},
    }
    r.update(over)
    return r


def _refused(r, code):
    assert r["computed"] is False, r
    assert r["source"] == code, r
    assert r["execution_authorized"] is False


def test_flat_design_balances_and_conserves_volume():
    r = ld.compute_levelling_design(_req())
    assert r["computed"] is True, r
    assert r["area_m2"] == pytest.approx(400.0)
    q = r["quantities"]
    assert q["cut_m3"] == pytest.approx(q["fill_m3"], rel=1e-6)
    # mean |dz| = 0.25 m over 400 m2 => 100 m3 moved, half cut and half fill.
    assert q["cut_m3"] == pytest.approx(50.0, rel=1e-3)
    assert r["design"]["target_elevation_mean_m"] == pytest.approx(100.45, abs=0.01)
    assert r["units"] == {"horizontal": "m", "vertical": "m", "volume": "m3"}
    assert r["vertical_datum"] == "EGM2008"
    assert r["crs_epsg"] == 32638


def test_no_execution_authority_and_status():
    r = ld.compute_levelling_design(_req())
    assert r["execution_authorized"] is False
    assert r["status"] == "design_proposal_not_for_construction"


def test_shrink_factor_requires_more_cut_than_fill():
    r = ld.compute_levelling_design(_req(design={"mode": "flat", "shrink_factor": 1.2}))
    q = r["quantities"]
    assert q["cut_m3"] == pytest.approx(q["fill_m3"] * 1.2, rel=1e-4)


def test_plane_design_with_slope():
    r = ld.compute_levelling_design(
        _req(design={"mode": "plane", "slope_x_pct": 5.0, "slope_y_pct": 0.0, "shrink_factor": 1.0})
    )
    assert r["computed"] is True
    # terrain already 5% (0.1 m per 2 m): tiny earthwork vs the flat case
    flat = ld.compute_levelling_design(_req())
    assert r["quantities"]["cut_m3"] < 0.1 * flat["quantities"]["cut_m3"]


def test_hole_excluded_from_area_and_volume():
    ext = [
        [500000, 1700000],
        [500020, 1700000],
        [500020, 1700020],
        [500000, 1700020],
        [500000, 1700000],
    ]
    hole = [
        [500008, 1700008],
        [500012, 1700008],
        [500012, 1700012],
        [500008, 1700012],
        [500008, 1700008],
    ]
    r = ld.compute_levelling_design(_req(polygon={"exterior": ext, "holes": [hole]}))
    assert r["computed"] is True
    assert r["area_m2"] == pytest.approx(400.0 - 16.0)


def test_nodata_cells_excluded_and_reported():
    z = _req()["elevation_m"]
    z[0][0] = -9999.0
    z[1][1] = float("nan")
    r = ld.compute_levelling_design(_req(elevation_m=z))
    assert r["computed"] is True
    assert r["coverage"]["nodata_cells"] == 2
    assert r["area_m2"] == pytest.approx(392.0)


def test_low_valid_coverage_refused():
    z = [[-9999.0] * 10 for _ in range(10)]
    z[0][0] = 100.0
    _refused(ld.compute_levelling_design(_req(elevation_m=z)), "insufficient-valid-coverage")


@pytest.mark.parametrize(
    "over,code",
    [
        ({"crs_epsg": 4326}, "crs-not-projected-metric"),
        ({"crs_epsg": None}, "crs-missing"),
        ({"vertical_datum": None}, "vertical-datum-missing"),
        ({"vertical_datum": ""}, "vertical-datum-missing"),
        ({"cell_size_m": [0.0, 2.0]}, "cell-size-invalid"),
        ({"cell_size_m": [2.0]}, "cell-size-invalid"),
        ({"polygon": None}, "polygon-invalid"),
        ({"polygon": {"exterior": [[0, 0], [1, 1]]}}, "polygon-invalid"),
        ({"design": {"mode": "flat", "shrink_factor": 0.5}}, "design-invalid"),
        ({"design": {"mode": "bowl"}}, "design-invalid"),
        ({"design": {"mode": "plane", "slope_x_pct": 40}}, "design-invalid"),
        ({"elevation_m": []}, "elevation-grid-invalid"),
        ({"elevation_m": [[1.0, 2.0], [1.0]]}, "elevation-grid-invalid"),
        ({"nodata": None, "elevation_m": [[float("inf")] * 10] * 10}, "elevation-grid-invalid"),
    ],
)
def test_explicit_inputs_refused(over, code):
    _refused(ld.compute_levelling_design(_req(**over)), code)


def test_grid_size_bound():
    big = [[1.0] * 1100 for _ in range(1000)]
    _refused(
        ld.compute_levelling_design(
            _req(
                elevation_m=big,
                polygon={
                    "exterior": [
                        [500000, 1700000],
                        [502200, 1700000],
                        [502200, 1702000],
                        [500000, 1700000],
                    ]
                },
            )
        ),
        "grid-too-large",
    )


def test_polygon_outside_grid_refused():
    far = [[600000, 1800000], [600010, 1800000], [600010, 1800010], [600000, 1800000]]
    _refused(ld.compute_levelling_design(_req(polygon={"exterior": far})), "polygon-outside-grid")


def test_topsoil_volumes():
    r = ld.compute_levelling_design(_req(topsoil={"strip_depth_m": 0.2}))
    t = r["topsoil"]
    assert t["strip_m3"] == pytest.approx(80.0)
    assert t["respread_m3"] == pytest.approx(80.0)
    assert t["stockpile_required"] is True
    assert "subsoil_exposed_area_m2" in t
    # topsoil is NOT counted in earthwork cut/fill
    assert r["quantities"]["cut_m3"] == pytest.approx(
        ld.compute_levelling_design(_req())["quantities"]["cut_m3"]
    )


def test_topsoil_negative_or_absurd_refused():
    _refused(ld.compute_levelling_design(_req(topsoil={"strip_depth_m": -0.1})), "topsoil-invalid")
    _refused(ld.compute_levelling_design(_req(topsoil={"strip_depth_m": 5})), "topsoil-invalid")


def _rtk(n=6, dz=0.0, fix="fixed", datum="EGM2008"):
    return [
        {
            "x": 500002.0 + 3 * i,
            "y": 1700010.0,
            "z": 100.0 + 0.1 * (1 + (3 * i) // 2) + dz,
            "fix": fix,
            "h_acc_m": 0.02,
            "v_acc_m": 0.03,
            "vertical_datum": datum,
        }
        for i in range(n)
    ]


def test_without_rtk_is_indicative_and_reports_no_evidence():
    r = ld.compute_levelling_design(_req())
    assert r["evidence"]["rtk"]["points"] == 0
    assert r["evidence"]["grade"] == "dem_only_indicative"


def test_rtk_agreeing_points_give_survey_checked():
    r = ld.compute_levelling_design(_req(rtk_points=_rtk()))
    ev = r["evidence"]
    assert ev["rtk"]["fixed_points"] == 6
    assert ev["rtk"]["rmse_m"] == pytest.approx(0.0, abs=0.06)
    assert ev["grade"] == "rtk_checked"


def test_rtk_disagreeing_points_downgrade():
    r = ld.compute_levelling_design(_req(rtk_points=_rtk(dz=0.5)))
    assert r["evidence"]["grade"] == "rtk_disagrees_with_dem"
    assert r["evidence"]["rtk"]["rmse_m"] == pytest.approx(0.5, abs=0.06)


def test_rtk_float_points_not_counted_as_fixed():
    r = ld.compute_levelling_design(_req(rtk_points=_rtk(fix="float")))
    assert r["evidence"]["rtk"]["fixed_points"] == 0
    assert r["evidence"]["grade"] == "dem_only_indicative"


def test_rtk_datum_mismatch_refused():
    _refused(
        ld.compute_levelling_design(_req(rtk_points=_rtk(datum="WGS84-ellipsoid"))),
        "rtk-datum-mismatch",
    )


def test_rtk_points_outside_field_not_used():
    pts = _rtk()
    pts[0]["x"] = 900000.0
    r = ld.compute_levelling_design(_req(rtk_points=pts))
    assert r["evidence"]["rtk"]["outside_field"] == 1
    assert r["evidence"]["rtk"]["fixed_points"] == 5


def test_costs_quantities_only_without_prices():
    r = ld.compute_levelling_design(_req())
    c = r["cost"]
    assert c["priced"] is False
    assert c["total"] is None
    assert c["quantities"]["earthwork_m3"] == pytest.approx(
        r["quantities"]["cut_m3"] + r["quantities"]["fill_m3"]
    )


def test_costs_priced_only_with_supplied_prices():
    r = ld.compute_levelling_design(
        _req(
            topsoil={"strip_depth_m": 0.2},
            unit_prices={
                "currency": "YER",
                "earthwork_per_m3": 10.0,
                "topsoil_handling_per_m3": 20.0,
            },
        )
    )
    c = r["cost"]
    assert c["priced"] is True and c["currency"] == "YER"
    q = r["quantities"]
    assert c["total"] == pytest.approx(10.0 * (q["cut_m3"] + q["fill_m3"]) + 20.0 * (80.0 + 80.0))


def test_negative_price_refused():
    _refused(
        ld.compute_levelling_design(_req(unit_prices={"currency": "YER", "earthwork_per_m3": -1})),
        "unit-prices-invalid",
    )
