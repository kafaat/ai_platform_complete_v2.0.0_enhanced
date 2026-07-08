"""تحقّق — حزمة نشر النشرة الإقليميّة (الشريحة C، V86): بنية/no-overwrite/manifest تصنيفيّ."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bulletin_bundle import run_bulletin_bundle  # noqa: E402

pytestmark = pytest.mark.unit

_TS = "2026-07-08T16:00:00Z"


def _bulletin() -> dict:
    return {
        "schema": "sahool.regional_bulletin/1",
        "period": "2026-06",
        "privacy_floor_fields": 5,
        "governorate_count": 1,
        "published_governorates": 1,
        "suppressed_governorates": 0,
        "governorates": [
            {
                "governorate": "الجوف",
                "status": "published",
                "condition": "watch",
                "mean_ndvi_anomaly": -0.08,
                "districts": [
                    {
                        "district": "الحزم",
                        "status": "published",
                        "condition": "poor",
                        "mean_ndvi_anomaly": -0.2,
                    },
                ],
            }
        ],
    }


def _stub(rows, **kw):
    return b"\x89PNG\r\n\x1a\nBULLETIN"


def test_bundle_creates_full_audited_tree(tmp_path):
    res = run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, render_fn=_stub)
    assert res["status"] == "completed"
    rd = Path(res["run_dir"])
    assert (rd / "maps" / "regional_bulletin_publication.png").exists()
    for p in ("run_manifest.json", "sources.json", "checksums.json"):
        assert (rd / "provenance" / p).exists()
    assert (rd / "scripts" / "figure_rows.json").exists()


def test_manifest_declares_categorical_not_geographic(tmp_path):
    res = run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, render_fn=_stub)
    m = json.loads((Path(res["run_dir"]) / "provenance" / "run_manifest.json").read_text("utf-8"))
    assert m["geographic"] is False and m["representation"] == "categorical_figure"
    assert m["geographic_blocker"] == "no_admin_boundaries_in_repo"
    assert m["external_fetch"] is False


def test_no_overwrite_enforced(tmp_path):
    run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, render_fn=_stub)
    with pytest.raises(FileExistsError):
        run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, render_fn=_stub)


def test_schema_mismatch_raises(tmp_path):
    with pytest.raises(ValueError, match="schema"):
        run_bulletin_bundle({"not": "a bulletin"}, root=tmp_path, ts_iso=_TS, render_fn=_stub)


def test_renderer_failure_is_failed_without_crashing(tmp_path):
    def _boom(rows, **kw):
        raise RuntimeError("boom")

    res = run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, render_fn=_boom)
    assert res["status"] == "failed" and res["render_ok"] is False
    assert (Path(res["run_dir"]) / "provenance" / "run_manifest.json").exists()
