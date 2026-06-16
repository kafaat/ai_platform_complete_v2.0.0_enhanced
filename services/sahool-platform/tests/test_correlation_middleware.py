"""اختبارات وسيط معرّف الربط (api.correlation_middleware) — TestClient على تطبيق صغير."""

import pytest

pytestmark = pytest.mark.unit


def _app():
    pytest.importorskip("fastapi")
    from api.correlation_middleware import CorrelationIdMiddleware
    from core.correlation import get_correlation_id
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/probe")
    def probe():
        return {"cid": get_correlation_id()}

    return app


def test_generates_correlation_id_when_absent():
    from api.correlation_middleware import CORRELATION_HEADER
    from fastapi.testclient import TestClient

    client = TestClient(_app())
    r = client.get("/probe")
    assert r.status_code == 200
    # وُلِّد معرّف وأُعيد في الرأس + رآه المسار.
    assert r.headers.get(CORRELATION_HEADER)
    assert r.json()["cid"] is not None


def test_propagates_incoming_correlation_id():
    from api.correlation_middleware import CORRELATION_HEADER
    from fastapi.testclient import TestClient

    client = TestClient(_app())
    r = client.get("/probe", headers={CORRELATION_HEADER: "abc-123"})
    assert r.json()["cid"] == "abc-123"  # نفس المعرّف الوارد وصل المسار
    assert r.headers.get(CORRELATION_HEADER) == "abc-123"  # وأُعيد في الاستجابة


def test_distinct_ids_for_separate_requests():
    from fastapi.testclient import TestClient

    client = TestClient(_app())
    a = client.get("/probe").json()["cid"]
    b = client.get("/probe").json()["cid"]
    assert a and b and a != b
