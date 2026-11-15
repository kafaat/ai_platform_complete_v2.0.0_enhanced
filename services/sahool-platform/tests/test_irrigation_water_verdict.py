"""Irrigation-water verdict: invalid input is refused, partial data is not "suitable".

Owner reproduction (2026-11-13): EC = -1 dS/m with no ion measurements returned
«صالح للريّ» and «لا قيود» while the same response reported the data as incomplete.
"""

import math

import pytest
from core.irrigation_water_analysis import WaterSample, analyze_water_sample, classify_ec

pytestmark = pytest.mark.unit

_FULL_SAFE = dict(na=1.0, ca=2.0, mg=2.0, hco3=1.0, co3=0.0, cl=1.0, ec_dsm=0.5, ph=7.2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ec_dsm", -1.0),
        ("ec_dsm", math.nan),
        ("ec_dsm", math.inf),
        ("na", -0.1),
        ("hco3", -2.0),
        ("ph", 15.0),
        ("ph", -0.5),
    ],
)
def test_physically_impossible_inputs_are_refused(field, value):
    with pytest.raises(ValueError, match=field):
        WaterSample(sample_id="w1", **{field: value})


def test_owner_reproduction_negative_ec_without_ions_never_reads_suitable():
    with pytest.raises(ValueError):
        WaterSample(sample_id="w1", ec_dsm=-1.0)
    assert classify_ec(-1.0)["class"] is None
    assert "لا قيود" not in str(classify_ec(-1.0))


def test_low_ec_without_ions_is_insufficient_data_with_partial_result_kept():
    out = analyze_water_sample(WaterSample(sample_id="w1", ec_dsm=0.4))
    assert out["verdict"] == "insufficient_data"
    assert out["suitable_ar"] == "بيانات غير كافية للحكم العامّ"
    assert out["suitable_ar"] != "صالح للريّ"
    # the valid partial result stays visible
    assert out["classification"]["salinity"]["class"] == "low"
    assert set(out["not_assessed"]) == {"sodicity", "alkalinity"}
    assert out["data_complete"] is False


def test_a_hazard_found_with_partial_data_still_reads_needs_treatment():
    out = analyze_water_sample(WaterSample(sample_id="w1", ec_dsm=4.0))
    assert out["verdict"] == "needs_treatment"
    assert "ملوحة شديدة" in out["hazard_flags_ar"]


def test_suitable_only_when_all_three_axes_are_assessed():
    out = analyze_water_sample(WaterSample(sample_id="w1", **_FULL_SAFE))
    assert out["verdict"] == "suitable"
    assert out["suitable_ar"] == "صالح للريّ"
    assert out["not_assessed"] == []


def test_zero_calcium_plus_magnesium_leaves_sodicity_unassessed():
    out = analyze_water_sample(WaterSample(sample_id="w1", **{**_FULL_SAFE, "ca": 0.0, "mg": 0.0}))
    assert out["classification"]["sodicity_sar"]["class"] is None
    assert out["verdict"] in {"insufficient_data", "needs_treatment"}
    assert out["verdict"] != "suitable"
    assert out["data_complete"] is False


def test_engine_rejects_an_instance_mutated_after_construction():
    sample = WaterSample(sample_id="w1", ec_dsm=0.5, na=1, ca=2, mg=2)
    sample.ec_dsm = -1
    with pytest.raises(ValueError, match="ec_dsm"):
        analyze_water_sample(sample)


def test_the_analysis_endpoint_returns_422_for_negative_ec():
    from api.api_models import WaterAnalysisRequest
    from api.routers.irrigation import irrigation_water_analysis
    from fastapi import HTTPException
    from pydantic import ValidationError

    # Normal JSON input never reaches the handler: FastAPI/Pydantic return HTTP 422.
    with pytest.raises(ValidationError):
        WaterAnalysisRequest(sample_id="w1", ec_dsm=-1.0)
    # A programmatic caller bypassing the schema must also be refused by the engine.
    bypassed = WaterAnalysisRequest.model_construct(sample_id="w1", ec_dsm=-1.0)
    with pytest.raises(HTTPException) as exc:
        irrigation_water_analysis(bypassed, user=None)
    assert exc.value.status_code == 422


def test_the_lab_water_results_body_refuses_negative_ec_with_422():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    def probe(payload: WaterSample):
        return {"ok": True}

    # Avoid a decorator on a test-only route: the static service inventory
    # must not count this probe as a production API endpoint.
    probe_path = "/probe"
    app.add_api_route(probe_path, probe, methods=["POST"])

    r = TestClient(app).post(probe_path, json={"sample_id": "w1", "ec_dsm": -1})
    assert r.status_code == 422


def test_all_axes_calculated_but_only_optional_chloride_missing():
    full = dict(_FULL_SAFE)
    full.pop("cl")
    out = analyze_water_sample(WaterSample(sample_id="w1", **full))
    assert out["verdict"] == "suitable"
    assert out["data_complete"] is True
