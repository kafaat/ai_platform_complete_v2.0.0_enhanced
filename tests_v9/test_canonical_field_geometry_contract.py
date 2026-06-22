"""اختبارات عقد CanonicalFieldGeometry الموحَّد (shared/domain/field_geometry.py).

تضمن أنّ الشكل الكنسيّ (geometry Polygon + area_ha + bbox{min_lng..} + revision +
source) يبقى متطابقاً مع ما يُنتجه حارس الـGIS في الخلفيّة، دون أيّ تغيير سلوك.
"""

from __future__ import annotations

import pytest

from shared.domain.field_geometry import (
    CanonicalFieldGeometry,
    is_canonical_field_geometry,
    validate_canonical_field_geometry,
)

pytestmark = pytest.mark.unit


_VALID = {
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.2, 15.0], [44.2, 15.2], [44.0, 15.2], [44.0, 15.0]]],
    },
    "area_ha": 12.3456,
    "bbox": {"min_lng": 44.0, "min_lat": 15.0, "max_lng": 44.2, "max_lat": 15.2},
    "revision": 3,
    "source": "gis-guard-v1",
}


def test_valid_shape_passes() -> None:
    assert is_canonical_field_geometry(_VALID) is True
    validate_canonical_field_geometry(_VALID)  # لا يرمي


def test_roundtrip_to_dict() -> None:
    geom = CanonicalFieldGeometry.from_dict(_VALID)
    out = geom.to_dict()
    assert out["geometry"]["type"] == "Polygon"
    assert out["area_ha"] == pytest.approx(12.3456)
    assert out["bbox"] == _VALID["bbox"]
    assert out["revision"] == 3
    assert out["source"] == "gis-guard-v1"


def test_revision_optional_none() -> None:
    data = {**_VALID, "revision": None}
    geom = CanonicalFieldGeometry.from_dict(data)
    assert geom.revision is None
    assert is_canonical_field_geometry(data) is True


def test_default_source_is_unknown() -> None:
    geom = CanonicalFieldGeometry(
        geometry=_VALID["geometry"],
        area_ha=1.0,
        bbox=_VALID["bbox"],
    )
    assert geom.source == "unknown"
    assert geom.revision is None


def test_bbox_must_use_lng_keys_not_lon() -> None:
    # العقد يلتزم بمفاتيح min_lng/max_lng مثل حارس الـGIS — lon مرفوض.
    bad = {
        **_VALID,
        "bbox": {"min_lon": 44.0, "min_lat": 15.0, "max_lon": 44.2, "max_lat": 15.2},
    }
    assert is_canonical_field_geometry(bad) is False
    with pytest.raises(ValueError):
        validate_canonical_field_geometry(bad)


def test_non_polygon_geometry_rejected() -> None:
    bad = {**_VALID, "geometry": {"type": "Point", "coordinates": [44.0, 15.0]}}
    assert is_canonical_field_geometry(bad) is False


def test_bad_types_rejected() -> None:
    assert is_canonical_field_geometry(None) is False
    assert is_canonical_field_geometry({**_VALID, "area_ha": "12"}) is False
    assert is_canonical_field_geometry({**_VALID, "source": 7}) is False
    assert is_canonical_field_geometry({**_VALID, "revision": "3"}) is False
    # bool ليس عدداً صحيحاً مقبولاً لا في revision ولا area_ha.
    assert is_canonical_field_geometry({**_VALID, "revision": True}) is False
    assert is_canonical_field_geometry({**_VALID, "area_ha": True}) is False


def test_post_init_validates() -> None:
    with pytest.raises(ValueError):
        CanonicalFieldGeometry(
            geometry={"type": "Point", "coordinates": [0, 0]},
            area_ha=1.0,
            bbox=_VALID["bbox"],
        )
