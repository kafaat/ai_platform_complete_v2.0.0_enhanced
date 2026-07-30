"""tests/test_canonical_soil_state.py — عميل التربة الكنسيّ (بلا شبكة، عبر respx).

يؤكّد:
  - النجاح مع ``contract_version`` يُطبَّع بإضافة ``schema_version`` دون حذف الأصل.
  - غياب الرمز (token) ⇒ None فوراً، بلا طلب شبكة.
  - 404 ⇒ None (لا ملفّ تربة للحقل).
  - خطأ HTTP/شبكة ⇒ None — لا اختلاق.
  - حمولة ليست dict، أو بلا ``contract_version``/``schema_version``/``schema`` ⇒ None.
  - وجود ``schema_version``/``schema`` أصلاً يُبقي الحمولة كما هي دون تكرار المفتاح.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from api.canonical_soil_state import resolve_canonical_soil_state

pytestmark = pytest.mark.unit

_URL = "http://sahool-soil-service:8000/v1/fields/f1/soil/profile"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-token")
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("SOIL_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("SOIL_SERVICE_URL", raising=False)


@pytest.mark.asyncio
@respx.mock
async def test_success_normalizes_contract_version_into_schema_version():
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"contract_version": "soil-profile.v1", "field_id": "f1", "layers": []}
        )
    )
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result["schema_version"] == "soil-profile.v1"
    assert result["contract_version"] == "soil-profile.v1"
    assert result["field_id"] == "f1"


@pytest.mark.asyncio
@respx.mock
async def test_existing_schema_version_key_is_left_untouched():
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "contract_version": "soil-profile.v1",
                "schema_version": "canonical_soil_state.v1",
            },
        )
    )
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result["schema_version"] == "canonical_soil_state.v1"


@pytest.mark.asyncio
async def test_missing_token_returns_none_without_network_call(monkeypatch):
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with respx.mock:
        route = respx.get(_URL).mock(return_value=httpx.Response(200, json={}))
        result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
        assert result is None
        assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_404_returns_none():
    respx.get(_URL).mock(return_value=httpx.Response(404))
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_server_error_returns_none_never_synthesizes():
    respx.get(_URL).mock(return_value=httpx.Response(500))
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_network_error_returns_none():
    respx.get(_URL).mock(side_effect=httpx.ConnectError("refused"))
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_non_dict_payload_returns_none():
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[1, 2, 3]))
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_payload_without_any_version_key_returns_none():
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"field_id": "f1"}))
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_returns_none():
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, content=b"not json", headers={"content-type": "application/json"}
        )
    )
    result = await resolve_canonical_soil_state(tenant_id="t1", field_id="f1")
    assert result is None
