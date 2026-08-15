from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts/ci" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_field_authority_policy_assigns_existing_writers_without_third_value_registry() -> None:
    policy = json.loads(
        (ROOT / "docs/capability-registry/field_authority_policy.json").read_text(encoding="utf-8")
    )
    assert policy["schema"] == "sahool.capability-field-authority/v1"
    fields = policy["field_authority"]
    assert fields["maturity"]["enum"] == list(range(6))
    assert fields["evidence_level"]["enum"] == list(range(6))
    assert fields["runtime.verification_receipts"] == {
        "authority": "runtime_verification",
        "append_only": True,
        "receipt_type": "attested-runtime-verification",
    }
    assert fields["runtime_verified"]["authority"] == "runtime_verification"
    assert fields["production_certified"]["authority"] == "certification"
    assert policy["reconciliation"]["no_third_value_registry"] is True
    assert "status" in policy["reconciliation"]["exclude_raw"]


def _attested_receipt(application_id: str = "a" * 64) -> dict:
    return {
        "type": "attested-runtime-verification",
        "application_id": application_id,
        "candidate_id": "candidate-1",
        "target_sha": "b" * 40,
        "environment_id": "staging-pg16",
        "evidence_bundle_sha256": "c" * 64,
        "approved_at": "2026-08-14T00:00:00Z",
        "approval_run_id": "123",
        "provenance": {"verified": True},
    }


def test_instrumentation_refresh_preserves_attested_runtime_receipt_and_foreign_authority_fields() -> (
    None
):
    mod = load_script("capability_runtime_evidence.py")
    receipt = _attested_receipt()
    source = {
        "capabilities": [
            {
                "id": "X-001",
                "title": "X",
                "services": [],
                "apis": [],
                "tests": [],
                "evidence": [],
                "runtime": {"metrics": [], "traces": [], "receipts": [receipt], "audit_events": []},
                "runtime_verified": True,
                "production_certified": True,
                "status": "owned_elsewhere",
            }
        ]
    }
    derived = mod.derive(source)["capabilities"][0]
    assert receipt in derived["runtime"]["receipts"]
    assert derived["runtime_verified"] is True
    assert derived["production_certified"] is True
    assert derived["status"] == "owned_elsewhere"


