"""v26 workstream 05: a documented observed zero is distinguishable from a monitor stop.

The database half (v259 CHECK, append-only, tenant RLS, re-run) was exercised on a disposable
PostgreSQL/PostGIS by the porting session; this file holds the parser and summary halves.
"""

from pathlib import Path

import pytest
from api.yield_map_ingestion import YieldMapIngestRequest, parse_yield_map
from core.yield_intelligence import build_canonical_yield_state

MIGRATION = Path(__file__).resolve().parents[3] / "migrations/v259_yield_map_observed_zero.sql"


def _sample(extra, value=0):
    return YieldMapIngestRequest(
        source_name="combine.geojson",
        source_format="geojson",
        idempotency_key="zero-1",
        payload={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "z1",
                    "geometry": {"type": "Point", "coordinates": [44, 15]},
                    "properties": {"yield_kg_ha": value, **extra},
                }
            ],
        },
    )


@pytest.mark.unit
def test_documented_zero_is_preserved_but_unreviewed():
    record = parse_yield_map(
        _sample({"zero_yield_observed": True, "zero_yield_evidence_id": " field-photo:123 "})
    ).records[0]
    assert record.yield_kg_ha == 0
    assert record.attributes["zero_yield_review_status"] == "pending"
    assert record.attributes["zero_yield_evidence_id"] == "field-photo:123"


@pytest.mark.unit
def test_caller_cannot_promote_a_zero_past_pending():
    record = parse_yield_map(
        _sample(
            {
                "zero_yield_observed": "TRUE",
                "zero_yield_evidence_id": "x",
                "zero_yield_review_status": "approved",
            }
        )
    ).records[0]
    assert record.attributes["zero_yield_review_status"] == "pending"


@pytest.mark.unit
@pytest.mark.parametrize(
    "attr",
    [
        {},
        {"zero_yield_observed": True},
        {"zero_yield_observed": True, "zero_yield_evidence_id": "  "},
        {"zero_yield_observed": False, "zero_yield_evidence_id": "x"},
        {"zero_yield_observed": "yes", "zero_yield_evidence_id": "x"},
    ],
)
def test_undocumented_zero_is_rejected(attr):
    with pytest.raises(ValueError, match="zero yield requires"):
        parse_yield_map(_sample(attr))


@pytest.mark.unit
def test_negative_is_rejected_even_when_documented():
    with pytest.raises(ValueError, match=">= 0"):
        parse_yield_map(
            _sample({"zero_yield_observed": True, "zero_yield_evidence_id": "x"}, value=-1)
        )


@pytest.mark.unit
def test_csv_documented_zero_supported():
    request = YieldMapIngestRequest(
        source_name="combine.csv",
        source_format="csv",
        idempotency_key="zero-csv",
        payload=(
            "longitude,latitude,yield_kg_ha,zero_yield_observed,zero_yield_evidence_id\n"
            "44,15,0,true,field-photo:123\n"
        ),
    )
    record = parse_yield_map(request).records[0]
    assert record.yield_kg_ha == 0
    assert record.attributes["zero_yield_observed"] is True


@pytest.mark.unit
def test_pending_zero_never_enters_the_canonical_yield_mean():
    zero = {"yield_kg_ha": 0.0, "attributes": {"zero_yield_review_status": "pending"}}
    state = build_canonical_yield_state(
        field_id="f",
        season_id="s",
        source_sha256="a" * 64,
        records=[{"yield_kg_ha": 3000.0}, zero],
        calibration_factor=1.0,
    )
    assert state.raw_mean_kg_ha == 3000.0 and state.min_kg_ha == 3000.0
    assert "pending_zero_yield_records:1" in state.limitations
    assert state.quality_status != "verified"


@pytest.mark.unit
def test_v259_guards_every_add_constraint_for_the_deploy_rerun():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count("ADD CONSTRAINT") == sql.count("IF NOT EXISTS") == 1
    assert "zero_yield_review_status' = 'pending'" in sql
    assert sql.index("ADD CONSTRAINT") < sql.index("DROP CONSTRAINT")
