"""Irrigation-water analysis contract: no false field binding, source vocabulary, overflow.

Owner pilot report (2026-11-13, rounds 1 and 2):
1. The web form sent ``field_id`` but ``WaterAnalysisRequest`` did not define it, so Pydantic
   dropped it silently while the page implied the result belonged to the selected field. The
   endpoint is a calculation and stores nothing, so it now refuses ``field_id`` (422) and says
   ``persisted: false``. A field-bound, stored result is the lab-water workflow's job.
2. ``source`` was free text and the form sent ``field:<field name>``, which is not a water
   source type. Owner decision 2026-11-14: the vocabulary is the seven types of the database
   contract (v168 ``irrigation_water_sources.source_type``), read here from the migration, so
   the API, the lab model and the web form cannot drift from it.
4. WATER-NUMERIC-OVERFLOW: finite but extreme inputs overflowed inside SAR/RSC/blend arithmetic.
   The owner's patch fails closed (``None``); this file adds the distinct reason, so the gap
   never reads as generic missing data. The owner's own tests are in
   ``test_irrigation_water_numeric_safety.py``.
"""

from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

import pytest
from core.irrigation_water_analysis import (
    WATER_NUMERIC_OVERFLOW,
    WATER_SOURCE_TYPES,
    WaterSample,
    analyze_water_sample,
    compute_blend_water_quality,
    compute_rsc,
    compute_sar,
    rsc_with_reason,
    sar_with_reason,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

pytestmark = pytest.mark.unit

BIG = 1.7e308  # finite, but the sum of two overflows
TINY = 1e-300

_SAFE = dict(na=1.0, ca=2.0, mg=2.0, hco3=1.0, co3=0.0, cl=1.0, ec_dsm=0.5, ph=7.2)


def _request(**kw):
    from api.api_models import WaterAnalysisRequest

    return WaterAnalysisRequest(**kw)


def _client():
    """The real router over HTTP, with the caller injected (no database is touched)."""
    from api.main import get_current_user
    from api.routers.irrigation import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _post(body):
    return _client().post("/api/v1/irrigation/water-analysis", json=body)


# ─── Gap 1: a calculation is not a field-bound sample ────────────────────────


def test_field_id_is_refused_not_silently_dropped():
    with pytest.raises(ValidationError, match="not saved to a field"):
        _request(sample_id="w1", field_id="fld-1")


def test_the_http_contract_refuses_field_id_with_422():
    r = _post({"sample_id": "w1", "field_id": "fld-1", **_SAFE})
    assert r.status_code == 422, r.text
    assert "lab/water-results" in r.text


def test_the_result_says_it_is_not_persisted():
    r = _post({"sample_id": "w1", **_SAFE})
    assert r.status_code == 200, r.text
    assert r.json()["persisted"] is False
    assert "field_id" not in r.json()


# ─── Gap 2: source vocabulary ─────────────────────────────────────────────────


_REPO = Path(__file__).resolve().parents[3]


def _v168_source_types() -> tuple[str, ...]:
    sql = (_REPO / "migrations" / "v168_irrigation_engineering_foundation.sql").read_text()
    match = re.search(r"source_type TEXT NOT NULL CHECK \(source_type IN \(([^)]*)\)\)", sql)
    assert match, "v168 no longer declares the source_type CHECK"
    return tuple(re.findall(r"'([a-z_]+)'", match.group(1)))


def test_the_source_vocabulary_is_the_v168_database_contract():
    assert WATER_SOURCE_TYPES == _v168_source_types()
    assert WATER_SOURCE_TYPES == (
        "well",
        "reservoir",
        "canal",
        "river",
        "municipal",
        "rainwater",
        "other",
    )


def test_the_web_form_offers_exactly_the_v168_source_types():
    ts = (_REPO / "frontend" / "src" / "lib" / "waterFieldOps.ts").read_text()
    block = ts.split("export const WATER_SOURCE_OPTIONS", 1)[1].split("];", 1)[0]
    assert tuple(re.findall(r"key: '([a-z_]+)'", block)) == _v168_source_types()
    api_ts = (_REPO / "frontend" / "src" / "services" / "api.ts").read_text()
    kind = re.search(r"export type WaterSourceKind =([^;]*);", api_ts).group(1)
    assert tuple(re.findall(r"'([a-z_]+)'", kind)) == _v168_source_types()


@pytest.mark.parametrize("source", WATER_SOURCE_TYPES)
def test_water_source_types_are_accepted(source):
    assert _request(sample_id="w1", source=source).source == source


def test_mixed_is_not_a_source_type_a_blend_is_several_sources():
    # v168 has no 'mixed'; a blend is several sources with v214 mixing ratios.
    with pytest.raises(ValidationError):
        _request(sample_id="w1", source="mixed")


def test_the_lab_water_route_takes_the_same_vocabulary():
    """The stored lab flow binds WaterSample's source type at its HTTP edge too."""
    from api.routers.soil_sampling import WaterLabResultIn
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def probe(payload):
        return {"source": payload.source}

    # This module postpones annotations; bind the real body type, not its name.
    probe.__annotations__["payload"] = WaterLabResultIn
    app = FastAPI()
    app.post("/probe")(probe)
    client = TestClient(app)
    assert client.post("/probe", json={"sample_id": "s", "source": "rainwater"}).json() == {
        "source": "rainwater"
    }
    for bad in ("mixed", "field:North", "WELL"):
        assert client.post("/probe", json={"sample_id": "s", "source": bad}).status_code == 422


def test_source_defaults_to_well():
    assert _request(sample_id="w1").source == "well"


@pytest.mark.parametrize("source", ["field:North block", "field:", "", "WELL", "river-ish"])
def test_a_field_label_or_free_text_is_not_a_water_source(source):
    with pytest.raises(ValidationError):
        _request(sample_id="w1", source=source)


def test_the_http_contract_returns_422_for_the_old_ui_source_value():
    r = _post({"sample_id": "w1", "source": "field:North", **_SAFE})
    assert r.status_code == 422, r.text


# ─── Gap 4: overflow fails closed with a distinct reason ─────────────────────


def test_overflow_reasons_are_distinct_from_missing_input():
    assert sar_with_reason(5.0, BIG, BIG) == (None, "numeric_overflow")  # was SAR 0.0
    assert sar_with_reason(1e308, TINY, 0.0) == (None, "numeric_overflow")  # was inf
    assert sar_with_reason(1.0, 0.0, 0.0) == (None, "calcium_plus_magnesium_zero")
    assert sar_with_reason(None, 1.0, 1.0) == (None, None)  # missing input: no reason
    assert rsc_with_reason(BIG, BIG, BIG, BIG) == (None, "numeric_overflow")  # was nan
    assert rsc_with_reason(None, 1.0, 1.0, 1.0) == (None, None)
    assert compute_sar(5.0, BIG, BIG) is None and compute_rsc(BIG, BIG, 1.0, 1.0) is None


def test_ordinary_values_are_unchanged():
    assert compute_sar(10, 4, 2) == pytest.approx(5.77, abs=0.01)
    assert compute_rsc(1, 5, 2, 1) == 3


def test_an_overflowed_index_is_reported_as_not_computable_not_as_missing_data():
    out = analyze_water_sample(
        WaterSample(sample_id="w1", na=5.0, ca=BIG, mg=BIG, co3=0.0, hco3=0.0, ec_dsm=0.5)
    )
    assert out["indices"]["sar"] is None
    assert out["missing_inputs"] == []  # nothing is missing
    reasons = {x["index"]: x for x in out["indices_not_computable"]}
    assert reasons["sar"]["reason"] == "numeric_overflow"
    assert reasons["sar"]["code"] == WATER_NUMERIC_OVERFLOW
    assert reasons["rsc_meq_l"]["reason"] == "numeric_overflow"
    note = out["classification"]["sodicity_sar"]["note_ar"]
    assert WATER_NUMERIC_OVERFLOW in note and "نقص" not in note
    assert out["verdict"] == "insufficient_data"
    assert out["verdict"] != "suitable"
    JSONResponse(out)


def test_complete_valid_sample_reports_no_uncomputable_index():
    out = analyze_water_sample(WaterSample(sample_id="w1", **_SAFE))
    assert out["indices_not_computable"] == []


@pytest.mark.parametrize(
    "values",
    [
        dict(na=1e308, ca=TINY, mg=0.0, co3=0.0, hco3=0.0, ec_dsm=0.5),
        dict(na=5.0, ca=BIG, mg=BIG, co3=0.0, hco3=0.0, ec_dsm=0.5),
        dict(na=1.0, ca=BIG, mg=BIG, co3=BIG, hco3=BIG, ec_dsm=0.5),
    ],
)
def test_the_endpoint_answers_200_with_the_typed_reason_never_500(values):
    r = _post({"sample_id": "w1", **values})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indices"]["sar"] is None
    assert body["indices_not_computable"][0]["code"] == WATER_NUMERIC_OVERFLOW


def _blend(**ion):
    return [
        {"source_id": "a", "mixing_ratio": 0.5, **ion},
        {"source_id": "b", "mixing_ratio": 0.5, **ion},
    ]


def test_blend_sar_overflow_is_a_typed_not_computable_not_ca_mg_zero():
    out = compute_blend_water_quality(
        _blend(ec_ds_m=1.0, sodium_meq_l=1.0, calcium_meq_l=BIG, magnesium_meq_l=BIG)
    )
    assert out["sar"]["status"] == "not_computable"
    assert out["sar"]["value"] is None
    assert out["sar"]["reason"] == "numeric_overflow"
    assert out["sar"]["code"] == WATER_NUMERIC_OVERFLOW
    assert out["ions_meq_l"] is None
    assert out["status"] == "partial"
    json.dumps(out, allow_nan=False)


def test_blend_sar_infinite_from_a_tiny_denominator_is_not_computable():
    out = compute_blend_water_quality(
        [
            {
                "source_id": "a",
                "mixing_ratio": 1.0,
                "ec_ds_m": 1.0,
                "sodium_meq_l": 1e308,
                "calcium_meq_l": TINY,
                "magnesium_meq_l": 0.0,
            }
        ]
    )
    assert out["sar"]["reason"] == "numeric_overflow"
    json.dumps(out, allow_nan=False)


def test_blend_zero_calcium_magnesium_keeps_its_own_reason():
    out = compute_blend_water_quality(
        _blend(ec_ds_m=1.0, sodium_meq_l=1.0, calcium_meq_l=0.0, magnesium_meq_l=0.0)
    )
    assert out["sar"]["reason"] == "calcium_plus_magnesium_zero"


def test_blend_ec_overflow_is_not_computable():
    out = compute_blend_water_quality(
        [
            {"source_id": "a", "mixing_ratio": 0.9995, "ec_ds_m": 1.7976931348623157e308},
            {"source_id": "b", "mixing_ratio": 0.0010, "ec_ds_m": 1.7976931348623157e308},
        ]
    )
    assert out["ec_ds_m"]["status"] == "not_computable"
    assert out["ec_ds_m"]["reason"] == "numeric_overflow"
    json.dumps(out, allow_nan=False)


# ─── Synthetic stress: 1,000 extreme samples, single and blended ─────────────


def _extreme(rng: random.Random) -> float | None:
    roll = rng.random()
    if roll < 0.1:
        return None
    if roll < 0.15:
        return 0.0
    if roll < 0.3:
        return rng.choice([BIG, 1.7976931348623157e308, 1e308, 5e-324, TINY])
    return 10 ** rng.uniform(-320, 308)


def _all_finite(obj) -> bool:
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(_all_finite(v) for v in obj.values())
    if isinstance(obj, list | tuple):
        return all(_all_finite(v) for v in obj)
    return True


def test_1000_extreme_samples_never_produce_a_non_finite_or_unexplained_none():
    rng = random.Random(20261113)
    overflowed = blend_overflow = 0
    for i in range(1000):
        values = {k: _extreme(rng) for k in ("na", "ca", "mg", "hco3", "co3", "cl", "ec_dsm")}
        out = analyze_water_sample(WaterSample(sample_id=f"s{i}", **values))
        assert _all_finite(out), out
        json.dumps(out, allow_nan=False)
        explained = {x["index"] for x in out["indices_not_computable"]}
        for index, needs in (
            ("sar", ("na", "ca", "mg")),
            ("rsc_meq_l", ("co3", "hco3", "ca", "mg")),
        ):
            if out["indices"][index] is None:
                # every None is either a missing input or a named reason
                assert index in explained or any(values[k] is None for k in needs), (i, out)
        overflowed += any(x["reason"] == "numeric_overflow" for x in out["indices_not_computable"])

        ratio = rng.random()
        blend = compute_blend_water_quality(
            [
                {
                    "source_id": sid,
                    "mixing_ratio": share,
                    "ec_ds_m": _extreme(rng),
                    "sodium_meq_l": _extreme(rng),
                    "calcium_meq_l": _extreme(rng),
                    "magnesium_meq_l": _extreme(rng),
                }
                for sid, share in (("a", ratio), ("b", 1.0 - ratio))
            ]
        )
        assert _all_finite(blend), blend
        json.dumps(blend, allow_nan=False)
        blend_overflow += any(
            blend[m].get("reason") == "numeric_overflow" for m in ("ec_ds_m", "sar")
        )
    # The stress must actually exercise the overflow path, not pass on easy inputs.
    assert overflowed >= 20, overflowed
    assert blend_overflow >= 10, blend_overflow
