from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "migrations/v207_historical_season_simulation_bridge.sql"
MANIFEST = ROOT / "migrations/MANIFEST.txt"
ROUTER = ROOT / "services/sahool-platform/api/routers/seasons.py"
COMPOSER = ROOT / "services/sahool-platform/core/historical_season_context.py"


def _entries() -> list[str]:
    return [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip().endswith(".sql")
    ]


def test_bridge_runs_before_final_rls_catalog_assertion():
    entries = _entries()
    # v206 (final RLS catalog hardening) MUST stay last; every season-bridge
    # migration (v207 tables, v208 sim_run lineage ALTER) runs before it.
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries.index(MIGRATION.name) < entries.index("v206_rls_final_hardening.sql")
    assert entries.index("v208_seasons_sim_run_lineage.sql") < entries.index(
        "v206_rls_final_hardening.sql"
    )


def test_bridge_is_tenant_bound_append_only_and_validates_accepted_ownership():
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("season_record_links", "season_simulation_runs"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
        assert f"trg_{table}_append_only" in sql
    assert "trust_status <> 'accepted'" in sql
    assert "tenant/field ownership mismatch" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "sahool_effective_tenant_id()" in sql


def test_existing_simulation_route_uses_composer_and_ledger_no_parallel_endpoint():
    src = ROUTER.read_text(encoding="utf-8")
    assert src.count('@router.post("/api/v1/seasons/{season_id}/simulate"') == 1
    assert "compose_historical_season_context" in src
    assert "season_simulation_runs" in src
    assert "observed_fapar=composed_inputs" in src
    assert "irrigation_mm_total=composed_inputs" in src
    assert "compose_context_snapshot" in src
    assert '"features": []' in src
    assert "HISTORICAL_SEASON_DECISION_CONTEXT_ENABLED" in src
    assert '"0"' in src


def test_composer_forbids_silent_irrigation_and_daily_fapar_invention():
    src = COMPOSER.read_text(encoding="utf-8")
    assert 'e.get("amount_mm") is not None' in src
    assert 'not bool(e.get("low_confidence"))' in src
    assert '"no_daily_fapar_interpolation": True' in src
    assert "from api.season_simulation import fapar_from_ndvi" in src
    assert "1.24 *" not in src


def test_decision_snapshot_carries_simulation_outcome_and_engine_identity():
    """The decision-center mirror must expose the run's outcome, not inputs only.

    Guards HISTORICAL-SEASON-COMPOSITION-02 slice 1: engine identity + prediction
    band + expected-vs-actual delta reach the snapshot; the composer never invents
    an actual yield.
    """
    composer = COMPOSER.read_text(encoding="utf-8")
    assert "def build_simulation_outcome(" in composer
    assert '"expected_vs_actual"' in composer
    assert '"no_actual_yield"' in composer  # absence is explicit, not invented

    router = ROUTER.read_text(encoding="utf-8")
    assert "build_simulation_outcome(" in router
    assert '"simulation": simulation_outcome' in router


V208 = ROOT / "migrations/v208_seasons_sim_run_lineage.sql"
MODELS = ROOT / "services/sahool-platform/api/season_models.py"


def test_sim_projection_is_bound_to_the_run_ledger_by_run_id():
    """HISTORICAL-SEASON-COMPOSITION-02 slice: seasons.sim_* carries sim_run_id so
    the latest projection can never lose its lineage to season_simulation_runs.
    """
    v208 = V208.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS sim_run_id UUID" in v208

    router = ROUTER.read_text(encoding="utf-8")
    # The run row is inserted first, then the projection UPDATE binds its run_id.
    assert "sim_run_id = $8 WHERE season_id = $1" in router
    assert router.index("INSERT INTO season_simulation_runs") < router.index("sim_run_id = $8")


def test_response_declares_actual_run_engine_not_only_canonical_target():
    """The response must not pair yield with canonical_yield_engine alone: it states
    the engine that actually produced the yield (rue-fao56) vs the canonical target.
    """
    models = MODELS.read_text(encoding="utf-8")
    assert 'simulation_engine: str = "rue-fao56"' in models
    assert 'canonical_yield_engine: str = "pcse_wofost"' in models

    router = ROUTER.read_text(encoding="utf-8")
    assert "simulation_engine=ENGINE_NAME" in router
