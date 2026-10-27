"""
test_change_detection_validity.py — صدق كشف التغيّر: لا مقارنة بلا خلايا مشتركة،
ولا اتّجاه مؤشّر يتبدّل بحالة الأحرف.

  • S3-a: شبكتان لكلّ منهما قيم صالحة لكن بلا خليّة صالحة مشتركة ⇒ not_assessable
    ومقاييس null (لا mean_delta=0 ولا نسب 0% تُقرأ «استقراراً مرصوداً»).
  • S3-b: اسم المؤشّر يُطبَّع ويُتحقَّق منه مقابل قائمة معروفة باتّجاه صريح؛
    SALINITY ≡ salinity، والاسم المجهول يُرفض (ValueError ⇒ 422 على الحدود).
"""

from __future__ import annotations

import change_detection as cd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from raster_api_models import ChangeDetectRequest, FieldChangeRequest, IndicatorKind
from routers import analysis

pytestmark = pytest.mark.unit

_IDENT = {
    "crs": "EPSG:32638",
    "transform": [10.0, 0.0, 400000.0, 0.0, -10.0, 1600000.0],
    "geometry_revision": 1,
    "rows": 1,
    "cols": 2,
}
_TOKEN = "change-validity-token"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(analysis, "AGENT_TOKEN", _TOKEN)
    app = FastAPI()
    app.include_router(analysis.router)
    return TestClient(app)


def _payload(before, after, index="ndvi") -> dict:
    return {
        "field_id": "fld_1",
        "index": index,
        "date_before": "2025-03-01",
        "date_after": "2026-03-01",
        "grid_before": before,
        "grid_after": after,
        "grid_before_identity": _IDENT,
        "grid_after_identity": _IDENT,
    }


# ── S3-a: لا خلايا صالحة مشتركة ⇒ غير قابل للتقييم ومقاييس null ──


def test_no_common_valid_cells_is_not_assessable_with_null_metrics():
    res = cd.detect_change([[0.5, None]], [[None, 0.7]], index="ndvi")
    assert res["status"] == "not_assessable"
    assert "no_common_valid_pixels" in res["reason_codes"]
    assert res["valid_pixels"] == 0
    assert res["coverage_pct"] == 0.0
    for key in ("mean_delta", "improved_pct", "degraded_pct", "stable_pct", "degraded_grid_pct"):
        assert res[key] is None, key
    assert res["stats"] is None
    assert res["areas"] is None
    assert res["zones"] == []
    assert res["change_grid"] == [[None, None]]


def test_common_valid_cells_are_assessed():
    res = cd.detect_change([[0.5, None]], [[0.5, 0.7]], index="ndvi")
    assert res["status"] == "assessed"
    assert res["reason_codes"] == []
    assert res["mean_delta"] == 0.0
    assert res["stable_pct"] == 100.0


def test_route_no_common_valid_cells_not_assessable(monkeypatch):
    resp = _client(monkeypatch).post(
        "/v1/change/detect",
        headers={"X-Agent-Token": _TOKEN},
        json=_payload([[0.5, None]], [[None, 0.7]]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "not_assessable"
    assert "no_common_valid_pixels" in body["reason_codes"]
    assert body["mean_delta"] is None
    assert body["areas"] is None
    assert body["grid_identity"]["crs"] == "EPSG:32638"


def test_route_common_valid_cells_still_assessed(monkeypatch):
    resp = _client(monkeypatch).post(
        "/v1/change/detect",
        headers={"X-Agent-Token": _TOKEN},
        json=_payload([[0.6, 0.6]], [[0.3, 0.3]]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "assessed"
    assert resp.json()["degraded_pct"] == 100.0


# ── S3-b: اسم المؤشّر مُطبَّع ومُتحقَّق منه ──


@pytest.mark.parametrize("name", ["SALINITY", "Salinity", " salinity ", "NDSI", "soil-salinity"])
def test_salinity_direction_is_case_and_alias_insensitive(name):
    ref = cd.detect_change([[0.1]], [[0.5]], index="salinity")
    res = cd.detect_change([[0.1]], [[0.5]], index=name)
    assert ref["change_grid"] == [[cd.CODE_SEVERE_DEGRADATION]]
    assert res["change_grid"] == ref["change_grid"]
    assert res["direction"] == "higher_is_worse"


def test_ndvi_upper_case_keeps_vegetation_direction():
    res = cd.detect_change([[0.6]], [[0.2]], index="NDVI")
    assert res["index"] == "ndvi"
    assert res["direction"] == "lower_is_worse"
    assert res["change_grid"] == [[cd.CODE_SEVERE_DEGRADATION]]


@pytest.mark.parametrize("name", ["foo", "", "truecolor", "salinityy"])
def test_unknown_indicator_rejected(name):
    with pytest.raises(ValueError, match="unknown_change_index"):
        cd.detect_change([[0.1]], [[0.5]], index=name)


def test_every_scalar_indicator_kind_has_explicit_direction():
    scalar = {k.value for k in IndicatorKind} - {"truecolor", "et_inputs"}
    for name in scalar | {"salinity"}:
        assert cd.canonical_index(name.upper()) == name
        assert cd.index_direction(name) in ("higher_is_worse", "lower_is_worse")


def test_request_models_normalise_and_reject_unknown_index():
    assert (
        ChangeDetectRequest(**_payload([[0.1, 0.1]], [[0.5, 0.5]], "SALINITY")).index == "salinity"
    )
    assert FieldChangeRequest(index=" NDVI ", date_a="a", date_b="b").index == "ndvi"
    with pytest.raises(ValidationError, match="unknown_change_index"):
        ChangeDetectRequest(**_payload([[0.1, 0.1]], [[0.5, 0.5]], "foo"))
    with pytest.raises(ValidationError, match="unknown_change_index"):
        FieldChangeRequest(index="foo", date_a="a", date_b="b")


def test_route_unknown_index_is_422_and_upper_case_salinity_degrades(monkeypatch):
    client = _client(monkeypatch)
    headers = {"X-Agent-Token": _TOKEN}
    bad = client.post(
        "/v1/change/detect", headers=headers, json=_payload([[0.1, 0.1]], [[0.5, 0.5]], "foo")
    )
    assert bad.status_code == 422, bad.text
    ok = client.post(
        "/v1/change/detect", headers=headers, json=_payload([[0.1, 0.1]], [[0.5, 0.5]], "SALINITY")
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["degraded_pct"] == 100.0
    assert ok.json()["improved_pct"] == 0.0
