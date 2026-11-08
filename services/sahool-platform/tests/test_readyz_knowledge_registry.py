"""G3: ``/readyz`` يُعلِن غياب سجلّ مصادر الحقيقة (503) بدل حجبٍ صامتٍ لكلّ توصية ريّ.

كان ``knowledge_source_registry.json`` غائباً عن صورة المنصّة، فكلّ توصية MPC ساعيّة
تُحجَب بـ``knowledge_context_unsatisfied`` بينما ``/readyz`` يقول «جاهز».
"""

from __future__ import annotations

import asyncio
import json

import pytest

from shared.knowledge import source_registry as ksr

pytestmark = pytest.mark.unit


@pytest.fixture
def readyz(monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    # main أوّلاً: هو من يستورد الراوترات ويُركِّبها؛ استيرادُ الراوتر قبله يُنتج دورةً
    # تُركِّب راوتراً نصفَ مُهيّأ فتصير /readyz 404 لبقيّة الجناح.
    from api import main
    from api.routers import platform_health

    monkeypatch.setattr(main, "_DB_POOL", None)
    ksr.registry.cache_clear()
    yield platform_health.readyz
    ksr.registry.cache_clear()


def _call(readyz):
    response = asyncio.run(readyz())
    return response.status_code, json.loads(response.body)


def test_readyz_is_not_ready_when_the_knowledge_registry_is_missing(readyz, tmp_path, monkeypatch):
    monkeypatch.setenv(ksr.REGISTRY_ENV, str(tmp_path / "absent.json"))
    status, body = _call(readyz)
    assert status == 503
    check = body["checks"]["knowledge_source_registry"]
    assert check["ok"] is False
    assert "absent.json" in check["error"]


def test_readyz_reports_the_registry_when_present(readyz, monkeypatch):
    monkeypatch.delenv(ksr.REGISTRY_ENV, raising=False)
    status, body = _call(readyz)
    assert status == 200, body
    assert body["checks"]["knowledge_source_registry"]["ok"] is True
