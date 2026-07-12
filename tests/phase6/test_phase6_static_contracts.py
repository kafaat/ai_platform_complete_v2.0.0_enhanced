from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase6_migration_registered_and_rls_protected():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text()
    assert "v108_phase10_feature_store_model_registry_runtime.sql" in manifest
    sql = (
        ROOT / "migrations" / "v108_phase10_feature_store_model_registry_runtime.sql"
    ).read_text()
    for table in [
        "feature_definitions_runtime",
        "feature_set_versions_runtime",
        "offline_dataset_versions_runtime",
        "model_versions_runtime",
        "model_serving_aliases_runtime",
        "model_promotion_history_runtime",
        "model_rollback_history_runtime",
    ]:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql


def test_phase10_api_exposes_feature_store_and_model_registry_runtime_endpoints():
    api = (
        ROOT / "services" / "sahool-platform" / "api" / "phase10_continuous_learning.py"
    ).read_text()
    for route in [
        "/feature-store/register",
        "/feature-store/offline-dataset",
        "/feature-store/online-materialization",
        "/feature-store/point-in-time",
        "/models/register",
        "/models/serving/promote",
        "/models/serving/rollback",
    ]:
        assert route in api


def test_phase10_persistence_adapter_knows_production_runtime_tables():
    adapter = (ROOT / "services" / "sahool-platform" / "api" / "phase_runtime_store.py").read_text()
    for table in [
        "feature_definitions_runtime",
        "offline_dataset_versions_runtime",
        "point_in_time_snapshots_runtime",
        "model_versions_runtime",
        "model_serving_aliases_runtime",
        "model_promotion_history_runtime",
        "model_rollback_history_runtime",
    ]:
        assert table in adapter
