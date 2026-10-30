"""Physical experimental units must not be duplicated by new labels/IDs."""

import importlib.util
import sys
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def spatial():
    source = Path(__file__).resolve().parents[1] / "shared/precision_agriculture/trial_spatial.py"
    spec = importlib.util.spec_from_file_location("spatial_review_guards", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plots():
    return [mapping(box(44 + i * 0.002, 15, 44 + i * 0.002 + 0.001, 15.001)) for i in range(8)]


def _assign(spatial, plots=None, treatments=None, **kwargs):
    return spatial.assign_rcbd_geometries(
        trial_id="physical-units",
        treatments=treatments or ["control", "A"],
        n_blocks=4,
        plot_geometries=plots or _plots(),
        machine_heading_deg=0,
        randomization_seed="review",
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["equal", "contained", "cross_block_overlap"])
def test_positive_area_collisions_rejected(spatial, kind):
    plots = _plots()
    if kind == "equal":
        plots = [plots[0]] * 8
    elif kind == "contained":
        plots[1] = mapping(box(44.0001, 15.0001, 44.0009, 15.0009))
    else:
        plots[7] = mapping(box(44.0005, 15, 44.0015, 15.001))
    with pytest.raises(ValueError, match="overlap|duplicate"):
        _assign(spatial, plots)


def test_touching_boundaries_and_corners_remain_valid(spatial):
    x = [44 + i * 0.001 for i in range(9)]
    plots = [mapping(box(x[i], 15, x[i + 1], 15.001)) for i in range(8)]
    rows = _assign(spatial, plots)
    assert len(rows) == len({row["plot_id"] for row in rows}) == 8
    assert rows == _assign(spatial, plots)


@pytest.mark.parametrize("names", [["control", "شاهد"], [" CONTROL ", " شاهد "]])
def test_arabic_and_english_control_are_one_identity(spatial, names):
    with pytest.raises(ValueError, match="unique non-empty"):
        _assign(spatial, treatments=names)
    with pytest.raises(ValueError, match="unique non-empty"):
        spatial.generate_rcbd_plot_geometries(
            field_geometry=mapping(box(44, 15, 44.01, 15.01)),
            treatments=names,
            n_blocks=4,
            machine_heading_deg=0,
            implement_width_m=10,
        )


def test_custom_control_aliases_share_identity(spatial):
    with pytest.raises(ValueError, match="unique non-empty"):
        _assign(spatial, treatments=["baseline", "CONTROL"], control_names=("baseline",))
    rows = _assign(spatial, treatments=[" Baseline ", "A"], control_names=("baseline",))
    assert sum(row["role"] == "control" for row in rows) == 4
    assert {row["treatment"] for row in rows} == {"Baseline", "A"}


def test_local_projection_rejects_nonlocal_and_polar_layouts(spatial):
    for plots in (
        [mapping(box(44 + i, 15, 44 + i + 0.001, 15.001)) for i in range(8)],
        [mapping(box(44 + i * 0.002, 89, 44 + i * 0.002 + 0.001, 89.001)) for i in range(8)],
    ):
        with pytest.raises(ValueError, match="local|polar"):
            _assign(spatial, plots)


def test_normal_disjoint_plots_keep_measured_binding(spatial):
    rows = _assign(spatial)
    outcomes = {
        r["plot_id"]: {
            "layout_id": r["layout_id"],
            "measurements": {"yield": 5},
            "outcome_refs": ["measured:plot"],
        }
        for r in rows
    }
    bound = spatial.bind_plot_outcomes(rows, outcomes)
    assert len(bound) == 8
    assert all(row["measurements"]["yield"] == 5 for row in bound)


def test_binding_rechecks_physical_units_even_with_consistent_content_ids(spatial):
    rows = _assign(spatial)
    rows[1]["geometry"] = rows[0]["geometry"]
    # Reproduce a legacy/supplied assignment whose digest is internally valid.
    # A digest alone must not certify that its physical experimental unit is new.
    rows[1]["plot_id"] = spatial._stable_plot_id(rows[1]["layout_id"], rows[1])
    outcomes = {
        row["plot_id"]: {
            "layout_id": row["layout_id"],
            "outcome_refs": ["measured:plot"],
            "measurements": {"yield": 5},
        }
        for row in rows
    }
    with pytest.raises(ValueError, match="overlap|duplicate"):
        spatial.bind_plot_outcomes(rows, outcomes)


@pytest.mark.parametrize(
    "measurements",
    [
        {"yield": True},
        {"yield": False},
        {"yield": 10**400},
        {"yield": None},
        {"yield": []},
        [5],
        "5",
    ],
    ids=["true", "false", "overflow", "null", "list-value", "list-map", "string-map"],
)
def test_invalid_measurements_fail_as_controlled_input_error(spatial, measurements):
    rows = _assign(spatial)
    outcomes = {
        row["plot_id"]: {
            "layout_id": row["layout_id"],
            "outcome_refs": ["measured:plot"],
            "measurements": {"yield": 5},
        }
        for row in rows
    }
    outcomes[rows[0]["plot_id"]]["measurements"] = measurements
    with pytest.raises(ValueError, match="invalid outcome measurements"):
        spatial.bind_plot_outcomes(rows, outcomes)


@pytest.mark.parametrize("value", [0, 5.5, "5.5"])
def test_finite_measurements_preserve_numeric_string_compatibility(spatial, value):
    rows = _assign(spatial)
    outcomes = {
        row["plot_id"]: {
            "layout_id": row["layout_id"],
            "outcome_refs": ["measured:plot"],
            "measurements": {"yield": value},
        }
        for row in rows
    }
    bound = spatial.bind_plot_outcomes(rows, outcomes)
    assert len(bound) == len(rows)
    assert all(row["measurements"] == {"yield": float(value)} for row in bound)
