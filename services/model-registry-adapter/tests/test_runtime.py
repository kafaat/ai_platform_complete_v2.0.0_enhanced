import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wxruntime", ROOT / "runtime.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


_QUIET = {
    "feature_drift": 0.0,
    "prediction_drift": 0.0,
    "calibration_error": 0.0,
    "error_rate": 0.0,
}


def test_drift_classification(monkeypatch):
    monkeypatch.setenv("MODEL_DRIFT_FEATURE_WARNING", "0.1")
    assert m.classify_drift({**_QUIET, "feature_drift": 0.01}) == "stable"
    assert m.classify_drift({**_QUIET, "feature_drift": 0.11}) == "warning"
    assert m.classify_drift({**_QUIET, "feature_drift": 0.25}) == "critical"


def test_missing_or_non_finite_drift_metric_is_never_stable():
    # A window that does not report a threshold metric proves nothing; it must not read as stable.
    assert m.classify_drift({}) == m.INSUFFICIENT_EVIDENCE_DRIFT_STATE
    assert m.classify_drift({"feature_drift": 0.0}) == m.INSUFFICIENT_EVIDENCE_DRIFT_STATE
    for bad in (None, float("nan"), float("inf"), "n/a", True):
        metrics = {**_QUIET, "error_rate": bad}
        assert m.classify_drift(metrics) == m.INSUFFICIENT_EVIDENCE_DRIFT_STATE, bad
    assert m.INSUFFICIENT_EVIDENCE_DRIFT_STATE != "stable"


def _verify_with(monkeypatch, checks):
    monkeypatch.setenv("MODEL_INFERENCE_VERIFY_URL", "http://inference.local")
    monkeypatch.setenv("MODEL_INFERENCE_VERIFY_TOKEN", "tok")
    digest = "d" * 64

    def _fake(method, url, *, token="", body=None, headers=None, timeout=15.0):
        resp = {"artifact_digest": body["artifact_digest"]}
        if checks is not _ABSENT:
            resp["checks"] = checks
        return resp

    monkeypatch.setattr(m, "_json_request", _fake)
    return m.HttpInferenceVerifier().verify(
        {
            "model_id": "m1",
            "feature_set_id": "f1",
            "target_environment": "staging",
            "active_artifact_uri": "s3://a",
            "active_artifact_digest": digest,
        }
    )


_ABSENT = object()
_ALL_PASS = {name: True for name in ("artifact_digest", "schema", "feature_set", "smoke_inference")}


def test_verifier_requires_every_requested_check_to_pass(monkeypatch):
    assert set(m.REQUIRED_VERIFICATION_CHECKS) == set(_ALL_PASS)
    out = _verify_with(monkeypatch, dict(_ALL_PASS))
    assert out["verification_state"] == "verified_healthy"
    assert out["failure_reason"] is None


def test_verifier_empty_or_absent_checks_fail_closed(monkeypatch):
    for checks in ({}, None, _ABSENT, ["artifact_digest"]):
        out = _verify_with(monkeypatch, checks)
        assert out["verification_state"] == "verification_failed", checks
        for name in _ALL_PASS:
            assert f"missing:{name}" in out["failure_reason"], (checks, name)
        assert isinstance(out["checks"], dict)


def test_verifier_partial_or_truthy_checks_fail_closed(monkeypatch):
    out = _verify_with(monkeypatch, {"artifact_digest": True, "schema": True})
    assert out["verification_state"] == "verification_failed"
    assert out["failure_reason"] == "missing:feature_set,missing:smoke_inference"

    out = _verify_with(monkeypatch, {**_ALL_PASS, "smoke_inference": "yes", "schema": 1})
    assert out["verification_state"] == "verification_failed"
    assert out["failure_reason"] == "schema,smoke_inference"


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
