"""bulletin_bundle: فشل تسجيل الأدلّة لا يُبتلَع صامتاً (نفس عقد run_bundle)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bulletin_figure  # noqa: E402
from bulletin_bundle import run_bulletin_bundle  # noqa: E402
from run_bundle import register_evidence  # noqa: E402

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
                "districts": [],
            }
        ],
    }


def _stub(rows, **kw):
    return b"\x89PNG\r\n\x1a\nBULLETIN"


def _run(tmp_path, **kw):
    kw.setdefault("render_fn", _stub)
    return run_bulletin_bundle(_bulletin(), root=tmp_path, ts_iso=_TS, **kw)


def _manifest(res) -> dict:
    return json.loads(
        (Path(res["run_dir"]) / "provenance" / "run_manifest.json").read_text("utf-8")
    )


def test_no_evidence_writer_means_not_requested(tmp_path):
    res = _run(tmp_path)
    assert res["status"] == "completed"
    assert res["evidence_registered"] is None
    assert res["evidence_error_class"] is None
    assert res["evidence_registration_failed"] is False
    assert res["accepted"] is True
    assert "evidence_registered" not in _manifest(res)


def test_successful_evidence_registration_is_recorded(tmp_path):
    seen: list[dict] = []
    res = _run(tmp_path, evidence_writer=seen.append)
    assert len(seen) == 1
    assert seen[0]["representation"] == "categorical_figure"
    assert res["evidence_registered"] is True
    assert res["accepted"] is True
    m = _manifest(res)
    assert m["evidence_registered"] is True
    assert m["evidence_registration_failed"] is False
    assert m["accepted"] is True


def test_failed_evidence_registration_is_not_swallowed(tmp_path):
    def _boom(manifest):
        raise ConnectionError("evidence store down")

    res = _run(tmp_path, evidence_writer=_boom)
    # still renderable…
    assert res["status"] == "completed"
    assert res["render_ok"] is True
    # …but not accepted, and the failure is visible in result and manifest.
    assert res["evidence_registered"] is False
    assert res["evidence_error_class"] == "ConnectionError"
    assert res["evidence_registration_failed"] is True
    assert res["accepted"] is False
    m = _manifest(res)
    assert m["status"] == "completed"
    assert m["evidence_registered"] is False
    assert m["evidence_error_class"] == "ConnectionError"
    assert m["evidence_registration_failed"] is True
    assert m["accepted"] is False


def test_failed_render_is_never_accepted_even_with_evidence(tmp_path):
    def _bad_render(rows, **kw):
        raise RuntimeError("render failed")

    seen: list[dict] = []
    res = _run(tmp_path, render_fn=_bad_render, evidence_writer=seen.append)
    assert res["status"] == "failed"
    assert res["evidence_registered"] is True
    assert res["accepted"] is False
    assert _manifest(res)["accepted"] is False


def test_register_evidence_helper_contract():
    assert register_evidence(None, {}, "completed")["evidence_registered"] is None

    def _boom(_m):
        raise ValueError("x")

    out = register_evidence(_boom, {}, "degraded")
    assert out == {
        "evidence_registered": False,
        "evidence_error_class": "ValueError",
        "evidence_registration_failed": True,
        "accepted": False,
    }
    assert register_evidence(lambda _m: None, {}, "degraded")["accepted"] is True


def test_bulletin_required_check_with_unknown_result_does_not_pass(monkeypatch):
    real_result = bulletin_figure._result

    def _unknown_privacy(name, severity, passed, detail):
        if name == "privacy_floor_respected":
            passed = None
        return real_result(name, severity, passed, detail)

    monkeypatch.setattr(bulletin_figure, "_result", _unknown_privacy)
    sc = bulletin_figure.bulletin_self_checks(_bulletin())
    assert sc["passed"] is False
    assert sc["quality"] == "failed"
    assert sc["n_failed_required"] == 1
