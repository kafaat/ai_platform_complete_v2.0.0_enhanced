"""AgriAI production readiness truth: readyz + docs match the fail-closed behavior."""

from pathlib import Path


def test_readyz_is_not_unconditionally_ready_in_production():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "AGRIAI_PRODUCTION_MODE" in src
    assert "pcse_available" in src
    assert "required_missing" in src


def test_wofost_docs_match_fail_closed_behavior():
    src = (Path(__file__).resolve().parents[1] / "wofost_adapter.py").read_text()
    assert "فشل مُغلَق" in src
    assert "لا ننهار أبداً" not in src
    assert "agriai_production_simulation_unavailable" in src
