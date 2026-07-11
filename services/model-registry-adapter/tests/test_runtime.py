import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wxruntime", ROOT / "runtime.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_drift_classification(monkeypatch):
    monkeypatch.setenv("MODEL_DRIFT_FEATURE_WARNING", "0.1")
    assert m.classify_drift({"feature_drift": 0.01}) == "stable"
    assert m.classify_drift({"feature_drift": 0.11}) == "warning"
    assert m.classify_drift({"feature_drift": 0.25}) == "critical"


def test_backoff_is_bounded():
    b = m.Backoff(minimum=1, maximum=4, jitter=0)
    assert [b.next() for _ in range(5)] == [1, 2, 4, 4, 4]


def test_production_secret_fail_closed(monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    try:
        m.DecisionClient()
    except m.RuntimeContractError:
        pass
    else:
        raise AssertionError("expected fail closed")
