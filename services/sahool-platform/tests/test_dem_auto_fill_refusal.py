"""dem_auto_fill must keep raster's refusal source/reason (not a blanket 'not configured')."""

import pytest
from core.engines.dem_enrichment import build_dem_auto_fill

pytestmark = pytest.mark.unit


def test_no_valid_pixels_refusal_is_preserved():
    computed = {
        "computed": False,
        "source": "dem-no-valid-pixels",
        "reason": "لا توجد قياسات ارتفاع صالحة داخل نطاق الحقل",
    }
    out = build_dem_auto_fill(computed)
    assert out["available"] is False
    assert out["source"] == "dem-no-valid-pixels"
    assert out["reason"] == computed["reason"]
    assert "dem-no-valid-pixels" in out["note_ar"]
    assert computed["reason"] in out["note_ar"]
    assert "FIELD_DEM_PATH" not in out["note_ar"]
    assert out["computed"] is computed


def test_not_configured_keeps_configuration_message():
    out = build_dem_auto_fill({"computed": False, "source": "dem-not-configured", "reason": "x"})
    assert out["available"] is False
    assert out["source"] == "dem-not-configured"
    assert "FIELD_DEM_PATH" in out["note_ar"]


def test_no_envelope_is_configuration_message_without_source():
    out = build_dem_auto_fill(None)
    assert out == {
        "available": False,
        "source": None,
        "reason": None,
        "computed": None,
        "note_ar": out["note_ar"],
    }
    assert "FIELD_DEM_PATH" in out["note_ar"]


def test_successful_compute_is_available():
    computed = {"computed": True, "source": "copernicus-dem-30m", "elevation_m": {"mean": 1200}}
    out = build_dem_auto_fill(computed)
    assert out["available"] is True
    assert out["source"] == "copernicus-dem-30m"
    assert out["reason"] is None
    assert "FIELD_DEM_PATH" not in out["note_ar"]


def test_refusal_without_reason_still_names_source():
    out = build_dem_auto_fill({"computed": False, "source": "field-outside-dem"})
    assert "field-outside-dem" in out["note_ar"]
    assert out["reason"] is None
