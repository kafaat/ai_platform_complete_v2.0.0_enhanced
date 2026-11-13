"""دليل تغيّر Sentinel-1 حول تاريخ حراثة مُسجَّل (``radar_change_evidence``).

شبكات GeoTIFF اصطناعيّة قبل/بعد (UTM 38N، بكسل 10 م، ضجيج بقع ضربيّ ثابت البذرة)، بلا أيّ
نداء شبكة. كلّ اختبار يسمّي صنف الثقة المطلوب في معايير القبول:

* ارتفاع يشبه الخشونة على حقل عارٍ ⇒ consistent
* لا تغيّر ⇒ inconsistent
* ارتفاع مع مطر/ريّ مُسجَّل في النافذة ⇒ ambiguous
* مدار غير متطابق ⇒ ambiguous مع سبب مُعلَن
* بكسلات قليلة ⇒ insufficient
* لا مشهد في النافذة ⇒ no_acquisition

والنتيجة لا تكون «مُتحقَّقاً/إثباتاً» في أيّ صنف.
"""

from __future__ import annotations

import asyncio
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from pydantic import ValidationError
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import routers.analysis as analysis  # noqa: E402
import sar_tillage_evidence as ste  # noqa: E402
from raster_api_models import SarRviRequest  # noqa: E402

pytestmark = pytest.mark.unit

_CRS = "EPSG:32638"
_X0, _Y0, _PX = 500000.0, 1700000.0, 10.0
_SIZE = 40  # 40×40 بكسل = 400×400 م
_EVENT = "2026-03-15"
_TOKEN = "tok-sar-tillage"

# تربة عارية جافّة نموذجيّة (قدرة خطّيّة): VV ≈ −13 dB، VH ≈ −23 dB ⇒ VH/VV ≈ −10 dB.
_VV0, _VH0 = 0.05, 0.005
_ROUGH = 1.8  # ×1.8 ≈ +2.55 dB — ارتفاع يشبه زيادة الخشونة


