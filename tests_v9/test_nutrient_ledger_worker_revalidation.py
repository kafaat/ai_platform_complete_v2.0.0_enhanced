"""N5: the learning worker must not trust a stored ledger's own permission claims.

``_process_projection_request`` rebuilt ``CanonicalNutrientLedger(**payload)`` and
persisted it as canonical truth, so a payload saying
``operational_recommendation_allowed: true`` over missing soil evidence became a
fertilization-capable ledger.  ``nutrient_ledger_from_payload`` re-derives the
decision with the builder's own rules (``ledger_inconsistencies``).
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "services/sahool-platform/workers/canonical_execution_learning_worker.py"
NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _worker():
    spec = importlib.util.spec_from_file_location("_learning_worker_nutrient_check", WORKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stored_payload(**soil_kw) -> dict:
    """A ledger as the projection request stores it: JSON, ISO timestamps."""
    from api.canonical_nutrient_ledger import (
        CropNutrientDemand,
        SoilNutrientEvidence,
        build_canonical_nutrient_ledger,
    )

    soil = None
    if soil_kw.pop("with_soil", True):
        soil = SoilNutrientEvidence(
            sampled_at=NOW - timedelta(days=10),
            evidence_digest="a" * 64,
            nitrogen_kg_ha=25.0,
            phosphorus_kg_ha=5.0,
            potassium_kg_ha=45.0,
            **soil_kw,
        )
    ledger = build_canonical_nutrient_ledger(
        tenant_id="t",
        field_id="f",
        season_id="s",
        crop_id="wheat",
        cultivar_id=None,
        phenology_stage="development",
        as_of=NOW,
        soil=soil,
        demand=CropNutrientDemand(
            evidence_digest="b" * 64,
            nitrogen_kg_ha=100.0,
            phosphorus_kg_ha=30.0,
            potassium_kg_ha=40.0,
        ),
        applications=[],
    )
    return json.loads(json.dumps(asdict(ledger), default=lambda v: v.isoformat()))


def test_consistent_stored_ledger_is_accepted():
    worker = _worker()
    for payload in (_stored_payload(), _stored_payload(with_soil=False)):
        ledger, problems = worker.nutrient_ledger_from_payload(payload)
        assert problems == []
        assert ledger is not None and ledger.ledger_digest == payload["ledger_digest"]


def test_forged_permission_over_missing_soil_is_rejected():
    worker = _worker()
    payload = _stored_payload(with_soil=False)
    assert payload["operational_recommendation_allowed"] is False
    payload.update(operational_recommendation_allowed=True, status="managed")
    ledger, problems = worker.nutrient_ledger_from_payload(payload)
    assert ledger is None
    assert "OPERATIONAL_ALLOWED_MISMATCH" in problems


def test_unknown_supply_balance_closed_as_zero_is_rejected():
    worker = _worker()
    payload = _stored_payload()
    n = next(b for b in payload["balances"] if b["nutrient"] == "N")
    n.update(soil_supply_kg_ha=None, remaining_requirement_kg_ha=100.0, surplus_kg_ha=0.0)
    _, problems = worker.nutrient_ledger_from_payload(payload)
    assert "N_BALANCE_CLOSED_WITHOUT_SUPPLY" in problems


@pytest.mark.parametrize(
    "mutate", [lambda p: p.pop("as_of"), lambda p: p.update(balances=[{"x": 1}])]
)
def test_malformed_payload_is_rejected_without_raising(mutate):
    worker = _worker()
    payload = _stored_payload()
    mutate(payload)
    ledger, problems = worker.nutrient_ledger_from_payload(payload)
    assert ledger is None and problems == ["MALFORMED_NUTRIENT_PAYLOAD"]


def test_worker_marks_rejected_request_failed_before_persisting():
    text = WORKER_PATH.read_text(encoding="utf-8")
    branch = text[text.index('elif kind == "nutrient":') :]
    assert branch.index("nutrient_ledger_from_payload(") < branch.index(
        "persist_nutrient_projection("
    )
    assert "status='failed'" in branch.split("persist_nutrient_projection(")[0]
