from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_soak_scenario_scales_to_required_minimums():
    mod = load("soak_scenario", "scripts/soak/soak_scenario.py")
    scenario = mod.build_scenario(1000, 100000, 7)
    assert scenario.tenants == 1000
    assert scenario.fields == 100000
    assert scenario.duration_days == 7
    assert scenario.chaos_interval_minutes == 120


def test_soak_assertions_fail_on_fake_fallbacks():
    mod = load("soak_assertions", "scripts/soak/soak_assertions.py")
    ok, failures = mod.evaluate({"ai_fake_fallbacks": 1, "worker_recovery_rate": 1})
    assert not ok
    assert any("AI fake fallback" in f for f in failures)


def test_soak_assertions_pass_for_clean_metrics():
    mod = load("soak_assertions", "scripts/soak/soak_assertions.py")
    ok, failures = mod.evaluate({
        "http_5xx_rate": 0,
        "outbox_backlog_age_seconds": 0,
        "dead_letters": 0,
        "tile_cache_mismatch": 0,
        "ai_fake_fallbacks": 0,
        "replay_drift": 0,
        "worker_recovery_rate": 1,
    })
    assert ok
    assert failures == []
