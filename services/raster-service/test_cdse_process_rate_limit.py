import sys
import time
import types

import cdse_client


class FakeHTTPStatusError(Exception):
    pass


class FakeResp:
    def __init__(self, status_code, content=b"ok", text="", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = text or ("rate limited" if status_code == 429 else "")
        self.headers = headers or {}

    def json(self):
        return {"access_token": "token", "expires_in": 3600}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPStatusError(str(self.status_code))


def _patch_pure_builders(monkeypatch):
    monkeypatch.setattr(cdse_client, "build_evalscript", lambda index: "// evalscript")
    monkeypatch.setattr(cdse_client, "bbox_dims", lambda bbox: (16, 16))


def test_process_index_retries_429_then_succeeds(monkeypatch):
    _patch_pure_builders(monkeypatch)
    monkeypatch.setenv("CDSE_PROCESS_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("CDSE_PROCESS_MAX_RETRIES", "2")
    monkeypatch.setenv("CDSE_PROCESS_RETRY_BASE_SECONDS", "0.01")
    monkeypatch.setenv("CDSE_PROCESS_RETRY_MAX_SECONDS", "0.01")
    sleeps = []
    monkeypatch.setattr(cdse_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    calls = []
    responses = [FakeResp(429), FakeResp(200, content=b"tiff-bytes")]

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return responses.pop(0)

    fake_httpx = types.SimpleNamespace(post=fake_post, HTTPStatusError=FakeHTTPStatusError)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    client = cdse_client.CdseClient(base_url="https://example.test")
    client._token = "token"
    client._token_exp = time.time() + 3600
    out = client.process_index(
        index="ndvi",
        bbox=[44.0, 15.0, 44.01, 15.01],
        time_from="2025-01-01T00:00:00Z",
        time_to="2025-01-02T00:00:00Z",
    )

    assert out == b"tiff-bytes"
    assert len(calls) == 2
    assert sleeps == [0.01]


def test_process_index_honors_retry_after_header(monkeypatch):
    _patch_pure_builders(monkeypatch)
    monkeypatch.setenv("CDSE_PROCESS_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("CDSE_PROCESS_MAX_RETRIES", "1")
    monkeypatch.setenv("CDSE_PROCESS_RETRY_BASE_SECONDS", "0.01")
    sleeps = []
    monkeypatch.setattr(cdse_client.time, "sleep", lambda seconds: sleeps.append(seconds))

    responses = [FakeResp(429, headers={"Retry-After": "3"}), FakeResp(200, content=b"ok")]
    fake_httpx = types.SimpleNamespace(
        post=lambda *a, **k: responses.pop(0), HTTPStatusError=FakeHTTPStatusError
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    client = cdse_client.CdseClient(base_url="https://example.test")
    client._token = "token"
    client._token_exp = time.time() + 3600
    assert (
        client.process_index(
            index="ndvi",
            bbox=[44.0, 15.0, 44.01, 15.01],
            time_from="2025-01-01T00:00:00Z",
            time_to="2025-01-02T00:00:00Z",
        )
        == b"ok"
    )
    assert sleeps == [3.0]


_QUOTA_BODY = (
    '{"error":{"status":403,"reason":"Forbidden",'
    '"message":"Insufficient processing units or requests available in your account.",'
    '"code":"ACCESS_INSUFFICIENT_PROCESSING_UNITS"}}'
)


def _client_with_response(monkeypatch, resp):
    _patch_pure_builders(monkeypatch)
    monkeypatch.setenv("CDSE_PROCESS_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("CDSE_PROCESS_MAX_RETRIES", "3")
    monkeypatch.setattr(cdse_client.time, "sleep", lambda *_a: None)
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        return resp

    fake_httpx = types.SimpleNamespace(post=fake_post, HTTPStatusError=FakeHTTPStatusError)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    client = cdse_client.CdseClient(base_url="https://example.test")
    client._token = "token"
    client._token_exp = time.time() + 3600
    return client, calls


def test_process_index_quota_exhausted_raises_typed_and_does_not_retry(monkeypatch):
    """403 ACCESS_INSUFFICIENT_PROCESSING_UNITS ⇒ CdseQuotaExhausted بلا إعادة محاولة."""
    import pytest

    client, calls = _client_with_response(monkeypatch, FakeResp(403, text=_QUOTA_BODY))
    with pytest.raises(cdse_client.CdseQuotaExhausted):
        client.process_index(
            index="truecolor",
            bbox=[44.0, 15.0, 44.01, 15.01],
            time_from="2025-01-01T00:00:00Z",
            time_to="2025-01-02T00:00:00Z",
        )
    # حالة نهائيّة: طلب واحد فقط، لا طحن.
    assert len(calls) == 1


def test_process_index_other_403_is_not_treated_as_quota(monkeypatch):
    """403 لسبب آخر (بلا رمز نفاد الرصيد) يبقى خطأ HTTP عاديّاً لا CdseQuotaExhausted."""
    import pytest

    client, _ = _client_with_response(monkeypatch, FakeResp(403, text='{"error":"forbidden"}'))
    with pytest.raises(FakeHTTPStatusError):
        client.process_index(
            index="ndvi",
            bbox=[44.0, 15.0, 44.01, 15.01],
            time_from="2025-01-01T00:00:00Z",
            time_to="2025-01-02T00:00:00Z",
        )
