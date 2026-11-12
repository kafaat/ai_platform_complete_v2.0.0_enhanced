from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import api.main  # noqa: F401
import api.routers.evidence_map as router
import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("defect", ["wrong_tenant", "missing_field", "negative", "mirror", "too_many_successes"])
async def test_owner_failure_cannot_be_displayed_as_an_empty_or_verified_field(monkeypatch, defect):
    user = SimpleNamespace(tenant_id="my-tenant")
    counts = {"p": {"decisions": 3, "outcomes": 2, "successes": 1}}
    reply = {"counts": counts, "tenant_id": user.tenant_id, "authoritative": True}
    if defect == "wrong_tenant":
        reply["tenant_id"] = "another-tenant"
    elif defect == "missing_field":
        counts.clear()
    elif defect == "negative":
        counts["p"]["decisions"] = -1
    elif defect == "mirror":
        reply["authoritative"] = False
    else:
        counts["p"]["successes"] = 3

    @asynccontextmanager
    async def fields_connection(_):
        yield AsyncMock()

    monkeypatch.setenv("FEATURE_EVIDENCE_MAP", "true")
    monkeypatch.setattr(router, "tenant_connection", fields_connection)
    monkeypatch.setattr(router, "get_platform_decision_sor_mode",
                        lambda: SimpleNamespace(strict_decision_service_required=True))
    monkeypatch.setattr(router, "_fields_only_rows", AsyncMock(return_value=[{"field_id": "p"}]))
    monkeypatch.setattr(router, "decision_post_json", AsyncMock(return_value=reply))
    with pytest.raises(HTTPException) as exc:
        await router.evidence_map_endpoint(user=user)
    assert exc.value.status_code == 502
