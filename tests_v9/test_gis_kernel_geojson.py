"""اختبار وحدويّ نقيّ لدوالّ GeoJSON في نواة GIS (api/gis_kernel.py).

يثبت تحقّق/استخراج/تطبيع GeoJSON بلا قاعدة ولا shapely: نوع الهندسة، الاستخراج من
Feature/FeatureCollection، التطبيع (إسقاط properties)، فرض الخطّ للشفرة والمساحة،
وتحقّق المسافة. نواة بلا خدمات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.gis_kernel import (  # noqa: E402
    GeoJSONError,
    extract_geometry,
    is_geometry_type,
    normalize_geometry,
    require_lineal_blade,
    require_polygonal,
    validate_distance_m,
    validate_geometry,
)

_POLY = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.1], [44.0, 15.0]]],
}
_LINE = {"type": "LineString", "coordinates": [[44.0, 15.0], [44.2, 15.2]]}


# ─── is_geometry_type ────────────────────────────────────────────────────


def test_is_geometry_type_known_and_unknown():
    assert is_geometry_type("Polygon")
    assert is_geometry_type("GeometryCollection")
    assert not is_geometry_type("Feature")
    assert not is_geometry_type("polygon")  # حسّاس لحالة الأحرف
    assert not is_geometry_type(None)


# ─── validate_geometry ───────────────────────────────────────────────────


def test_validate_geometry_accepts_polygon():
    assert validate_geometry(_POLY) is _POLY


def test_validate_geometry_rejects_non_dict():
    with pytest.raises(GeoJSONError):
        validate_geometry([1, 2, 3])


def test_validate_geometry_rejects_unknown_type():
    with pytest.raises(GeoJSONError):
        validate_geometry({"type": "Blob", "coordinates": []})


def test_validate_geometry_requires_coordinates_list():
    with pytest.raises(GeoJSONError):
        validate_geometry({"type": "Polygon"})


def test_validate_geometry_collection_recurses():
    gc = {"type": "GeometryCollection", "geometries": [_POLY, _LINE]}
    assert validate_geometry(gc) is gc
    with pytest.raises(GeoJSONError):
        validate_geometry({"type": "GeometryCollection", "geometries": [{"type": "Nope"}]})
    with pytest.raises(GeoJSONError):
        validate_geometry({"type": "GeometryCollection"})  # لا geometries


# ─── extract_geometry ────────────────────────────────────────────────────


def test_extract_from_bare_geometry():
    assert extract_geometry(_POLY)["type"] == "Polygon"


def test_extract_from_feature():
    feat = {"type": "Feature", "properties": {"name": "x"}, "geometry": _POLY}
    assert extract_geometry(feat)["coordinates"] == _POLY["coordinates"]


def test_extract_feature_null_geometry_rejected():
    with pytest.raises(GeoJSONError):
        extract_geometry({"type": "Feature", "geometry": None})


def test_extract_from_single_feature_collection():
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": _POLY}]}
    assert extract_geometry(fc)["type"] == "Polygon"


def test_extract_multi_feature_collection_rejected():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": _POLY},
            {"type": "Feature", "geometry": _LINE},
        ],
    }
    with pytest.raises(GeoJSONError):
        extract_geometry(fc)


def test_extract_empty_feature_collection_rejected():
    with pytest.raises(GeoJSONError):
        extract_geometry({"type": "FeatureCollection", "features": []})


def test_extract_unknown_wrapper_rejected():
    with pytest.raises(GeoJSONError):
        extract_geometry({"type": "Topology"})


# ─── normalize_geometry ──────────────────────────────────────────────────


def test_normalize_strips_non_geometry_keys():
    feat = {"type": "Feature", "properties": {"name": "x"}, "bbox": [0, 0, 1, 1], "geometry": _POLY}
    out = normalize_geometry(feat)
    assert set(out.keys()) == {"type", "coordinates"}
    assert out["coordinates"] == _POLY["coordinates"]


def test_normalize_geometry_collection_recurses_and_strips():
    gc = {"type": "GeometryCollection", "geometries": [_POLY]}
    out = normalize_geometry(gc)
    assert out["type"] == "GeometryCollection"
    assert set(out["geometries"][0].keys()) == {"type", "coordinates"}


# ─── require_lineal_blade ────────────────────────────────────────────────


def test_require_lineal_blade_accepts_line():
    assert require_lineal_blade(_LINE)["type"] == "LineString"


def test_require_lineal_blade_rejects_polygon():
    with pytest.raises(GeoJSONError):
        require_lineal_blade(_POLY)


# ─── require_polygonal ───────────────────────────────────────────────────


def test_require_polygonal_accepts_polygon():
    assert require_polygonal(_POLY)["type"] == "Polygon"


def test_require_polygonal_rejects_line():
    with pytest.raises(GeoJSONError):
        require_polygonal(_LINE)


# ─── validate_distance_m ─────────────────────────────────────────────────


def test_validate_distance_accepts_int_float_negative():
    assert validate_distance_m(10) == 10.0
    assert validate_distance_m(-2.5) == -2.5


def test_validate_distance_rejects_non_number_and_bool():
    for bad in ("10", None, True, [1]):
        with pytest.raises(GeoJSONError):
            validate_distance_m(bad)


def test_validate_distance_rejects_nan_inf():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(GeoJSONError):
            validate_distance_m(bad)
