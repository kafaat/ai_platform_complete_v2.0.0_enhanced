"""اختبارات نقيّة لبناء Shapefile من الوصفة (api.prescription_shapefile).

يتحقّق أنّ الأرشيف صالح ويحوي .shp/.shx/.dbf/.prj، وأنّ السجلّات تطابق المناطق، ويرفض
ما لا هندسة صالحة له (لا shapefile مُلفَّق). نقيّ — بلا خدمات/شبكة.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile

import pytest

pytestmark = pytest.mark.unit

# يتطلّب pyshp (تبعيّة تصدير اختياريّة) — يُتخطّى الاختبار إن غابت (مثل وظيفة Unit Tests التي
# لا تُثبّت api/requirements.txt)؛ يعمل محليّاً وفي Platform Unit Tests (حيث pyshp مُثبَّتة).
pytest.importorskip("shapefile")

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.prescription_shapefile import build_shapefile_zip  # noqa: E402

_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.1], [44.0, 15.0]]],
}
_ZONES = [
    {"geometry": _SQUARE, "rate": 450.5, "unit": "seeds/m2"},
    {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[44.2, 15.0], [44.3, 15.0], [44.3, 15.1], [44.2, 15.0]]],
        },
        "rate": 120.0,
        "unit": "kg/ha",
    },
]


def _names(zb: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(zb)) as zf:
        return set(zf.namelist())


def test_archive_has_all_shapefile_parts():
    zb = build_shapefile_zip("وصفة تجريبيّة", "seed", _ZONES)
    names = _names(zb)
    assert {"prescription.shp", "prescription.shx", "prescription.dbf", "prescription.prj"} <= names


def test_prj_is_wgs84():
    zb = build_shapefile_zip("rx", "seed", _ZONES)
    with zipfile.ZipFile(io.BytesIO(zb)) as zf:
        prj = zf.read("prescription.prj").decode("utf-8")
    assert "WGS 84" in prj


def test_records_match_zones():
    import shapefile  # pyshp

    zb = build_shapefile_zip("rx", "fertility", _ZONES)
    with zipfile.ZipFile(io.BytesIO(zb)) as zf, _extract(zf) as base:
        r = shapefile.Reader(base)
        assert r.numRecords == 2
        recs = r.records()
        # حقل rate الثاني = 120.0 (التحقّق من نقل المعدّل)
        assert float(recs[1]["rate"]) == pytest.approx(120.0)
        assert recs[0]["unit"] == "seeds/m2"


def test_multipolygon_supported():
    multi = {
        "type": "MultiPolygon",
        "coordinates": [
            _SQUARE["coordinates"],
            [[[45.0, 16.0], [45.1, 16.0], [45.1, 16.1], [45.0, 16.0]]],
        ],
    }
    zb = build_shapefile_zip("rx", "seed", [{"geometry": multi, "rate": 1, "unit": "u"}])
    assert "prescription.shp" in _names(zb)


@pytest.mark.parametrize(
    "zones",
    [
        [],
        [{"geometry": None, "rate": 1, "unit": "u"}],
        [{"geometry": {"type": "Point", "coordinates": [1, 2]}}],
    ],
)
def test_rejects_no_valid_geometry(zones):
    with pytest.raises(ValueError):
        build_shapefile_zip("rx", "seed", zones)


# ── مساعد: يفكّ الأرشيف لمجلّد مؤقّت ويعيد المسار الأساس (لقراءة pyshp) ──
import contextlib  # noqa: E402
import tempfile  # noqa: E402


@contextlib.contextmanager
def _extract(zf: zipfile.ZipFile):
    with tempfile.TemporaryDirectory() as td:
        zf.extractall(td)
        yield os.path.join(td, "prescription")