def test_instrumentation_writer_is_bound_to_field_authority_policy(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("capability_runtime_evidence.py")
    broken = json.loads(mod.FIELD_AUTHORITY_POLICY.read_text(encoding="utf-8"))
    broken["field_authority"]["runtime.verification_receipts"]["authority"] = (
        "repository_runtime_instrumentation"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setattr(mod, "FIELD_AUTHORITY_POLICY", policy)
    with pytest.raises(ValueError, match="receipt authority mismatch|field authority mismatch"):
        mod.derive({"capabilities": []})


def test_runtime_authority_requires_claim_services_and_governed_application_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("runtime_certification_gate.py")
    monkeypatch.setattr(mod, "APPLY_LEDGER_DIR", tmp_path)
    receipt = _attested_receipt()
    cap = {"id": "X-001", "runtime": {"receipts": [receipt]}}

    valid, errors = mod.governed_receipts(cap)
    assert valid == []
    assert errors == ["application_ledger_missing"]

    ledger = {
        "application_id": receipt["application_id"],
        "candidate_id": receipt["candidate_id"],
        "approval_run_id": receipt["approval_run_id"],
        "target_sha": receipt["target_sha"],
        "environment_id": receipt["environment_id"],
        "capabilities": ["X-001"],
    }
    (tmp_path / f"{receipt['application_id']}.json").write_text(
        json.dumps(ledger), encoding="utf-8"
    )
    valid, errors = mod.governed_receipts(cap)
    assert valid == [receipt]
    assert errors == []
    assert mod.runtime_authority_verified(True, True, valid, errors) is True
    assert mod.runtime_authority_verified(True, True, [], []) is False
    assert mod.runtime_authority_verified(True, False, valid, []) is False


def test_evidence_maturity_uses_normalized_runtime_authority_not_readiness_booleans(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("capability_evidence_maturity_engine.py")
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.json"
    runtime_csv = tmp_path / "runtime.csv"
    cert_csv = tmp_path / "cert.csv"
    authority = tmp_path / "authority.json"

    registry.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "X-001",
                        "title": {"en": "X"},
                        "domain": "x",
                        "dependencies": [],
                        "maturity": 0,
                        "business_goal": "x",
                        "apis": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "X-001",
                        "tests": [],
                        "backend": [],
                        "routes": [],
                        "database": [],
                        "events": [],
                        "web": [],
                        "mobile": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    runtime_csv.write_text(
        "id,metrics,traces,receipts,audit_events,runtime_surfaces,production_certified\n"
        "X-001,0,0,0,0,0,false\n",
        encoding="utf-8",
    )
    # Deliberately green old readiness booleans: they must not grant runtime truth.
    cert_csv.write_text(
        "id,runtime_proof,eligible_for_certification,certified\nX-001,true,true,false\n",
        encoding="utf-8",
    )
    authority.write_text(
        json.dumps({"capabilities": [{"id": "X-001", "runtime_authority_verified": False}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "REGISTRY", registry)
    monkeypatch.setattr(mod, "MAPPING", mapping)
    monkeypatch.setattr(mod, "RUNTIME_CSV", runtime_csv)
    monkeypatch.setattr(mod, "CERT_CSV", cert_csv)
    monkeypatch.setattr(mod, "RUNTIME_AUTHORITY", authority)

    matrix = json.loads(mod.build()["capability_evidence_matrix.json"])
    assert matrix["capabilities"][0]["runtime_verified"] is False

    authority.write_text(
        json.dumps({"capabilities": [{"id": "X-001", "runtime_authority_verified": True}]}),
        encoding="utf-8",
    )
    matrix = json.loads(mod.build()["capability_evidence_matrix.json"])
    assert matrix["capabilities"][0]["runtime_verified"] is True


def _minimal_mapping_payload() -> dict:
    dimensions = ["backend", "routes", "database", "events", "web", "mobile", "tests", "governance"]
    cap = {
        "capability_id": "X-001",
        "domain": "x",
        "title": "X",
        "mapped": False,
        "coverage_dimensions": 0,
        **{key: [] for key in dimensions},
    }
    return {
        "summary": {
            "capabilities_total": 1,
            "capabilities_mapped": 0,
            "capabilities_unmapped": 1,
            "capabilities_multidimensional": 0,
            "files_scanned": 0,
            "files_by_kind": {},
            "unmapped_artifacts": 0,
            "ambiguous_artifacts": 0,
        },
        "capabilities": [cap],
        "unmapped_artifacts": [],
        "ambiguous_artifacts": [],
    }


@pytest.mark.parametrize(
    "artifact",
    [
        "capability_mapping.json",
        "capability_mapping.csv",
        "unmapped_artifacts.json",
        "ambiguous_artifacts.json",
        "CAPABILITY_MAPPING_REPORT.md",
        "mapping_manifest.json",
    ],
)
def test_mapping_check_covers_csv_report_queues_and_manifest(
    tmp_path: Path, monkeypatch, artifact: str
) -> None:
    mod = load_script("capability_mapping_engine.py")
    payload = _minimal_mapping_payload()
    mod.write_outputs(payload, tmp_path)
    monkeypatch.setattr(mod, "OUT", tmp_path)
    assert mod.check_outputs(payload) is True
    (tmp_path / artifact).write_text("corrupt\n", encoding="utf-8")
    assert mod.check_outputs(payload) is False


@pytest.mark.parametrize(
    "artifact",
    [
        "capability_management_matrix.json",
        "capability_management_matrix.csv",
        "capability_knowledge_graph.json",
        "capability_knowledge_graph.dot",
        "coverage_dashboard.json",
        "CAPABILITY_HEAT_MAP.md",
        "management_manifest.json",
    ],
)
def test_management_check_covers_companion_files_and_manifest(
    tmp_path: Path, monkeypatch, artifact: str
) -> None:
    mod = load_script("capability_management_engine.py")
    matrix: list[dict] = []
    graph = {"schema_version": mod.SCHEMA_VERSION, "nodes": [], "edges": []}
    dashboard = {"domains": []}
    mod.write_all(matrix, graph, dashboard, tmp_path)
    monkeypatch.setattr(mod, "OUT", tmp_path)
    assert mod.generated_drift(matrix, graph, dashboard) == []
    (tmp_path / artifact).write_text("corrupt\n", encoding="utf-8")
    assert artifact in mod.generated_drift(matrix, graph, dashboard)


def test_generated_pipeline_orders_runtime_authority_before_evidence_maturity() -> None:
    mod = load_script("verify_all_generated.py")
    runtime = ("scripts/ci/runtime_certification_gate.py", ["--check"])
    evidence = ("scripts/ci/capability_evidence_maturity_engine.py", ["--check"])
    assert mod._sort_key(runtime) < mod._sort_key(evidence)


# ── A′-1: additive evidence schema — L5 alone is never sufficient for promotion ──


def test_promotion_policy_declares_l5_alone_insufficient() -> None:
    policy = json.loads(
        (ROOT / "docs/capability-registry/field_authority_policy.json").read_text(encoding="utf-8")
    )
    promotion = policy["promotion_preconditions"]
    assert promotion["l5_alone_sufficient"] is False
    assert promotion["execution_outcome_schema"] == "sahool.execution-outcome/v1"
    assert "execution_outcome" in promotion["runtime_verified"]
    assert "subject_sha_binding" in promotion["runtime_verified"]
    assert "evidence_level_5_necessary_not_sufficient" in promotion["production_certified"]


def _ledger_for(receipt: dict, **extra) -> dict:
    return {
        "application_id": receipt["application_id"],
        "candidate_id": receipt["candidate_id"],
        "approval_run_id": receipt["approval_run_id"],
        "target_sha": receipt["target_sha"],
        "environment_id": receipt["environment_id"],
        "capabilities": ["X-001"],
        **extra,
    }


def test_a_receipt_without_execution_outcome_never_satisfies_promotion(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("runtime_certification_gate.py")
    monkeypatch.setattr(mod, "APPLY_LEDGER_DIR", tmp_path)
    receipt = _attested_receipt()
    ledger = _ledger_for(receipt, applied_to_head=receipt["target_sha"])
    (tmp_path / f"{receipt['application_id']}.json").write_text(
        json.dumps(ledger), encoding="utf-8"
    )
    verdict = mod.receipt_assurance([receipt])
    assert verdict["execution_outcome_satisfied"] is False
    assert verdict["subject_sha_binding_satisfied"] is True
    assert "execution_outcome_missing_or_unbound" in verdict["blocking_reasons"]
    empty = mod.receipt_assurance([])
    assert empty["execution_outcome_satisfied"] is False
    assert empty["subject_sha_binding_satisfied"] is False
    assert empty["blocking_reasons"] == ["no_governed_runtime_receipt"]


def test_an_execution_outcome_bound_to_a_foreign_subject_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("runtime_certification_gate.py")
    monkeypatch.setattr(mod, "APPLY_LEDGER_DIR", tmp_path)
    receipt = _attested_receipt()
    outcome = {
        "schema": "sahool.execution-outcome/v1",
        "conclusion": "success",
        "subject_sha": "f" * 40,
    }
    ledger = _ledger_for(receipt, applied_to_head=receipt["target_sha"], execution_outcome=outcome)
    (tmp_path / f"{receipt['application_id']}.json").write_text(
        json.dumps(ledger), encoding="utf-8"
    )
    verdict = mod.receipt_assurance([receipt])
    assert verdict["execution_outcome_satisfied"] is False
    assert "execution_outcome_missing_or_unbound" in verdict["blocking_reasons"]

    outcome["subject_sha"] = receipt["target_sha"]
    (tmp_path / f"{receipt['application_id']}.json").write_text(
        json.dumps(ledger), encoding="utf-8"
    )
    verdict = mod.receipt_assurance([receipt])
    assert verdict["execution_outcome_satisfied"] is True
    assert verdict["subject_sha_binding_satisfied"] is True
    assert verdict["blocking_reasons"] == []


def test_an_unbound_target_sha_breaks_subject_binding_even_with_an_outcome(
    tmp_path: Path, monkeypatch
) -> None:
    mod = load_script("runtime_certification_gate.py")
    monkeypatch.setattr(mod, "APPLY_LEDGER_DIR", tmp_path)
    receipt = _attested_receipt()
    outcome = {
        "schema": "sahool.execution-outcome/v1",
        "conclusion": "success",
        "subject_sha": receipt["target_sha"],
    }
    ledger = _ledger_for(receipt, applied_to_head="e" * 40, execution_outcome=outcome)
    (tmp_path / f"{receipt['application_id']}.json").write_text(
        json.dumps(ledger), encoding="utf-8"
    )
    verdict = mod.receipt_assurance([receipt])
    assert verdict["subject_sha_binding_satisfied"] is False
    assert "subject_sha_binding_unproven" in verdict["blocking_reasons"]


def _maturity_fixture(tmp_path: Path, monkeypatch, authority_row: dict) -> object:
    mod = load_script("capability_evidence_maturity_engine.py")
    registry = tmp_path / "registry.json"
    mapping = tmp_path / "mapping.json"
    runtime_csv = tmp_path / "runtime.csv"
    cert_csv = tmp_path / "cert.csv"
    authority = tmp_path / "authority.json"
    registry.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "X-001",
                        "title": {"en": "X"},
                        "domain": "x",
                        "dependencies": [],
                        "maturity": 0,
                        "evidence_level": 5,
                        "business_goal": "x",
                        "apis": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "capability_id": "X-001",
                        "tests": [],
                        "backend": [],
                        "routes": [],
                        "database": [],
                        "events": [],
                        "web": [],
                        "mobile": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    runtime_csv.write_text(
        "id,metrics,traces,receipts,audit_events,runtime_surfaces,production_certified\n"
        "X-001,0,0,0,0,0,false\n",
        encoding="utf-8",
    )
    cert_csv.write_text(
        "id,runtime_proof,eligible_for_certification,certified\nX-001,true,true,false\n",
        encoding="utf-8",
    )
    authority.write_text(
        json.dumps({"capabilities": [dict(authority_row, id="X-001")]}), encoding="utf-8"
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "REGISTRY", registry)
    monkeypatch.setattr(mod, "MAPPING", mapping)
    monkeypatch.setattr(mod, "RUNTIME_CSV", runtime_csv)
    monkeypatch.setattr(mod, "CERT_CSV", cert_csv)
    monkeypatch.setattr(mod, "RUNTIME_AUTHORITY", authority)
    return mod


def test_evidence_maturity_binds_promotion_to_preconditions_not_authority_alone(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _maturity_fixture(
        tmp_path,
        monkeypatch,
        {
            "runtime_authority_verified": True,
            "execution_outcome_satisfied": False,
            "subject_sha_binding_satisfied": True,
            "promotion_preconditions_satisfied": False,
            "promotion_blocking_reasons": ["execution_outcome_missing_or_unbound"],
        },
    )
    record = json.loads(mod.build()["capability_evidence_matrix.json"])["capabilities"][0]
    assert record["runtime_verified"] is True
    assert record["evidence"]["runtime"] is False
    assert record["promotion_preconditions_satisfied"] is False
    assert "execution_outcome_missing_or_unbound" in record["blocking_reasons"]
    assert (
        "evidence_level_5_declared_without_execution_outcome_binding" in record["blocking_reasons"]
    )


def test_evidence_maturity_fails_closed_on_an_authority_row_without_precondition_fields(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _maturity_fixture(tmp_path, monkeypatch, {"runtime_authority_verified": True})
    record = json.loads(mod.build()["capability_evidence_matrix.json"])["capabilities"][0]
    assert record["evidence"]["runtime"] is False
    assert record["promotion_preconditions_satisfied"] is False
    assert "promotion_preconditions_unavailable" in record["blocking_reasons"]


def test_additive_records_preserve_all_prior_fields_and_type_their_sources(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _maturity_fixture(tmp_path, monkeypatch, {"runtime_authority_verified": False})
    record = json.loads(mod.build()["capability_evidence_matrix.json"])["capabilities"][0]
    prior_fields = {
        "capability_id",
        "title",
        "domain",
        "declared_maturity",
        "assessed_maturity",
        "maturity_delta",
        "maturity_alignment",
        "evidence",
        "evidence_score",
        "unit_test_paths",
        "integration_test_paths",
        "decision_linked",
        "learning_linked",
        "assessment_reasons",
        "runtime_verified",
        "production_certified",
        "automatic_registry_update",
    }
    assert prior_fields <= set(record)
    assert {r["type"] for r in record["evidence_records"]} == set(record["evidence"])
    assert all(r["source"] for r in record["evidence_records"])
    assurance = record["assurance_records"][0]
    assert assurance["authority"] == "runtime_verification"
    assert assurance["promotion_preconditions_satisfied"] is False
    assert record["field_validation"]["evidence_level"] == "in_enum"
    assert record["field_validation"]["production_certified"] == "false_as_required"


def test_certification_eligibility_requires_outcome_and_binding_beyond_l5() -> None:
    mod = load_script("capability_certification_gate.py")
    cap = {
        "id": "X-001",
        "title": "X",
        "services": ["s"],
        "apis": ["a"],
        "tests": ["t"],
        "maturity": 5,
        "evidence_level": 5,
        "production_certified": False,
        "runtime": {
            "metrics": ["m"],
            "traces": ["t"],
            "receipts": ["r"],
            "audit_events": ["a"],
        },
        "evidence": [{"type": "runtime"}, {"type": "production"}],
    }
    without = mod.evaluate(cap, {})
    assert without["gates_passed"] == without["gates_total"]
    assert without["execution_outcome"] is False
    assert without["eligible_for_certification"] is False
    with_preconditions = mod.evaluate(
        cap,
        {
            "X-001": {
                "execution_outcome_satisfied": True,
                "subject_sha_binding_satisfied": True,
            }
        },
    )
    assert with_preconditions["eligible_for_certification"] is True
