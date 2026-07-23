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
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries.index(MIGRATION.name) == len(entries) - 2


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
