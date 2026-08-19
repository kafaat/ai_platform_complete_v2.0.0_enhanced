from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = "a" * 40


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def test_field_receipt_guard_accepts_only_restricted_two_tenant_live_proof():
    m = _load("s4_field_receipt_guard_test", "scripts/architecture/s4_field_rls_receipt_guard.py")
    receipt = {
        "schema": m.SCHEMA,
        "subject_sha": SUBJECT,
        "status": "PASSED",
        "observed_at": _now(),
        "service": "field-management-service",
        "source_identity": m._source_identity(),
        "source_identity_match": True,
        "application_role": {
            "name": "sahool_app",
            "superuser": False,
            "bypassrls": False,
            "createdb": False,
            "createrole": False,
            "reachable_privileged_role_count": 0,
        },
        "tenant_isolation": {
            "tenant_a": "tenant-a",
            "tenant_b": "tenant-b",
            "field_id": "field-a",
            "owner_http": 200,
            "cross_tenant_http": 404,
        },
        "authentication": {"missing_token_http": 401, "wrong_token_http": 401},
        "owner_or_superuser_proof_accepted": False,
        "authority_promotion": False,
    }
    assert m.findings(receipt, SUBJECT) == []

    for mutation in (
        lambda d: d["application_role"].__setitem__("bypassrls", True),
        lambda d: d["application_role"].__setitem__("reachable_privileged_role_count", 1),
        lambda d: d["tenant_isolation"].__setitem__("tenant_b", "tenant-a"),
        lambda d: d["tenant_isolation"].__setitem__("cross_tenant_http", 200),
        lambda d: d["authentication"].__setitem__("wrong_token_http", 200),
    ):
        broken = json.loads(json.dumps(receipt))
        mutation(broken)
        assert m.findings(broken, SUBJECT), broken


def _kg_receipt(m):
    cases = json.loads(m.CASES.read_text(encoding="utf-8"))
    freeze = json.loads(m.FREEZE.read_text(encoding="utf-8"))
    identity = m._source_identity()
    rows = []
    for case in cases:
        rows.append(
            {
                "case": case,
                "rest_count": case["min_edges"],
                "graphql_count": case["min_edges"],
                "parity": True,
                "minimum_evidence_met": True,
                "status": "PASSED",
                "edge_digest": "b" * 64,
            }
        )
    return {
        "schema": m.SCHEMA,
        "subject_sha": SUBJECT,
        "local_subject_sha": SUBJECT,
        "local_subject_match": True,
        "status": "PASSED",
        "observed_at": _now(),
        "read_only": True,
        "authority_promotion": False,
        "service": "knowledge-graph",
        "ready": {"status": "ready", "service": "knowledge-graph", "edges": 4},
        "source_identity": identity,
        "expected_source_identity": identity,
        "source_identity_match": True,
        "cases_sha256": m._sha(m.CASES),
        "consumer_freeze_sha256": m._sha(m.FREEZE),
        "consumer_fingerprint_sha256": freeze["consumer_fingerprint_sha256"],
        "case_count": len(cases),
        "non_empty_case_count": len(cases),
        "cases": rows,
    }


def test_kg_receipt_guard_rejects_empty_equal_results_and_source_drift():
    m = _load(
        "s4_kg_receipt_guard_test", "scripts/architecture/s4_kg_runtime_parity_receipt_guard.py"
    )
    receipt = _kg_receipt(m)
    assert m.findings(receipt, SUBJECT) == []

    empty = json.loads(json.dumps(receipt))
    empty["cases"][0]["rest_count"] = 0
    empty["cases"][0]["graphql_count"] = 0
    empty["cases"][0]["minimum_evidence_met"] = False
    empty["non_empty_case_count"] -= 1
    assert m.findings(empty, SUBJECT)

    drift = json.loads(json.dumps(receipt))
    drift["source_identity"]["kg_store_sha256"] = "0" * 64
    drift["source_identity_match"] = False
    assert m.findings(drift, SUBJECT)

    swapped = json.loads(json.dumps(receipt))
    swapped["cases"] = list(reversed(swapped["cases"]))
    assert m.findings(swapped, SUBJECT)


def test_kg_collector_requires_non_empty_governed_cases_and_live_source_identity(monkeypatch):
    m = _load("s4_kg_collector_test", "scripts/staging/kg_runtime_parity_collector.py")
    cases = json.loads(m.DEFAULT_CASES.read_text(encoding="utf-8"))
    expected_identity = m.expected_source_identity()

    def fake_get(url, headers=None, data=None):
        if url.endswith("/readyz"):
            return {
                "status": "ready",
                "service": "knowledge-graph",
                "edges": 4,
                "source_identity": expected_identity,
            }
        if "/v1/edges?" in url or url.endswith("/graphql"):
            return {
                "edges": [
                    {
                        "edge_id": "e1",
                        "subject_id": "wheat",
                        "relation": "historically_susceptible_to",
                        "object_id": "stripe_rust",
                        "confidence": "reference",
                        "prescriptive": False,
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(m, "get_json", fake_get)
    monkeypatch.setattr(m, "local_subject_sha", lambda: SUBJECT)
    doc = m.collect(
        base_url="http://kg", tenant_id="tenant-a", subject_sha=SUBJECT, cases_path=m.DEFAULT_CASES
    )
    assert doc["status"] == "PASSED"
    assert doc["source_identity_match"] is True
    assert doc["local_subject_sha"] == SUBJECT
    assert doc["local_subject_match"] is True
    assert doc["non_empty_case_count"] == len(cases)

    monkeypatch.setattr(m, "local_subject_sha", lambda: "b" * 40)
    with pytest.raises(ValueError, match="checkout_subject_sha_mismatch"):
        m.collect(
            base_url="http://kg",
            tenant_id="tenant-a",
            subject_sha=SUBJECT,
            cases_path=m.DEFAULT_CASES,
        )
    monkeypatch.setattr(m, "local_subject_sha", lambda: SUBJECT)

    def empty_get(url, headers=None, data=None):
        if url.endswith("/readyz"):
            return {
                "status": "ready",
                "service": "knowledge-graph",
                "edges": 4,
                "source_identity": expected_identity,
            }
        return {"edges": []}

    monkeypatch.setattr(m, "get_json", empty_get)
    doc = m.collect(
        base_url="http://kg", tenant_id="tenant-a", subject_sha=SUBJECT, cases_path=m.DEFAULT_CASES
    )
    assert doc["status"] == "FAILED"
    assert doc["non_empty_case_count"] == 0


def test_kg_readyz_exposes_shipped_source_digests_without_new_route():
    source = (ROOT / "services/knowledge-graph/main.py").read_text(encoding="utf-8")
    assert '"source_identity": _runtime_source_identity()' in source
    assert '@app.get("/runtime-identity")' not in source, (
        "المسار قانونيّ فقط في api/routers/platform_health.py — إضافته هنا يخالف عقد الموضع"
    )
    assert (
        "main_sha256" in source and "kg_store_sha256" in source and "gateway_deps_sha256" in source
    )
