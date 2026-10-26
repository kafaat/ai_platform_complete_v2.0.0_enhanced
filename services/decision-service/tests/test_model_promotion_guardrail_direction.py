"""Behavioural tests for create_model_promotion_decision guardrail direction.

Guardrail metrics must be judged in their own direction: for an error metric (mae, rmse, ...)
a larger candidate value is a regression, not an improvement. The primary-metric threshold
must also be non-negative so a policy cannot declare a worse model eligible. These tests run
the persistence function against an in-memory fake connection (no Postgres).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001103"


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, baseline: dict, candidate: dict):
        self.baseline = baseline
        self.candidate = candidate
        self.inserted: tuple | None = None

    def transaction(self):
        return _Tx()

    async def execute(self, *args):
        return None

    async def fetchrow(self, sql, *args):
        if "FROM decision_model_promotion_decisions" in sql:
            return None
        if "FROM decision_model_evaluation_runs" in sql:
            return {
                "baseline_metrics": self.baseline,
                "candidate_metrics": self.candidate,
                "model_id": "m",
                "feature_set_id": None,
                "candidate_artifact_uri": "u",
                "candidate_artifact_digest": "d" * 64,
                "agronomic_cohorts": {},
                "agronomic_cohort_fingerprint": "f",
            }
        if "INSERT INTO decision_model_promotion_decisions" in sql:
            self.inserted = args
            return {
                "promotion_decision_id": args[0],
                "evaluation_run_id": args[2],
                "model_id": "m",
                "feature_set_id": None,
                "policy_version": args[5],
                "policy_snapshot": json.loads(args[6]),
                "metric_deltas": json.loads(args[7]),
                "decision_state": args[8],
                "decision_reason": args[9],
                "candidate_artifact_uri": "u",
                "candidate_artifact_digest": "d" * 64,
                "agronomic_cohorts": {},
                "agronomic_cohort_fingerprint": "f",
                "decided_by": "x",
                "decided_at": "t",
            }
        raise AssertionError(f"unexpected query: {sql}")

    async def close(self):
        return None


def _payload(**overrides) -> SimpleNamespace:
    base = {
        "evaluation_run_id": "eval_1",
        "policy_version": "v1",
        "primary_metric": "rmse",
        "min_improvement": 0.5,
        "lower_is_better": True,
        "max_regression": 0.0,
        "guardrail_metrics": ["mae"],
        "idempotency_key": "idem_1",
        "metadata": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _decide(monkeypatch, conn: _FakeConn, payload: SimpleNamespace) -> dict:
    async def fake_connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", fake_connect)
    return asyncio.run(
        persistence.create_model_promotion_decision(
            tenant_id=TENANT, decided_by="x", payload=payload
        )
    )


def test_error_guardrail_getting_worse_is_a_regression(monkeypatch):
    # Primary rmse improves 10 -> 9, but guardrail mae degrades 2 -> 9.
    conn = _FakeConn({"rmse": 10.0, "mae": 2.0}, {"rmse": 9.0, "mae": 9.0})
    result = _decide(monkeypatch, conn, _payload())
    assert result["decision_state"] == "promotion_rejected"
    assert result["decision_reason"] == "guardrail_regression"
    assert result["metric_deltas"]["mae"] == pytest.approx(-7.0)
    assert result["policy_snapshot"]["failed_guardrails"] == ["mae"]


def test_error_guardrail_improving_is_not_a_regression(monkeypatch):
    conn = _FakeConn({"rmse": 10.0, "mae": 2.0}, {"rmse": 9.0, "mae": 1.5})
    result = _decide(monkeypatch, conn, _payload())
    assert result["decision_state"] == "promotion_eligible"
    assert result["metric_deltas"]["mae"] == pytest.approx(0.5)


def test_higher_is_better_guardrail_keeps_its_direction(monkeypatch):
    conn = _FakeConn({"rmse": 10.0, "accuracy": 0.9}, {"rmse": 9.0, "accuracy": 0.8})
    result = _decide(monkeypatch, conn, _payload(guardrail_metrics=["accuracy"]))
    assert result["decision_state"] == "promotion_rejected"
    assert result["metric_deltas"]["accuracy"] == pytest.approx(-0.1)


def test_explicit_guardrail_spec_sets_direction(monkeypatch):
    # "yield_gap" is not a known error-metric name; the spec says lower is better.
    conn = _FakeConn({"rmse": 10.0, "yield_gap": 1.0}, {"rmse": 9.0, "yield_gap": 3.0})
    spec = [{"metric": "yield_gap", "lower_is_better": True}]
    result = _decide(monkeypatch, conn, _payload(guardrail_metrics=spec))
    assert result["decision_state"] == "promotion_rejected"
    assert result["metric_deltas"]["yield_gap"] == pytest.approx(-2.0)
    assert result["policy_snapshot"]["guardrail_directions"] == {"yield_gap": True}


def test_negative_min_improvement_is_refused(monkeypatch):
    conn = _FakeConn({"rmse": 10.0, "mae": 2.0}, {"rmse": 11.0, "mae": 2.0})
    result = _decide(monkeypatch, conn, _payload(min_improvement=-5.0, guardrail_metrics=[]))
    assert result == {"status": "conflict", "reason": "min_improvement_must_be_non_negative"}
    assert conn.inserted is None


@pytest.mark.parametrize(
    "spec",
    [
        [{"metric": "mae", "lower_is_better": "yes"}],
        [{"lower_is_better": True}],
        ["mae", {"metric": "mae", "lower_is_better": False}],
    ],
)
def test_malformed_or_contradictory_guardrail_specs_are_refused(monkeypatch, spec):
    conn = _FakeConn({"rmse": 10.0, "mae": 2.0}, {"rmse": 9.0, "mae": 2.0})
    result = _decide(monkeypatch, conn, _payload(guardrail_metrics=spec))
    assert result == {"status": "conflict", "reason": "guardrail_metrics_invalid"}
    assert conn.inserted is None


def test_plain_name_request_hash_is_unchanged():
    payload = _payload(guardrail_metrics=["mae", "accuracy", "mae"])
    legacy = hashlib.sha256(
        json.dumps(
            {
                "evaluation_run_id": payload.evaluation_run_id,
                "policy_version": payload.policy_version,
                "primary_metric": payload.primary_metric,
                "min_improvement": payload.min_improvement,
                "lower_is_better": payload.lower_is_better,
                "max_regression": payload.max_regression,
                "guardrail_metrics": sorted(set(payload.guardrail_metrics)),
                "metadata": payload.metadata,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    assert persistence._promotion_decision_hash(payload) == legacy
