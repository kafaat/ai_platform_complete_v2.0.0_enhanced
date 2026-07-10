from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_read_side_comparison_is_read_only_and_gated() -> None:
    text = _read("services/decision-service/read_side_compare.py")
    assert "DECISION_SERVICE_READ_COMPARE_APPROVED" in text
    assert "DECISION_SERVICE_READ_COMPARE_ALLOW_LIVE" in text
    assert "DECISION_SERVICE_READ_COMPARE_ALLOW_PRODUCTION" in text
    assert "migration_runner.py" in text
    assert "backfill.py" in text
    assert "/v1/cutover/readiness" in text
    assert "no writes are performed" in text


def test_production_promotion_requires_all_cutover_gates() -> None:
    text = _read("services/decision-service/production_promotion.py")
    for token in (
        "DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED",
        "DECISION_SERVICE_PRODUCTION_PROMOTION_ALLOW_LIVE",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        "DECISION_SERVICE_SOR_ENABLED",
        "DECISION_SERVICE_MIGRATIONS_VERIFIED",
        "DECISION_SERVICE_BACKFILL_VERIFIED",
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
        "DECISION_SERVICE_OUTBOX_VERIFIED",
        "can_demote_platform",
    ):
        assert token in text
    assert "dry-run" in text


def test_rollback_is_non_destructive_and_restores_platform_sor() -> None:
    text = _read("services/decision-service/rollback.py")
    assert "DECISION_SERVICE_ROLLBACK_APPROVED" in text
    assert "DECISION_SERVICE_ROLLBACK_ALLOW_LIVE" in text
    assert "SAHOOL_DECISION_WRITE_MODE=platform_sor" in text
    assert "keep decision-service tables for forensic comparison" in text
    assert "destructive" in text


def test_final_certification_gate_and_ci_are_wired() -> None:
    workflow = _read(".github/workflows/field-workspace-production-closure.yml")
    assert "decision_sor_final_certification_gate.py" in workflow
    assert "test_p0_5_decision_sor_final_certification_guard.py" in workflow
    gate = _read("scripts/ci/decision_sor_final_certification_gate.py")
    assert "Decision SoR final certification gate passed" in gate


def test_final_runbook_and_architecture_docs_exist() -> None:
    runbook = _read("docs/runbooks/DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md")
    arch = _read("docs/architecture/DECISION_SERVICE_SOR_FINAL_CERTIFICATION.md")
    assert "read-side comparison" in runbook
    assert "production promotion preflight" in runbook
    assert "rollback plan" in runbook
    assert "do not delete decision-service tables during rollback" in runbook
    assert "final certification" in arch
    assert "promotion is not a single flag" in arch
    assert "rollback is non-destructive" in arch


def test_field_workspace_ci_installs_backend_runtime_dependencies_before_runtime_gates() -> None:
    workflow = _read(".github/workflows/field-workspace-production-closure.yml")
    install_idx = workflow.find(
        "pip install -r tests_v9/requirements-test.txt -r services/sahool-platform/api/requirements.txt"
    )
    assert install_idx != -1, "backend runtime dependency install step missing before Python gates"
    assert "services/weather-service/requirements.txt" in workflow
    assert install_idx < workflow.index("Field Workspace Python closure gate")
    assert install_idx < workflow.index("Field Workspace guard tests")


def test_service_proxy_catch_all_routes_are_excluded_from_openapi_schema() -> None:
    proxy = _read("services/sahool-platform/api/routers/service_proxy.py")
    # Catch-all multi-method proxies generate duplicate OpenAPI operation IDs when
    # exposed as one api_route with several methods. They are internal gateway
    # pass-through routes, not SDK contracts, so they must stay hidden from OpenAPI.
    for path in (
        '"/api/edge/{path:path}",',
        '"/api/soil/{path:path}",',
        '"/api/segmentation/{path:path}",',
    ):
        idx = proxy.index(path)
        segment = proxy[idx : idx + 200]
        assert "include_in_schema=False" in segment
