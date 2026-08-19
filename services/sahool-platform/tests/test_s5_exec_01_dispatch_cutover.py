from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "services/sahool-platform/api/routers/decision_dispatch.py"


def test_legacy_dispatch_writer_is_retired_before_any_platform_db_access_after_cutover():
    t = P.read_text()
    s = t.index('@router.post("/api/v1/decision/dispatch/execute")')
    e = t.index('@router.post("/api/v1/decision/dispatch/consume")', s)
    b = t[s:e]
    gate = b.index("if mode.strict_decision_service_required:")
    db = b.index("async with tenant_connection(user) as conn:")
    assert gate < db
    cut = b[gate:db]
    assert "status_code=409" in cut
    assert "legacy_dispatch_writer_retired_after_decision_sor_cutover" in cut
    assert (
        "execution-plan" in cut and "dispatch-authorization" in cut and "execution-request" in cut
    )
    assert "INSERT INTO dispatch_decisions" not in cut


def test_pre_cutover_dispatch_writer_remains_guarded():
    t = P.read_text()
    s = t.index('@router.post("/api/v1/decision/dispatch/execute")')
    e = t.index('@router.post("/api/v1/decision/dispatch/consume")', s)
    b = t[s:e]
    assert 'assert_platform_may_write_decision_sor("dispatch_decisions")' in b
    assert "INSERT INTO dispatch_decisions" in b
