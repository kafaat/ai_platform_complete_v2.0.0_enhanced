"""تحقّق — عقد الـWorkflow Spec (الشريحة B): بنية صالحة + رفض المصادر الخارجيّة بسبب."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_spec import resolve_spec, validate_spec  # noqa: E402

pytestmark = pytest.mark.unit


def _valid() -> dict:
    return {
        "workflow_id": "field_ndvi_publication_bundle",
        "target": {"type": "field", "field_id": "fld_123"},
        "analysis": {"index": "ndvi", "source": "existing_raster_asset"},
        "outputs": {"publication_map": True},
        "self_checks": ["crs_present", "value_range"],
    }


def test_valid_spec_passes_and_resolves():
    ok, reason = validate_spec(_valid())
    assert ok and reason is None
    resolved = resolve_spec(_valid())
    assert resolved["analysis"]["index"] == "ndvi"
    assert resolved["outputs"]["quality_report"] is True  # افتراض


def test_invalid_spec_fails_with_reason():
    bad = _valid()
    del bad["workflow_id"]
    ok, reason = validate_spec(bad)
    assert not ok and "workflow_id" in reason
    ok2, reason2 = validate_spec({"workflow_id": "x", "target": {"type": "field"}})
    assert not ok2 and "field_id" in reason2


def test_external_sources_forbidden_in_slice_b():
    for ext in ("gee", "earthaccess", "wapor", "worldcereal", "hls"):
        bad = _valid()
        bad["analysis"]["source"] = ext
        ok, reason = validate_spec(bad)
        assert not ok and "forbidden" in reason
