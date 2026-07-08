"""تحقّق — حزمة التشغيل (الشريحة B، V85): بنية/لا-overwrite/مانيفست/checksums/فشل الرسم."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_bundle import run_workflow_bundle  # noqa: E402

pytestmark = pytest.mark.unit

_TS = "2026-07-08T15:30:22Z"
_PNG = b"\x89PNG\r\n\x1a\nSTUB"


def _spec() -> dict:
    return {
        "workflow_id": "field_ndvi_publication_bundle",
        "target": {"type": "field", "field_id": "fld_123"},
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
    return _PNG


def test_bundle_creates_maps_reports_provenance(tmp_path):
    res = run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    assert res["status"] == "completed"
    rd = Path(res["run_dir"])
    assert (rd / "maps" / "ndvi_publication.png").exists()
    for r in ("methodology.md", "quality_report.md", "self_check.md"):
        assert (rd / "reports" / r).exists()
    for p in ("run_manifest.json", "sources.json", "checksums.json"):
        assert (rd / "provenance" / p).exists()
    assert (rd / "scripts" / "resolved_spec.json").exists()


def test_no_overwrite_enforced(tmp_path):
    run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    # نفس الـspec ونفس الوقت ⇒ نفس run_id ⇒ يجب أن يفشل (لا كتابة فوق تشغيل).
    with pytest.raises(FileExistsError):
        run_workflow_bundle(
            _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
        )


def test_invalid_spec_raises_with_reason(tmp_path):
    bad = _spec()
    bad["analysis"]["source"] = "gee"  # مصدر خارجيّ محظور
    with pytest.raises(ValueError, match="forbidden"):
        run_workflow_bundle(
            bad, _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
        )


def test_missing_acquisition_date_degrades(tmp_path):
    meta = _meta()
    del meta["acquisition_date"]
    res = run_workflow_bundle(
        _spec(), _values(), meta, root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    assert res["status"] == "degraded"


def test_missing_crs_fails(tmp_path):
    meta = _meta()
    del meta["crs"]
    res = run_workflow_bundle(
        _spec(), _values(), meta, root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    assert res["status"] == "failed" and res["self_check"]["passed"] is False


def test_ndvi_out_of_range_fails(tmp_path):
    vals = _values().copy()
    vals[0, 0] = 5.0  # خارج [-1,1]
    res = run_workflow_bundle(
        _spec(), vals, _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    assert res["status"] == "failed"


def test_manifest_has_lineage_fields(tmp_path):
    res = run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    m = json.loads((Path(res["run_dir"]) / "provenance" / "run_manifest.json").read_text("utf-8"))
    assert m["source"] == "existing_raster_asset" and m["external_fetch"] is False
    assert m["scene_id"] == "S2_x" and m["acquisition_date"] == "2026-06-01"
    assert m["crs"] == "EPSG:4326" and m["resolution_m"] == 10


def test_checksums_generated_for_outputs(tmp_path):
    res = run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_stub_renderer
    )
    cs = json.loads((Path(res["run_dir"]) / "provenance" / "checksums.json").read_text("utf-8"))
    assert any(k.endswith("ndvi_publication.png") for k in cs)
    assert all(len(v) == 64 and all(ch in "0123456789abcdef" for ch in v) for v in cs.values())


def test_renderer_failure_gives_failed_status_without_crashing(tmp_path):
    def _boom(values, layout, **kw):
        raise RuntimeError("render exploded")

    res = run_workflow_bundle(
        _spec(), _values(), _meta(), root=tmp_path, ts_iso=_TS, render_fn=_boom
    )
    assert res["status"] == "failed" and res["render_ok"] is False
    # الحزمة لم تنكسر: المانيفست والتقارير مكتوبة رغم فشل الرسم.
    rd = Path(res["run_dir"])
    assert (rd / "provenance" / "run_manifest.json").exists()
    m = json.loads((rd / "provenance" / "run_manifest.json").read_text("utf-8"))
    assert m["render_ok"] is False and "render exploded" in (m["render_error"] or "")
