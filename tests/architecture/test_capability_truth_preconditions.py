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
