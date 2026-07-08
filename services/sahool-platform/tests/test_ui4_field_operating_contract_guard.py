from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_field_operating_api_contract_module_exists_and_is_reexported():
    module = read("frontend/src/services/api/fieldOperating.ts")
    facade = read("frontend/src/services/api.ts")

    assert "getFieldReadiness" in module
    assert "getFieldDataCompleteness" in module
    assert "getFieldUnifiedTimeline" in module
    assert "getFarmPriorityQueue" in module
    assert "getFieldPriorityQueue" in module
    assert "kongApi" in module
    assert "axios.create" not in module
    assert "localhost" not in module
    assert "from './api/fieldOperating'" in facade
    assert "FieldReadinessResponse" in facade
    assert "PriorityQueueResponse" in facade


def test_field_operating_contract_uses_stable_routes():
    module = read("frontend/src/services/api/fieldOperating.ts")
    assert "/api/v1/fields/${fieldId}/readiness" in module
    assert "/api/v1/fields/${fieldId}/data-completeness" in module
    assert "/api/v1/fields/${fieldId}/unified-timeline" in module
    assert "/api/v1/farms/${farmId}/priority-queue" in module
    assert "/api/v1/fields/${fieldId}/priority-queue" in module


def test_backend_field_readiness_facade_is_registered_by_autoreg_and_honest():
    router = read("services/sahool-platform/api/routers/field_readiness.py")
    registry = read("services/sahool-platform/api/router_registry.py")

    assert '@router.get("/api/v1/fields/{field_id}/readiness")' in router
    assert "field_data_completeness" in router
    assert "calibrated" in router and "False" in router
    assert "لا صحة المحصول" in router
    assert "ROUTER_AUTOREG_EXCLUDE" in registry
    assert '"field_readiness"' not in registry  # auto-registered, not excluded
