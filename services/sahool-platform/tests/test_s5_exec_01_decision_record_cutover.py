from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "services/sahool-platform/api/routers/decision_record.py"


def _body():
    t = P.read_text()
    s = t.index('@router.post("/api/v1/decision/record")')
    e = t.index("\n\nclass OutcomePlannedIn", s)
    return t[s:e]


def test_authoritative_cutover_branch_has_no_platform_db_write():
    b = _body()
    s = b.index("if mode.strict_decision_service_required:")
    e = b.index("    try:", s)
    cut = b[s:e]
    assert "tenant_connection" not in cut
    assert "INSERT INTO decision_record" not in cut
    assert "await _mirror_decision_to_service" in cut
    assert "authoritative" in cut and "persisted" in cut
    assert 'authoritative_store": "decision-service"' in cut


def test_pre_cutover_path_keeps_guarded_platform_authority_and_mirror():
    b = _body()
    pre = b[b.index("    try:") :]
    assert "tenant_connection" in pre
    assert "INSERT INTO decision_record" in pre
    assert 'assert_platform_may_write_decision_sor("decision_record")' in pre
    assert "await _mirror_to_decision_service" in pre
    assert "service_payload" in pre
