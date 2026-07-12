from pathlib import Path


def test_phase9_10_strengthening_migration_registered():
    manifest = Path("migrations/MANIFEST.txt").read_text()
    assert "v106_phase9_10_runtime_strengthening.sql" in manifest
    sql = Path("migrations/v106_phase9_10_runtime_strengthening.sql").read_text()
    assert "runtime_event_outbox" in sql
    assert "online_feature_values" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "WITH CHECK" in sql


def test_phase9_api_persists_feature_batch_and_event():
    src = Path("services/sahool-platform/api/phase9_autonomous_farm_os.py").read_text()
    assert "persist_phase9_feature_batch" in src
    assert "persist_runtime_event" in src
    assert "phase9.autonomy_cycle.completed" in src


def test_phase10_api_persists_learning_outputs_and_records():
    src = Path("services/sahool-platform/api/phase10_continuous_learning.py").read_text()
    assert "persist_phase10_learning_outputs" in src
    assert 'ds["records"] = req.records' in src
    assert "async def learning_cycle" in src


def test_runtime_store_sets_rls_context_before_tenant_writes():
    src = Path("services/sahool-platform/api/phase_runtime_store.py").read_text()
    assert "set_config('app.tenant_id'" in src
    assert "runtime_event_outbox" in src
    assert "online_feature_values" in src
