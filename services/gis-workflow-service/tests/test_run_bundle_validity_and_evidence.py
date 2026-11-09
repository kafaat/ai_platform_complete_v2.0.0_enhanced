"""run_bundle: ±inf ليس بكسلاً صالحاً، وفشل تسجيل الأدلّة لا يُبتلَع صامتاً."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_bundle import array_stats, run_workflow_bundle  # noqa: E402

pytestmark = pytest.mark.unit

_TS = "2026-07-08T15:30:22Z"


def _spec() -> dict:
    return {
        "workflow_id": "field_ndvi_publication_bundle",
        "target": {"type": "field", "field_id": "fld_ev"},
        "analysis": {"index": "ndvi", "source": "existing_raster_asset"},
        "outputs": {"publication_map": True},
        "self_checks": ["crs_present", "value_range"],
    }


def _meta() -> dict:
    return {
        "provider": "CDSE",
        "scene_id": "S2_x",
        "acquisition_date": "2026-06-01",
        "crs": "EPSG:4326",
        "resolution_m": 10,
        "valid_pixel_ratio": 0.9,
    }


def _values():
    return np.linspace(0.0, 0.8, 16).reshape(4, 4)


def _stub_renderer(values, layout, **kw):
    return b"\x89PNG\r\n\x1a\nSTUB"


def _run(tmp_path, **kw):
    return run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer, **kw
    )


def _manifest(res) -> dict:
    return json.loads(
        (Path(res["run_dir"]) / "provenance" / "run_manifest.json").read_text("utf-8")
    )


def test_inf_is_not_counted_as_valid_pixel():
    st = array_stats([[math.inf, 0.5]])
    assert st["valid_pixel_ratio"] == 0.5
    assert st["nodata_ratio"] == 0.5
    assert st["min"] == st["max"] == 0.5


def test_negative_inf_and_nan_are_both_invalid():
    st = array_stats([[-math.inf, math.nan], [0.1, 0.2]])
    assert st["valid_pixel_ratio"] == 0.5
    assert st["nodata_ratio"] == 0.5


def test_no_evidence_writer_means_not_requested(tmp_path):
    res = _run(tmp_path)
    assert res["evidence_registered"] is None
    assert res["evidence_registration_failed"] is False
    assert res["accepted"] is True
    assert "evidence_registered" not in _manifest(res)


def test_successful_evidence_registration_is_recorded(tmp_path):
    seen: list[dict] = []
    res = _run(tmp_path, evidence_writer=seen.append)
    assert len(seen) == 1
    assert res["evidence_registered"] is True
    assert res["evidence_error_class"] is None
    assert res["accepted"] is True
    m = _manifest(res)
    assert m["evidence_registered"] is True
    assert m["accepted"] is True


def test_failed_evidence_registration_is_not_swallowed(tmp_path):
    def _boom(manifest):
        raise ConnectionError("evidence store down")

    res = _run(tmp_path, evidence_writer=_boom)
    # still renderable…
    assert res["status"] == "completed"
    assert res["render_ok"] is True
    # …but not accepted, and the failure is visible.
    assert res["evidence_registered"] is False
    assert res["evidence_error_class"] == "ConnectionError"
    assert res["evidence_registration_failed"] is True
    assert res["accepted"] is False
    m = _manifest(res)
    assert m["evidence_registered"] is False
    assert m["evidence_error_class"] == "ConnectionError"
    assert m["accepted"] is False
    assert m["status"] == "completed"


def test_failed_run_is_never_accepted(tmp_path):
    def _bad_render(values, layout, **kw):
        raise RuntimeError("render failed")

    res = run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_bad_render
    )
    assert res["status"] == "failed"
    assert res["accepted"] is False
