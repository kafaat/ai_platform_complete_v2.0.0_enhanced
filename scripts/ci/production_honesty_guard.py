#!/usr/bin/env python3
"""Production honesty guard.

Prevents regression from honest fail-closed services back to mock/stub/fabricated
outputs on production routes. Test files are ignored; explicit 501 or degraded
health-only boundaries are allowed.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE = ROOT / "services" / "edge-inference"
INDICATORS = ROOT / "services" / "indicators-service"
COMPOSE = ROOT / "docker-compose.v9.yml"
MEMORY_EXPORT = ROOT / "shared" / "memory" / "export_engine.py"
MIGRATE = ROOT / "migrations" / "apply_in_compose.sh"
BOOTSTRAP = ROOT / "migrations" / "bootstrap_postgres.sh"
CERT_WORKFLOW = ROOT / ".github" / "workflows" / "production-certification-blockers.yml"


def fail(msg: str) -> None:
    raise SystemExit("✗ " + msg)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_edge_download_does_not_claim_simulation_fallback() -> None:
    source = text(EDGE / "download_models.py").lower()
    forbidden = [
        "simulation mode",
        '"fallback": "simulation"',
        "will use simulation",
        '"fallback": "regression"',
    ]
    found = [item for item in forbidden if item in source]
    if found:
        fail("edge model downloader still advertises fabricated fallback modes: " + repr(found))


def check_edge_predict_fail_closed_before_simulation() -> None:
    source_path = EDGE / "models" / "pest_detector.py"
    tree = ast.parse(text(source_path))
    predict_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "predict":
            predict_node = node
            break
    if predict_node is None:
        fail("EdgePestDetector.predict missing")
    calls = []
    raises_model_not_provisioned = False
    for node in ast.walk(predict_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.append(node.func.id)
        if isinstance(node, ast.Raise) and node.exc is not None:
            rendered = ast.unparse(node.exc)
            if "ModelNotProvisioned" in rendered:
                raises_model_not_provisioned = True
    if "_simulate_detection" in calls:
        fail("EdgePestDetector.predict calls _simulate_detection on production path")
    if not raises_model_not_provisioned:
        fail("EdgePestDetector.predict must raise ModelNotProvisioned when model is absent")


def check_indicators_contract_boundary_is_honest() -> None:
    source = text(INDICATORS / "main.py")
    required = [
        '"status": "ready"',
        '"implemented_runtime": True',
        # RS2/RS3 cutover: the service is now the canonical-observation adapter
        # (reads observations from raster-service), not a passive contract-only
        # stub. The honest role marker moved accordingly; spectral compute is
        # still disowned (409) and never simulated here.
        '"runtime_role": "canonical-observation-adapter"',
        '"spectral_compute": False',
        "status_code=409",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        fail("indicators-service contract boundary missing honesty markers: " + repr(missing))
    forbidden = ['"health_only": True', '"implemented_runtime": False', "status_code=501"]
    present = [item for item in forbidden if item in source]
    if present:
        fail("indicators-service retains stale health-only markers: " + repr(present))


def check_gap_hardening_contracts() -> None:
    compose = text(COMPOSE)
    migration_text = text(MIGRATE) + text(BOOTSTRAP)
    if "sahool_ingest_pw" in compose + migration_text:
        fail("known development ingest password remains reachable")
    required_compose = [
        "INGEST_DB_PASSWORD:?INGEST_DB_PASSWORD required",
        "SCOUT_INGEST_S3_ACCESS_KEY:?SCOUT_INGEST_S3_ACCESS_KEY required",
        "RASTER_S3_ACCESS_KEY:?RASTER_S3_ACCESS_KEY required",
        "FIELD_SERVICE_ALLOWED_CALLERS",
        "FIELD_SERVICE_TENANT_ASSERTION_KEY:?FIELD_SERVICE_TENANT_ASSERTION_KEY required",
    ]
    missing = [item for item in required_compose if item not in compose]
    if missing:
        fail("production compose missing fail-closed hardening: " + repr(missing))

    memory_export = text(MEMORY_EXPORT)
    for marker in ("class VectorExportUnavailable", "if include_vectors:", "vectors_included"):
        if marker not in memory_export:
            fail("memory export can regress to a misleading vector backup: " + marker)
    if 'payload["vectors"] = []' in memory_export:
        fail("memory export still fabricates an empty vector backup")

    field_service = text(ROOT / "services" / "field-management-service" / "main.py")
    vegetation = text(ROOT / "services" / "vegetation-analysis-service" / "vegetation_runtime.py")
    for marker in ("X-Tenant-Assertion", "verify_tenant_assertion"):
        if marker not in field_service:
            fail("field tenant binding is not assertion-verified: " + marker)
    for marker in ("X-Tenant-Assertion", "create_tenant_assertion"):
        if marker not in vegetation:
            fail("vegetation caller is not assertion-bound: " + marker)

    cert = text(CERT_WORKFLOW)
    if "certification-verdict:" not in cert or "--require-certified" not in cert:
        fail("production certification workflow lacks an enforcing aggregate verdict")
    if "redis_live_evidence_skipped_secret_missing\n            exit 0" in cert:
        fail("Redis evidence job can still pass while evidence is missing")

    season_models = text(ROOT / "services/sahool-platform/api/season_models.py")
    season_router = text(ROOT / "services/sahool-platform/api/routers/seasons.py")
    required_sim = ("screening_only", "eligible_for_calibration", "pcse_wofost")
    missing_sim = [m for m in required_sim if m not in season_models or m not in season_router]
    if missing_sim:
        fail("lightweight season simulation can compete with canonical yield truth: " + repr(missing_sim))


def main() -> None:
    check_edge_download_does_not_claim_simulation_fallback()
    check_edge_predict_fail_closed_before_simulation()
    check_indicators_contract_boundary_is_honest()
    check_gap_hardening_contracts()
    print("✓ production honesty guard passed")


if __name__ == "__main__":
    main()
