"""Real HTTP routes prove live speech bypasses Redis reads and writes."""

from unittest.mock import AsyncMock

import pytest

from tests_v9.test_tts_tenant_policy_gate import _BODY, _bearer, _client, _load

pytestmark = [pytest.mark.unit, pytest.mark.security]


@pytest.mark.parametrize("no_store", [False, True])
@pytest.mark.parametrize("cached", [None, b"cached-speech"])
def test_no_store_bypasses_both_cache_operations(monkeypatch, no_store, cached):
    main, _, _ = _load(monkeypatch)
    from types import SimpleNamespace

    import routers.tts as routes

    chosen = SimpleNamespace(
        name=main.DEFAULT_PROVIDER_NAME, external=False, media_type="audio/wav"
    )
    monkeypatch.setattr(routes, "_provider_allowed_by_policy", AsyncMock(return_value=chosen))
    redis = SimpleNamespace(get=AsyncMock(return_value=cached), setex=AsyncMock())
    monkeypatch.setattr(main, "_redis", redis)
    generate = AsyncMock(return_value=b"new-speech")
    monkeypatch.setattr(main, "_generate_speech", generate)
    response = _client(main).post(
        "/v1/tts/synthesize", json=_BODY | {"no_store": no_store}, headers=_bearer(main)
    )
    assert response.status_code == 200
    if no_store:
        redis.get.assert_not_awaited()
        redis.setex.assert_not_awaited()
        assert response.content == b"new-speech"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Cache"] == "BYPASS"
    else:
        redis.get.assert_awaited_once()
        assert response.headers["Cache-Control"] == "private, max-age=86400"
        if cached:
            generate.assert_not_awaited()
            redis.setex.assert_not_awaited()
            assert response.headers["X-Cache"] == "HIT"
        else:
            redis.setex.assert_awaited_once()
            assert response.headers["X-Cache"] == "MISS"


@pytest.mark.parametrize("value", ["true", 1, None])
def test_no_store_flag_is_strict(monkeypatch, value):
    main, _, _ = _load(monkeypatch)
    response = _client(main).post(
        "/v1/tts/synthesize", json=_BODY | {"no_store": value}, headers=_bearer(main)
    )
    assert response.status_code == 422


def test_local_stream_is_no_store_and_bypasses_cache(monkeypatch):
    main, _, _ = _load(monkeypatch)
    from types import SimpleNamespace

    import routers.tts as routes

    chosen = SimpleNamespace(name="piper", external=False, media_type="audio/wav")
    monkeypatch.setattr(routes, "_provider_allowed_by_policy", AsyncMock(return_value=chosen))
    redis = SimpleNamespace(get=AsyncMock(), setex=AsyncMock())
    monkeypatch.setattr(main, "_redis", redis)
    monkeypatch.setattr(main, "_generate_speech", AsyncMock(return_value=b"stream-audio"))
    response = _client(main).post(
        "/v1/tts/stream", json=_BODY | {"no_store": True}, headers=_bearer(main)
    )
    assert response.status_code == 200
    assert response.content == b"stream-audio"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Cache"] == "BYPASS"
    redis.get.assert_not_awaited()
    redis.setex.assert_not_awaited()
