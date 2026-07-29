import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/sahool-platform"))

from api.offline_sync_contracts import (  # noqa: E402
    FIELD_UPDATE_KIND,
    build_sync_manifest,
    normalize_offline_operation,
    summarize_sync_status,
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_normalize_preserves_mobile_operation_id_for_cross_request_idempotency():
    op = normalize_offline_operation(
        {
            "operation_id": "00000000-0000-7000-8000-000000000112",
            "kind": "observation_create",
            "payload": {"field_id": "f1"},
        }
    )
    assert op["op_id"] == "00000000-0000-7000-8000-000000000112"
    assert op["kind"] == "observation_create"
    assert op["payload"]["field_id"] == "f1"


def test_field_update_contract_is_conflict_aware_without_direct_overwrite():
    op = normalize_offline_operation(
        {
            "op_id": "00000000-0000-7000-8000-000000000113",
            "kind": FIELD_UPDATE_KIND,
            "payload": {
                "field_id": "11111111-1111-4111-8111-111111111111",
                "base_version": 7,
                "name": "A",
            },
        }
    )
    assert op["conflict_policy"] == "optimistic_row_version"
    assert op["requires_conflict_resolution"] is True
    assert op["has_base_version"] is True


def test_sync_manifest_exposes_supported_kinds_and_status_endpoint():
    manifest = build_sync_manifest()
    assert "field.update" in manifest["supported_operation_kinds"]
    assert manifest["stable_operation_id"]["format"] == "uuid"
    assert manifest["status_endpoint"] == "/api/v1/sync/status"
    assert manifest["dispatch"]["field.update"]["conflict_policy"] == "optimistic_row_version"


def test_sync_router_preserves_client_op_id_and_exposes_manifest_status():
    body = read("services/sahool-platform/api/routers/sync.py")
    assert '@router.get("/api/v1/sync/manifest")' in body
    assert '@router.get("/api/v1/sync/status")' in body
    assert "normalize_offline_operation(raw_op)" in body
    assert 'if normalized.get("op_id")' in body
    assert 'op.op_id = normalized["op_id"]' in body


def test_mobile_client_uses_ai_agronomist_and_sync_endpoints():
    body = read("mobile/sahool_app/lib/services/api_service.dart")
    assert "/api/ai-agronomist/chat" in body
    assert "/api/v1/sync/manifest" in body
    assert "/api/v1/sync/status" in body
    assert "syncOfflineOperations" in body
    assert "data: form,\n      data: form" not in body


def test_mobile_sync_smoke_script_is_fail_closed():
    script = ROOT / "scripts/mobile/mobile_sync_smoke.sh"
    body = script.read_text(encoding="utf-8")
    env = os.environ.copy()
    env.pop("SAHOOL_JWT", None)
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert proc.returncode != 0
    assert "SAHOOL_JWT is required" in proc.stdout
    assert "/api/v1/sync/manifest" in body
    assert "/api/v1/sync/status" in body
    assert "00000000-0000-7000-8000-000000000112" in body


def test_v112_migration_is_registered_and_rls_hardened():
    manifest = read("migrations/MANIFEST.txt")
    sql = read("migrations/v112_mobile_offline_sync_runtime.sql")
    assert "v112_mobile_offline_sync_runtime.sql" in manifest
    assert "mobile_sync_clients" in sql
    assert "mobile_sync_conflicts" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "tenant_id::text = current_setting('app.tenant_id', true)" in sql


def test_sync_status_summary_is_bounded_and_ui_safe():
    status = summarize_sync_status(queued=4, queue_size=7, durable_pending=2)
    assert status["healthy_for_sync"] is True
    assert status["queue"]["queued"] == 4
    assert status["queue"]["durable_pending"] == 2
