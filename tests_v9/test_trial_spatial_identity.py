"""Field-trial evidence must stay bound to its immutable spatial layout."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import shape

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def spatial():
    spec = importlib.util.spec_from_file_location(
        "trial_spatial_identity_tests", ROOT / "shared/precision_agriculture/trial_spatial.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _field(longitude=44.0):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [longitude, 15.0],
                [longitude + 0.004, 15.0],
                [longitude + 0.004, 15.004],
                [longitude, 15.004],
                [longitude, 15.0],
            ]
        ],
    }


def _design(spatial, **changes):
    arguments = {
        "trial_id": "trial-123",
        "treatments": ["control", "N-low"],
        "n_blocks": 4,
        "field_geometry": _field(),
        "machine_heading_deg": 0,
        "implement_width_m": 20,
        "randomization_seed": "A",
        "headland_m": 2,
        "strip_gap_m": 0,
        "min_plot_area_m2": 500,
    }
    arguments.update(changes)
    return spatial.design_spatial_rcbd(**arguments)


def _outcomes(assignments):
    return {
        row["plot_id"]: {
            "layout_id": row["layout_id"],
            "outcome_refs": ["raster:field-A:harvest-2026"],
            "measurements": {"yield_t_ha": 5.0},
        }
        for row in assignments
    }


def test_identical_design_is_deterministic_balanced_and_inside_the_field(spatial):
    first = _design(spatial)
    repeated = _design(spatial, field_geometry=json.loads(json.dumps(_field())))
    assert first == repeated
    assert len(first) == 8
    assert len({row["plot_id"] for row in first}) == 8
    assert len({row["layout_id"] for row in first}) == 1
    field = shape(_field()).buffer(1e-12)
    for row in first:
        assert field.covers(shape(row["geometry"]))
        assert row["area_m2"] >= 500
    for block in range(1, 5):
        rows = [row for row in first if row["block_index"] == block]
        assert {row["treatment"] for row in rows} == {"control", "N-low"}
        assert {row["plot_slot"] for row in rows} == {1, 2}
        assert sum(row["role"] == "control" for row in rows) == 1
    bound = spatial.bind_plot_outcomes(first, _outcomes(first))
    assert all(row["layout_id"] == first[0]["layout_id"] for row in bound)


@pytest.mark.parametrize(
    "changes",
    [
        {"field_geometry": _field(45.0)},
        {"randomization_seed": "B"},
        {"machine_heading_deg": 12},
        {"implement_width_m": 21},
        {"headland_m": 3},
        {"strip_gap_m": 1},
        {"min_plot_area_m2": 501},
        {"treatments": ["N-low", "control"]},
        {"n_blocks": 5},
        {"trial_id": "trial-124"},
    ],
)
def test_changed_layout_cannot_accept_previous_plot_outcomes(spatial, changes):
    previous = _design(spatial)
    current = _design(spatial, **changes)
    assert current[0]["layout_id"] != previous[0]["layout_id"]
    assert {row["plot_id"] for row in current}.isdisjoint(row["plot_id"] for row in previous)
    with pytest.raises(ValueError, match="identity mismatch"):
        spatial.bind_plot_outcomes(current, _outcomes(previous))


def test_old_measurements_cannot_be_relabelled_with_current_plot_ids(spatial):
    previous = _design(spatial)
    current = _design(spatial, randomization_seed="B")
    old_outcomes = list(_outcomes(previous).values())
    relabelled = {row["plot_id"]: value for row, value in zip(current, old_outcomes, strict=True)}
    with pytest.raises(ValueError, match="layout identity mismatch"):
        spatial.bind_plot_outcomes(current, relabelled)


def test_direct_geometry_order_is_part_of_layout_identity(spatial):
    geometries = [row["geometry"] for row in _design(spatial)]
    arguments = {
        "trial_id": "trial-123",
        "treatments": ["control", "N-low"],
        "n_blocks": 4,
        "machine_heading_deg": 0,
        "randomization_seed": "A",
    }
    first = spatial.assign_rcbd_geometries(plot_geometries=geometries, **arguments)
    reordered = [geometries[1], geometries[0], *geometries[2:]]
    second = spatial.assign_rcbd_geometries(plot_geometries=reordered, **arguments)
    assert first[0]["layout_id"] != second[0]["layout_id"]
    with pytest.raises(ValueError, match="identity mismatch"):
        spatial.bind_plot_outcomes(second, _outcomes(first))


@pytest.mark.parametrize(
    "field,value",
    [
        ("geometry", _field(45)),
        ("treatment", "another-treatment"),
        ("role", "another-role"),
        ("machine_heading_deg", 45),
        ("block_index", 20),
        ("plot_slot", 20),
        ("area_m2", 1),
    ],
)
def test_editing_an_assignment_without_new_identity_is_rejected(spatial, field, value):
    rows = _design(spatial)
    outcomes = _outcomes(rows)
    changed = copy.deepcopy(rows)
    changed[0][field] = value
    with pytest.raises(ValueError, match="assignment|identity"):
        spatial.bind_plot_outcomes(changed, outcomes)


def test_legacy_or_mixed_layout_evidence_fails_closed(spatial):
    rows = _design(spatial)
    outcomes = _outcomes(rows)
    legacy_rows = [{k: v for k, v in row.items() if k != "layout_id"} for row in rows]
    with pytest.raises(ValueError, match="layout_id"):
        spatial.bind_plot_outcomes(legacy_rows, outcomes)
    legacy_outcomes = copy.deepcopy(outcomes)
    del legacy_outcomes[rows[0]["plot_id"]]["layout_id"]
    with pytest.raises(ValueError, match="layout identity mismatch"):
        spatial.bind_plot_outcomes(rows, legacy_outcomes)
    mixed = copy.deepcopy(rows)
    mixed[0]["layout_id"] = "another-layout"
    with pytest.raises(ValueError, match="layout_id"):
        spatial.bind_plot_outcomes(mixed, outcomes)


def test_binding_still_rejects_partial_and_nonfinite_measurements(spatial):
    rows = _design(spatial)
    partial = _outcomes(rows)
    del partial[rows[0]["plot_id"]]
    with pytest.raises(ValueError, match="identity mismatch"):
        spatial.bind_plot_outcomes(rows, partial)
    extra = _outcomes(rows)
    extra["unrelated-plot"] = dict(extra[rows[0]["plot_id"]])
    with pytest.raises(ValueError, match="identity mismatch"):
        spatial.bind_plot_outcomes(rows, extra)
    nonfinite = _outcomes(rows)
    nonfinite[rows[0]["plot_id"]]["measurements"]["yield_t_ha"] = float("nan")
    with pytest.raises(ValueError, match="invalid outcome measurements"):
        spatial.bind_plot_outcomes(rows, nonfinite)


@pytest.mark.parametrize(
    "treatments",
    [
        ["control", "control"],
        ["control", " control "],
        ["Control", "control"],
        ["control", "   "],
    ],
)
def test_direct_assignment_rejects_duplicate_or_empty_normalized_treatments(spatial, treatments):
    with pytest.raises(ValueError, match="unique non-empty"):
        spatial.assign_rcbd_geometries(
            trial_id="trial-123",
            treatments=treatments,
            n_blocks=4,
            plot_geometries=[_field(44 + i * 0.01) for i in range(8)],
            machine_heading_deg=0,
            randomization_seed="A",
        )
    with pytest.raises(ValueError, match="unique non-empty"):
        _design(spatial, treatments=treatments)


def test_geometry_encoding_and_label_whitespace_do_not_change_identity(spatial):
    first = _design(spatial, treatments=["CONTROL", "N low"])
    # Reverse winding and change dict/numeric encodings without moving the field.
    field = _field(44)
    alternate = {"coordinates": [list(reversed(field["coordinates"][0]))], "type": "Polygon"}
    repeated = _design(
        spatial,
        field_geometry=alternate,
        treatments=["  CONTROL  ", "N   low"],
        implement_width_m=20.0,
        machine_heading_deg=360.0,
    )
    assert first == repeated
    assert sum(row["role"] == "control" for row in first) == 4


@pytest.mark.parametrize("trial_id", [None, "", "   ", "unbound-trial"])
def test_assignment_requires_a_real_trial_identity(spatial, trial_id):
    with pytest.raises(ValueError, match="trial_id"):
        _design(spatial, trial_id=trial_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"machine_heading_deg": float("nan")},
        {"implement_width_m": float("inf")},
        {"headland_m": float("nan")},
        {"strip_gap_m": float("nan")},
        {"min_plot_area_m2": float("nan")},
    ],
)
def test_nonfinite_layout_parameters_are_rejected(spatial, changes):
    with pytest.raises(ValueError):
        _design(spatial, **changes)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), 181])
def test_nonfinite_or_out_of_bounds_geometry_is_rejected(spatial, coordinate):
    invalid = _field()
    invalid["coordinates"][0][1][0] = coordinate
    with pytest.raises(ValueError):
        _design(spatial, field_geometry=invalid)
