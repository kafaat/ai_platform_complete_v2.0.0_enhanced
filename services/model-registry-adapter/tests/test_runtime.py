import importlib.util
import os
import pathlib
import re
import sys

import pytest

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


# ── F-R03: registry settings reach a configured adapter, and their absence stops it ────────
#
# Compose interpolates every service, profile or not, so the opt-in block cannot demand the
# registry URL/token without making the default stack demand them too. A nested guarded form
# (`${URL:-${ID:+${URL:?...}}}`) was tried and is not portable: the CI runner's Compose evaluated
# the inner `:?` with the guard empty. The block therefore passes flat `${NAME:-default}` values
# and the adapter itself refuses to start once it is configured (REGISTRY_ADAPTER_ID set) without
# a registry URL and token, whatever SAHOOL_ENV says.

_adapter_spec = importlib.util.spec_from_file_location("wxadapter", ROOT / "adapter.py")
adapter = importlib.util.module_from_spec(_adapter_spec)
sys.modules[_adapter_spec.name] = adapter  # dataclasses resolve their module through sys.modules
_adapter_spec.loader.exec_module(adapter)

COMPOSE = ROOT.parents[1] / "docker-compose.v9.yml"
SERVICE = "sahool-model-lifecycle-adapter"
REGISTRY_DEFAULTS = {
    "MODEL_REGISTRY_BACKEND": "http",
    "MODEL_REGISTRY_URL": "",
    "MODEL_REGISTRY_TOKEN": "",
    "MODEL_REGISTRY_DRY_RUN": "true",
}
_FLAT_DEFAULT = re.compile(r"\$\{(?P<name>[A-Z0-9_]+):-(?P<default>[^${}?]*)\}")


def _configured(monkeypatch, **overrides):
    env = {
        "SAHOOL_ENV": "staging",
        "REGISTRY_ADAPTER_ID": "adapter-1",
        "MODEL_REGISTRY_BACKEND": "http",
        "MODEL_REGISTRY_URL": "http://registry.local",
        "MODEL_REGISTRY_TOKEN": "tok",
        "MODEL_REGISTRY_DRY_RUN": "true",
        **overrides,
    }
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize("env", ["staging", "development", "production"])
@pytest.mark.parametrize("name", ["MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN"])
@pytest.mark.parametrize("supplied", [None, "", "   "])
def test_a_configured_adapter_refuses_to_start_without_registry_setting(
    monkeypatch, env, name, supplied
):
    _configured(
        monkeypatch,
        SAHOOL_ENV=env,
        MODEL_REGISTRY_DRY_RUN="false" if env == "production" else "true",
        **{name: supplied},
    )
    with pytest.raises(adapter.RegistryError) as refused:
        adapter.validate_runtime()
    assert name in str(refused.value)
    assert "REGISTRY_ADAPTER_ID" in str(refused.value)


def test_a_configured_adapter_with_registry_settings_passes_validation(monkeypatch):
    _configured(monkeypatch)
    adapter.validate_runtime()


def test_an_unconfigured_adapter_keeps_its_existing_refusals(monkeypatch):
    """Without an identity nothing new is demanded; the URL was, and still is, always required."""
    _configured(monkeypatch, REGISTRY_ADAPTER_ID=None, MODEL_REGISTRY_TOKEN=None)
    adapter.validate_runtime()  # non-production, no token: unchanged
    _configured(monkeypatch, REGISTRY_ADAPTER_ID=None, MODEL_REGISTRY_URL=None)
    with pytest.raises(adapter.RegistryError, match="MODEL_REGISTRY_URL is required"):
        adapter.validate_runtime()


def _compose_block_environment() -> dict[str, str]:
    """The block's `environment:` mapping, read as text (this CI job need not ship PyYAML)."""
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"  {SERVICE}:")
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("   "):
            break
        block.append(line)
    env_at = next(i for i, line in enumerate(block) if line.strip() == "environment:")
    indent = len(block[env_at]) - len(block[env_at].lstrip())
    out: dict[str, str] = {}
    for line in block[env_at + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        key, _, value = line.strip().partition(":")
        out[key] = value.strip()
    assert out, f"{SERVICE} environment mapping not found"
    return out


def test_the_compose_block_passes_the_registry_settings_with_flat_defaults():
    env = _compose_block_environment()
    for name, default in REGISTRY_DEFAULTS.items():
        assert name in env, f"{SERVICE} does not pass {name} to the adapter"
        match = _FLAT_DEFAULT.fullmatch(env[name])
        assert match, (
            f"{name}: {env[name]!r} must be a flat ${{{name}:-default}}; a nested or required "
            "(`?`) expansion is evaluated differently across Compose versions"
        )
        assert match["name"] == name
        assert match["default"] == default, f"{name} default must be {default!r}"


def test_the_opt_in_block_demands_nothing_from_the_default_stack():
    """Compose interpolates inactive profiles too: no required-variable syntax in this block."""
    offenders = {k: v for k, v in _compose_block_environment().items() if "?" in v}
    assert not offenders, offenders


def _render(host: dict[str, str]) -> dict[str, str]:
    """Container env Compose builds for this block from ``host`` (flat `${NAME:-d}` only)."""

    def one(raw: str) -> str:
        return _FLAT_DEFAULT.sub(lambda m: host.get(m["name"]) or m["default"], raw)

    return {k: one(v) for k, v in _compose_block_environment().items()}


def test_the_default_stack_container_is_refused_by_the_adapter(monkeypatch):
    """Started with nothing configured, the adapter stops at start-up instead of idling."""
    for name, value in _render({}).items():
        monkeypatch.setenv(name, value)
    assert os.environ["SAHOOL_ENV"] == "production"
    with pytest.raises(adapter.RegistryError):
        adapter.validate_runtime()


@pytest.mark.parametrize("missing", ["MODEL_REGISTRY_URL", "MODEL_REGISTRY_TOKEN"])
def test_a_configured_container_without_a_registry_setting_is_refused(monkeypatch, missing):
    host = {
        "REGISTRY_ADAPTER_ID": "adapter-1",
        "MODEL_REGISTRY_URL": "https://registry.invalid",
        "MODEL_REGISTRY_TOKEN": "test-only-not-a-real-credential",
        "MODEL_REGISTRY_DRY_RUN": "false",
    }
    for name, value in _render(host).items():
        monkeypatch.setenv(name, value)
    adapter.validate_runtime()  # complete operator host: the container passes start-up checks
    del host[missing]
    for name, value in _render(host).items():
        monkeypatch.setenv(name, value)
    with pytest.raises(adapter.RegistryError, match=missing):
        adapter.validate_runtime()
