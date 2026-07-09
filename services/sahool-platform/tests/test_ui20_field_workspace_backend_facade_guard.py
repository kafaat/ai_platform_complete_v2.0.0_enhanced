from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "services" / "sahool-platform"
FRONTEND = ROOT / "frontend" / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_priority_queue_backend_facade_exists_for_field_and_farm():
    router = read(BACKEND / "api" / "routers" / "field_priority_queue.py")
    assert "/api/v1/fields/{field_id}/priority-queue" in router
    assert "/api/v1/farms/{farm_id}/priority-queue" in router
    assert 'scope": "field"' in router or 'scope": "field"' in router
    assert 'scope": "farm"' in router or 'scope": "farm"' in router
    assert "require_permission(Permission.FIELD_VIEW)" in router


def test_priority_queue_facade_does_not_fabricate_items():
    router = read(BACKEND / "api" / "routers" / "field_priority_queue.py")
    assert "لا تُصنَّع أولويات" in router or "لا توجد عناصر مصطنعة" in router
    assert "alerts" in router
    assert "field_tasks" in router
    assert "items.extend(_shape_alert" in router
    assert "items.extend(_shape_task" in router
    assert "mock" not in router.lower()
    assert "placeholder" not in router.lower()


def test_priority_queue_facade_degrades_on_optional_source_failure():
    router = read(BACKEND / "api" / "routers" / "field_priority_queue.py")
    assert "degraded" in router
    assert "warning_ar" in router
    assert "_optional_fetch" in router
    assert "تعذّر قراءة مصدر اختياري" in router
    # Ownership checks remain hard failures rather than degraded visibility leaks.
    assert "_assert_field_in_tenant" in router
    assert "_assert_farm_in_tenant" in router


def test_field_workspace_frontend_contract_has_backend_counterparts():
    api = read(FRONTEND / "services" / "api" / "fieldOperating.ts")
    backend_files = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [
            BACKEND / "api" / "routers" / "field_readiness.py",
            BACKEND / "api" / "routers" / "field_completeness.py",
            BACKEND / "api" / "routers" / "fields.py",
            BACKEND / "api" / "routers" / "field_priority_queue.py",
            # UI28-30 cleanup: unified-timeline relocated here from fields.py.
            BACKEND / "api" / "routers" / "field_workspace_timeline.py",
        ]
    )
    for path in [
        "/api/v1/fields/{field_id}/readiness",
        "/api/v1/fields/{field_id}/data-completeness",
        "/api/v1/fields/{field_id}/unified-timeline",
        "/api/v1/fields/{field_id}/priority-queue",
        "/api/v1/farms/{farm_id}/priority-queue",
    ]:
        assert path in backend_files
    assert "/api/v1/fields/${fieldId}/priority-queue" in api
    assert "/api/v1/farms/${farmId}/priority-queue" in api


def test_router_autoregister_will_pick_up_priority_queue_router():
    registry = read(BACKEND / "api" / "router_registry.py")
    router = read(BACKEND / "api" / "routers" / "field_priority_queue.py")
    assert "pkgutil.iter_modules" in registry
    assert "ROUTER_AUTOREG_EXCLUDE" in registry
    assert "service_proxy" in registry
    assert "router = APIRouter()" in router
