from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "migrations/v205_irrigation_reservation_runtime_hardening.sql").read_text()
RELAY = (ROOT / "services/sahool-platform/api/irrigation_dispatch_relay_worker.py").read_text()
RESOLVER = (ROOT / "services/sahool-platform/api/irrigation_authoritative_resolver.py").read_text()


def test_project_coherent_fks():
    assert "fk_reservation_node_project" in SQL
    assert "(resource_node_id, project_id, tenant_id)" in SQL
    assert "fk_target_binding_node_project" in SQL


def test_exclusive_overlap_db_invariant():
    assert "EXCLUDE USING gist" in SQL
    assert "resource_policy = 'exclusive'" in SQL


def test_immutable_truths_and_legal_lifecycle():
    assert "trg_capacity_evaluations_immutable" in SQL
    assert "trg_target_binding_immutable_identity" in SQL
    assert "transition_irrigation_reservation" in SQL
    assert "r.state='reserved' AND p_target_state IN ('active','expired','cancelled')" in SQL


def test_authoritative_resolver_derives_not_accepts_resources():
    assert "irrigation_target_bindings" in RESOLVER
    assert "canonical_hydraulic_capabilities" in RESOLVER
    assert "_POLICY_BY_NODE" in RESOLVER
    assert (
        "resources:"
        not in RESOLVER.split("async def resolve_authoritative_intent", 1)[1].split(")", 1)[0]
    )


def test_relay_default_post_preserves_status():
    assert "return response.status_code, payload" in RELAY
    assert "return await decision_post_json" not in RELAY