def _write(path: Path, value: float, seed: int) -> str:
    rng = np.random.default_rng(seed)
    # بقع ضربيّة بمتوسّط 1 (ENL≈4.4 لـGRD IW) فلا تكون القيم ثابتة اصطناعيّاً.
    speckle = rng.gamma(shape=4.4, scale=1 / 4.4, size=(_SIZE, _SIZE))
    data = (value * speckle).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=_SIZE,
        height=_SIZE,
        count=1,
        dtype="float32",
        crs=_CRS,
        transform=from_origin(_X0, _Y0, _PX, _PX),
        nodata=float("nan"),
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _field(px_from: int, px_to: int) -> dict:
    """مضلّع مربّع بإحداثيّات البكسل داخل الشبكة، مُعاد إلى EPSG:4326."""
    x1, x2 = _X0 + px_from * _PX, _X0 + px_to * _PX
    y1, y2 = _Y0 - px_from * _PX, _Y0 - px_to * _PX
    ring = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]
    return transform_geom(_CRS, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


_BIG_FIELD = _field(5, 35)  # 30×30 = 900 بكسل
_TINY_FIELD = _field(10, 15)  # 5×5 = 25 بكسل < MIN_FIELD_PIXELS


def _acq(tmp: Path, tag: str, day: str, vv: float, vh: float, *, orbit=14, state="ascending"):
    seed = zlib.crc32(f"{tag}|{day}".encode())
    return {
        "item_id": f"S1A_{tag}_{day}",
        "datetime": f"{day}T03:05:00Z",
        "relative_orbit": orbit,
        "orbit_state": state,
        "vv_url": _write(tmp / f"{tag}_{day}_vv.tif", vv, seed),
        "vh_url": _write(tmp / f"{tag}_{day}_vh.tif", vh, seed + 1),
    }


def _assess(acqs, **kw):
    params = {
        "event_date": _EVENT,
        "field_geometry": _BIG_FIELD,
        "acquisitions": acqs,
        "backscatter_kind": "sigma0_linear",
        "moisture_checked": True,
        "surface_state_before": "bare",
    }
    params.update(kw)
    out = ste.assess_tillage_change(**params)
    # لا صنف يجعل الحدث مُتحقَّقاً.
    assert out["evidence_kind"] == "radar_change_evidence"
    assert out["verified"] is False and out["proof"] is False
    assert out["event_status_effect"] == "none"
    assert out["thresholds"]["calibrated"] is False
    return out


def _rough_pair(tmp: Path, **after_kw):
    before = _acq(tmp, "b", "2026-03-09", _VV0, _VH0)
    after = _acq(tmp, "a", "2026-03-21", _VV0 * _ROUGH, _VH0 * _ROUGH, **after_kw)
    return [before, after]


def test_roughness_rise_on_bare_field_is_consistent(tmp_path):
    out = _assess(_rough_pair(tmp_path))
    assert out["confidence_class"] == "consistent", out["reasons"]
    assert "backscatter_rise_consistent_with_roughness" in out["reasons"]
    d = out["backscatter"]["delta"]
    assert 2.0 < d["vv_db"] < 3.1 and 2.0 < d["vh_db"] < 3.1
    assert out["backscatter"]["kind"] == "sigma0_linear"
    assert out["pair"]["same_relative_orbit"] and out["pair"]["same_pass_direction"]
    assert out["pixels"]["valid_min"] >= ste.MIN_FIELD_PIXELS


def test_no_change_is_inconsistent(tmp_path):
    acqs = [
        _acq(tmp_path, "b", "2026-03-09", _VV0, _VH0),
        _acq(tmp_path, "a", "2026-03-21", _VV0, _VH0),
    ]
    out = _assess(acqs)
    assert out["confidence_class"] == "inconsistent", out["reasons"]
    assert "no_significant_backscatter_change" in out["reasons"]


@pytest.mark.parametrize("kind", ["rain", "irrigation"])
def test_rise_with_recorded_moisture_in_window_is_ambiguous(tmp_path, kind):
    out = _assess(
        _rough_pair(tmp_path),
        moisture_events=[{"date": "2026-03-18", "kind": kind, "amount_mm": 12.0}],
    )
    assert out["confidence_class"] == "ambiguous"
    assert f"{kind}_recorded_in_window" in out["reasons"]
    assert out["moisture"]["events_in_window"][0]["date"] == "2026-03-18"


def test_moisture_outside_window_does_not_downgrade(tmp_path):
    out = _assess(
        _rough_pair(tmp_path),
        moisture_events=[{"date": "2026-02-01", "kind": "rain", "amount_mm": 30.0}],
    )
    assert out["confidence_class"] == "consistent"
    assert out["moisture"]["events_in_window"] == []


def test_rise_without_moisture_check_is_ambiguous_and_declared(tmp_path):
    out = _assess(_rough_pair(tmp_path), moisture_checked=False)
    assert out["confidence_class"] == "ambiguous"
    assert "moisture_not_checked" in out["reasons"]
    assert "rise_without_moisture_check" in out["reasons"]


def test_orbit_mismatch_is_ambiguous_with_declared_reason(tmp_path):
    out = _assess(_rough_pair(tmp_path, orbit=87, state="descending"))
    assert out["confidence_class"] == "ambiguous"
    assert "relative_orbit_mismatch" in out["reasons"]
    assert "pass_direction_mismatch" in out["reasons"]
    assert out["pair"]["same_relative_orbit"] is False
    assert out["pair"]["same_pass_direction"] is False


def test_unknown_orbit_is_ambiguous(tmp_path):
    out = _assess(_rough_pair(tmp_path, orbit=None))
    assert out["confidence_class"] == "ambiguous"
    assert "relative_orbit_unknown" in out["reasons"]


def test_same_orbit_pair_preferred_over_closer_mismatch(tmp_path):
    acqs = _rough_pair(tmp_path)
    # مشهد أقرب للحدث لكن من مدار آخر: لا يُختار ما دام زوج المدار نفسه متاحاً.
    acqs.append(_acq(tmp_path, "x", "2026-03-16", _VV0, _VH0, orbit=87, state="descending"))
    out = _assess(acqs)
    assert out["pair"]["after"]["item_id"] == "S1A_a_2026-03-21"
    assert out["confidence_class"] == "consistent"


def test_too_few_pixels_is_insufficient(tmp_path):
    out = _assess(_rough_pair(tmp_path), field_geometry=_TINY_FIELD)
    assert out["confidence_class"] == "insufficient"
    assert out["pixels"]["valid_min"] < ste.MIN_FIELD_PIXELS
    assert "too_few_field_pixels_for_s1_resolution" in out["reasons"]
    assert out["backscatter"] is None


def test_db_valued_source_is_dropped_not_misread(tmp_path):
    """مصدر بالـdB (قيم سالبة) مُعلَن خطّيّاً خطأً: لا يُقرأ كقدرة، فلا أرقام."""
    acqs = [
        _acq(tmp_path, "b", "2026-03-09", -13.0, -23.0),
        _acq(tmp_path, "a", "2026-03-21", -10.0, -20.0),
    ]
    out = _assess(acqs)
    assert out["confidence_class"] == "insufficient"
    assert "non_positive_values_dropped_source_may_be_db_not_linear" in out["reasons"]


def test_no_scene_in_window_is_no_acquisition(tmp_path):
    acqs = [
        _acq(tmp_path, "b", "2026-01-10", _VV0, _VH0),  # قبل النافذة
        _acq(tmp_path, "a", "2026-03-21", _VV0 * _ROUGH, _VH0 * _ROUGH),
    ]
    out = _assess(acqs)
    assert out["confidence_class"] == "no_acquisition"
    assert "no_acquisition_before_event_in_window" in out["reasons"]
    assert out["backscatter"] is None and out["pair"] is None
    assert _assess([])["confidence_class"] == "no_acquisition"


def test_same_day_scene_is_excluded(tmp_path):
    acqs = [
        _acq(tmp_path, "b", _EVENT, _VV0, _VH0),
        _acq(tmp_path, "a", "2026-03-21", _VV0 * _ROUGH, _VH0 * _ROUGH),
    ]
    out = _assess(acqs)
    assert out["confidence_class"] == "no_acquisition"
    assert "same_day_acquisition_excluded" in out["reasons"]


def test_vegetated_before_is_ambiguous(tmp_path):
    # VH/VV قبل ≈ −4 dB (تشتّت حجميّ) ⇒ قد يكون حصاداً لا حراثة.
    acqs = [
        _acq(tmp_path, "b", "2026-03-09", 0.05, 0.02),
        _acq(tmp_path, "a", "2026-03-21", 0.05 * _ROUGH, 0.02 * _ROUGH),
    ]
    out = _assess(acqs, surface_state_before="unknown")
    assert out["confidence_class"] == "ambiguous"
    assert "volume_scattering_before_possible_vegetation_or_harvest" in out["reasons"]


def test_dn_backscatter_kind_rejected():
    with pytest.raises(ValueError):
        ste.assess_tillage_change(
            event_date=_EVENT,
            field_geometry=_BIG_FIELD,
            acquisitions=[],
            backscatter_kind="dn",
        )


# ─── المسار: وضع على POST /v1/sar/rvi القائم (لا مسار جديد) ─────────────────────


def _route(monkeypatch, tmp_path, acqs, **tillage):
    monkeypatch.setattr(analysis, "AGENT_TOKEN", _TOKEN)
    monkeypatch.setattr(analysis, "UPLOAD_DIR", str(tmp_path))
    body = {
        "field_id": "f-1",
        "date": _EVENT,
        "mode": "tillage_change_evidence",
        "tillage": {
            "field_geometry": _BIG_FIELD,
            "acquisitions": acqs,
            "backscatter_kind": "gamma0_linear",
            "moisture_checked": True,
            "surface_state_before": "bare",
            **tillage,
        },
    }
    return asyncio.run(analysis.sar_rvi_endpoint(SarRviRequest(**body), x_agent_token=_TOKEN))


def test_route_mode_returns_labelled_evidence(monkeypatch, tmp_path):
    out = _route(monkeypatch, tmp_path, _rough_pair(tmp_path))
    assert out["mode"] == "tillage_change_evidence" and out["field_id"] == "f-1"
    assert out["evidence_kind"] == "radar_change_evidence"
    assert out["confidence_class"] == "consistent"
    assert out["verified"] is False
    assert out["backscatter"]["kind"] == "gamma0_linear"


def test_route_rejects_source_outside_upload_dir(monkeypatch, tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    acqs = _rough_pair(tmp_path)  # الملفّات في tmp_path، والمجلّد المسموح inside
    monkeypatch.setattr(analysis, "AGENT_TOKEN", _TOKEN)
    monkeypatch.setattr(analysis, "UPLOAD_DIR", str(inside))
    body = {
        "field_id": "f-1",
        "date": _EVENT,
        "mode": "tillage_change_evidence",
        "tillage": {
            "field_geometry": _BIG_FIELD,
            "acquisitions": acqs,
            "backscatter_kind": "sigma0_linear",
        },
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analysis.sar_rvi_endpoint(SarRviRequest(**body), x_agent_token=_TOKEN))
    assert exc.value.status_code == 400


def test_route_requires_token(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "AGENT_TOKEN", _TOKEN)
    req = SarRviRequest(
        field_id="f",
        date=_EVENT,
        mode="tillage_change_evidence",
        tillage={"field_geometry": _BIG_FIELD, "backscatter_kind": "sigma0_linear"},
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analysis.sar_rvi_endpoint(req, x_agent_token="wrong"))
    assert exc.value.status_code in (401, 403)


def test_request_model_mode_contract():
    # rvi (الافتراضيّ) ما زال يتطلّب الشبكتين.
    with pytest.raises(ValidationError):
        SarRviRequest(field_id="f", date=_EVENT)
    with pytest.raises(ValidationError):
        SarRviRequest(field_id="f", date=_EVENT, mode="tillage_change_evidence")
    with pytest.raises(ValidationError):
        SarRviRequest(
            field_id="f",
            date=_EVENT,
            mode="tillage_change_evidence",
            tillage={"field_geometry": {"type": "Point"}, "backscatter_kind": "sigma0_linear"},
        )
    with pytest.raises(ValidationError):  # DN خام غير مقبول
        SarRviRequest(
            field_id="f",
            date=_EVENT,
            mode="tillage_change_evidence",
            tillage={"field_geometry": _BIG_FIELD, "backscatter_kind": "dn"},
        )
    ok = SarRviRequest(field_id="f", date=_EVENT, vv_grid=[[0.1]], vh_grid=[[0.01]])
    assert ok.mode == "rvi"


def test_radar_search_exposes_relative_orbit(monkeypatch):
    """بحث الرادار القائم يُمرّر sat:relative_orbit لاختيار زوج المدار نفسه (بلا شبكة)."""
    import stac_search

    feature = {
        "id": "S1A_IW_GRDH_X",
        "bbox": [44.0, 15.0, 45.0, 16.0],
        "properties": {
            "datetime": "2026-03-21T03:05:00Z",
            "sat:orbit_state": "ascending",
            "sat:relative_orbit": 14,
        },
        "assets": {"vv": {"href": "https://example.invalid/vv.tif"}},
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [feature]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(stac_search.httpx, "AsyncClient", _Client)
    out = asyncio.run(stac_search.stac_search_radar([44, 15, 45, 16], "a", "b", 5))
    item = out["items"][0]
    assert item["relative_orbit"] == 14 and item["orbit_state"] == "ascending"
