from pathlib import Path

import pytest

# Without a marker this file runs in NO CI job: pytest.ini scopes testpaths to
# tests_v9 and the gating job selects `-m unit`. An unmarked test is not a weak
# test, it is an absent one.
pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "services/sahool-platform/api/persisted_canonical_repositories.py"
WORKER = ROOT / "scripts/workers/canonical_execution_learning_worker.py"
COMPOSE = ROOT / "docker-compose.v9.yml"
RUNNER = ROOT / "scripts_v9/run_migrations.sql"


def test_projection_events_do_not_mint_fake_command_ids() -> None:
    text = REPO.read_text(encoding="utf-8")
    assert "_projection_command_id" not in text
    assert "uuid5(" not in text
    assert "        None," in text


def test_worker_is_registered_in_compose() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-canonical-execution-learning-worker:" in compose
    assert "/app/scripts/workers/canonical_execution_learning_worker.py" in compose
    assert "CANONICAL_LEARNING_DURABLE" in compose


def test_projection_persistence_has_executable_worker_call_sites() -> None:
    text = WORKER.read_text(encoding="utf-8")
    for name in (
        "persist_phenology_projection",
        "persist_salinity_projection",
        "persist_nutrient_projection",
    ):
        assert text.count(name) >= 2, f"{name} must be imported and called"
    assert "canonical_projection_requests" in text
    assert "agronomy.projection.requested" in text


def test_v227_has_truthful_banner_and_v206_remains_last() -> None:
    lines = RUNNER.read_text(encoding="utf-8").splitlines()
    v227 = lines.index("\\i migrations/v227_decision_learning_runtime.sql")
    v206 = lines.index("\\i migrations/v206_rls_final_hardening.sql")
    assert "v227_decision_learning_runtime.sql" in lines[v227 - 1]
    assert "v206_rls_final_hardening.sql" in lines[v206 - 1]
    assert v227 < v206
    assert not any(line.startswith("\\i migrations/") for line in lines[v206 + 1 :])
