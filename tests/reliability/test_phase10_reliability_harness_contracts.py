from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_load_harness_covers_field_imagery_and_ai_paths():
    script = ROOT / "scripts/load/k6_field_imagery_ai.js"
    runner = ROOT / "scripts/load/run_load_tests.sh"
    assert script.exists(), "k6 field/imagery/AI load script is missing"
    assert runner.exists(), "load test runner is missing"
    body = script.read_text(encoding="utf-8")
    assert "/api/raster/v1/fields/" in body
    assert "/available-dates" in body
    assert "/tilejson" in body
    assert "/api/ai-agronomist/chat" in body
    assert "sahool_tile_latency_ms" in body
    assert "sahool_ai_latency_ms" in body
    assert "http_req_failed" in body


def test_chaos_harness_targets_runtime_dependencies_and_recovery():
    body = read("scripts/chaos/run_chaos_tests.sh")
    for service in [
        "sahool-redis",
        "sahool-nats",
        "sahool-raster-service",
        "sahool-rag-retrieval",
        "sahool-knowledge-graph",
        "sahool-ai-agronomist",
    ]:
        assert service in body
    assert "compose stop" in body
    assert "compose up -d" in body
    assert "runtime_smoke.sh" in body
    assert "outbox_reliability_check.sh" in body
    assert "e2e_field_imagery_ai.sh" in body


def test_recovery_smoke_checks_gateway_and_versioned_tilejson():
    body = read("scripts/recovery/recovery_smoke.sh")
    for path in [
        "/api/raster/healthz",
        "/api/rag/healthz",
        "/api/knowledge-graph/healthz",
        "/api/ai-agronomist/healthz",
        "/available-dates",
        "/tilejson?index=",
        "v=recovery",
    ]:
        assert path in body


def test_load_runner_is_fail_closed_when_required_context_missing():
    body = read("scripts/load/run_load_tests.sh")
    assert "FIELD_ID and TENANT_ID are required" in body
    assert "exit 2" in body
    assert "k6 is required" in body
    assert "exit 127" in body


def test_existing_phase3_runtime_scripts_are_still_present():
    for path in [
        "scripts/check_gateway_routes.sh",
        "scripts/runtime_smoke.sh",
        "scripts/e2e/e2e_field_imagery_ai.sh",
        "scripts/security_audit.sh",
        "scripts/observability_smoke.sh",
        "scripts/outbox_reliability_check.sh",
    ]:
        assert (ROOT / path).exists(), f"{path} was removed"
