"""Chunking cannot hide a dose label or split a quantity from its unit."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
SPEC = importlib.util.spec_from_file_location(
    "tts_chunk_critical_speech",
    Path(__file__).resolve().parents[1] / "services/tts-service/critical_speech.py",
)
critical = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(critical)


@pytest.mark.parametrize(
    "prefix,suffix",
    [
        ("جرعة " + "وصف " * 200, "٢٢"),
        ("PHI " + "وصف " * 200, "7"),
        ("٣٫٥ ", "لتر"),
        ("٣\u200d٫٥ ", "لـتر"),
    ],
)
def test_full_validation_text_rejects_critical_cross_chunk_patterns(prefix, suffix):
    # Neither isolated chunk necessarily carries the complete forbidden pattern.
    critical.prepare_critical_speech(suffix)
    with pytest.raises(critical.CriticalSpeechError, match="structured quantity slots"):
        critical.prepare_critical_speech(suffix, validation_text=prefix + suffix)


def test_noncritical_validated_context_is_unchanged():
    text = "حرارة الحقل ٢٢ درجة. " * 90
    chunk = "حرارة الحقل ٢٢ درجة. "
    assert critical.prepare_critical_speech(chunk, validation_text=text) == chunk


@pytest.mark.parametrize("full", ["x" * 8001, "another answer", 1])
def test_bad_context_fails_closed(full):
    with pytest.raises(critical.CriticalSpeechError):
        critical.prepare_critical_speech("حالة الحقل", validation_text=full)


def test_validation_context_never_weakens_existing_quantity_gate():
    with pytest.raises(critical.CriticalSpeechError):
        critical.prepare_critical_speech("٣ لتر", validation_text="٣ لتر")


def test_context_cannot_be_combined_with_partial_slot_templates():
    with pytest.raises(critical.CriticalSpeechError):
        critical.prepare_critical_speech(
            "{quantity} {unit}",
            {"quantity": "3", "unit": "l"},
            validation_text="{quantity} {unit}",
        )


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_real_http_routes_validate_full_context_before_provider(monkeypatch, path):
    from unittest.mock import AsyncMock

    from tests_v9.test_tts_tenant_policy_gate import _bearer, _client, _load

    main, _, _ = _load(monkeypatch)
    generate = AsyncMock()
    monkeypatch.setattr(main, "_generate_speech", generate)
    full = "جرعة " + "وصف " * 300 + "٢٢"
    response = _client(main).post(
        path,
        json={"text": "٢٢", "validation_text": full, "no_store": True, "provider": "piper"},
        headers=_bearer(main),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "critical_speech_invalid"
    generate.assert_not_awaited()


@pytest.mark.parametrize("no_store,full_size", [(False, 80), (True, 8001)])
def test_http_context_requires_no_store_and_bound(monkeypatch, no_store, full_size):
    from unittest.mock import AsyncMock

    from tests_v9.test_tts_tenant_policy_gate import _bearer, _client, _load

    main, _, _ = _load(monkeypatch)
    generate = AsyncMock()
    monkeypatch.setattr(main, "_generate_speech", generate)
    response = _client(main).post(
        "/v1/tts/synthesize",
        json={"text": "حقل", "validation_text": "حقل" + " " * full_size, "no_store": no_store},
        headers=_bearer(main),
    )
    assert response.status_code == 422
    generate.assert_not_awaited()


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_valid_http_chunk_has_full_context_receipt_and_never_touches_cache(monkeypatch, path):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from tests_v9.test_tts_tenant_policy_gate import _bearer, _client, _load

    main, _, _ = _load(monkeypatch)
    import routers.tts as routes

    chosen = SimpleNamespace(name="piper", external=False, media_type="audio/wav")
    monkeypatch.setattr(routes, "_provider_allowed_by_policy", AsyncMock(return_value=chosen))
    redis = SimpleNamespace(get=AsyncMock(), setex=AsyncMock())
    monkeypatch.setattr(main, "_redis", redis)
    generate = AsyncMock(return_value=b"synthetic-speech")
    monkeypatch.setattr(main, "_generate_speech", generate)
    response = _client(main).post(
        path,
        json={
            "text": "حرارة الحقل ٢٢. ",
            "validation_text": "حرارة الحقل ٢٢. " * 80,
            "no_store": True,
            "provider": "piper",
        },
        headers=_bearer(main),
    )
    assert response.status_code == 200
    assert response.headers["X-Speech-Validation"] == "full-context-v1"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Cache"] == "BYPASS"
    assert generate.call_args.args[0] == "حرارة الحقل ٢٢. "
    redis.get.assert_not_awaited()
    redis.setex.assert_not_awaited()


def test_authenticated_status_reports_limits_without_claiming_missing_local_model_ready(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from tests_v9.test_tts_tenant_policy_gate import _bearer, _client, _load

    main, providers, policy = _load(monkeypatch)
    monkeypatch.setattr(providers.PiperProvider, "available", lambda _: False)
    monkeypatch.setattr(providers.XTTSProvider, "available", lambda _: False)
    monkeypatch.setattr(
        policy,
        "resolve_policy",
        AsyncMock(
            return_value=SimpleNamespace(
                mode="local_only", external_allowed=False, external_providers=frozenset()
            )
        ),
    )
    monkeypatch.setattr(main, "MAX_TEXT_LEN", 700)
    response = _client(main).get("/v1/tts/status", headers=_bearer(main))
    assert response.status_code == 200
    body = response.json()
    assert body["max_text_length"] == 700
    assert body["max_validation_text_length"] == 8000
    assert body["policy_eligible_provider"] is None
    assert body["unavailable_reason"] == policy.POLICY_BLOCKED_ERROR
