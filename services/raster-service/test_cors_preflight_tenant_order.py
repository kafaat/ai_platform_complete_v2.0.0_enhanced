"""طلب CORS التمهيديّ (preflight) لا يحمل اعتماداً فلا يُحكَم عليه بفحص المستأجر (مراجعة #1330).

العطل: ``tenant_context_middleware`` أُضيف بعد ``CORSMiddleware``، وفي Starlette آخِرُ وسيطٍ
يُضاف هو الأبعد فيعمل أوّلاً. فـ``OPTIONS …/tilejson?tid=T-1`` من المتصفّح (بلا Authorization
ولا X-Tenant-Id — المتصفّح لا يرسلهما في الطلب التمهيديّ) يُرفَض 403 من فحص ``tid`` قبل أن
يجيبه CORS، فلا يُرسَل الطلب الحقيقيّ أبداً. العقد: CORS أبعد وسيط — يجيب التمهيديّ بنفسه
(لا يبلغ أيَّ معالج)، والطلب الحقيقيّ يبقى خاضعاً لفحص المستأجر كما هو.
"""

from __future__ import annotations

import pytest
import raster_app_factory
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ORIGIN = "https://app.sahool.test"
TILEJSON = "/v1/fields/F-123/tilejson?index=ndvi&tid=T-1"


@pytest.fixture()
def client() -> TestClient:
    app = raster_app_factory.create_raster_app(
        title="raster-test", version="0", lifespan=None, cors_origins=[ORIGIN]
    )
    return TestClient(app)


def _preflight(client: TestClient, origin: str = ORIGIN):
    return client.options(
        TILEJSON,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_browser_preflight_with_tid_hint_is_answered_by_cors(client):
    resp = _preflight(client)
    assert resp.status_code == 200, resp.text
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


def test_preflight_from_disallowed_origin_is_still_refused(client):
    resp = _preflight(client, origin="https://evil.example")
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


def test_real_request_keeps_tenant_validation(client):
    """الطلب الحقيقيّ (وOPTIONS بلا Access-Control-Request-Method) يبقى 403 بلا مستأجر موثَّق،
    والآن بترويسات CORS فيقرأ المتصفّح الرفض بدل خطأ CORS مُبهَم."""
    resp = client.get(TILEJSON, headers={"Origin": ORIGIN})
    assert resp.status_code == 403
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert client.options(TILEJSON, headers={"Origin": ORIGIN}).status_code == 403
