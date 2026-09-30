"""agriai-engine: /readyz غير الجاهز يُعيد 503 — AGRIAI-READYZ-RETURNS-200-WHEN-NOT-READY-01.

**العطل:** في وضع الإنتاج (`AGRIAI_PRODUCTION_MODE`) بلا مسارٍ علميٍّ مُثبَت، كان الجسمُ
يقول `ready: false` والرمزُ 200. الموازِن والمُنسِّق وفحوصُ النشر تقرأ الرمز لا الجسم،
فالخدمةُ تُعَدّ جاهزةً وهي تُعلِن عكس ذلك.

**العقد:** غيرُ الجاهز ⇒ 503 بالجسم نفسه؛ الجاهز (خارج الإنتاج، أو الإنتاج بمسارٍ مُثبَت)
⇒ 200. و`/healthz` حياةٌ لا جاهزيّة: 200 في الحالتين.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = pytest.mark.unit

SVC = os.path.join(os.path.dirname(__file__), "..", "services", "agriai-engine")
_SCI_ENV = ("SIM_PCSE_ENABLED", "SIM_PCSE_INTEGRATION_VERIFIED")


def _client(monkeypatch, production: bool):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "1" if production else "0")
    for key in _SCI_ENV:
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location(
        "_agriai_main_readyz", os.path.join(SVC, "main.py")
    )
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    return main, TestClient(main.app)


def test_production_without_verified_scientific_path_is_503(monkeypatch):
    _main, client = _client(monkeypatch, production=True)
    r = client.get("/readyz")
    body = r.json()
    assert body["ready"] is False
    assert body["status"] == "not_ready"
    assert body["dependencies"]["pcse"] == "verified_missing"
    assert r.status_code == 503, "ready=false must not be served as HTTP 200"


def test_liveness_is_unaffected_when_not_ready(monkeypatch):
    _main, client = _client(monkeypatch, production=True)
    assert client.get("/healthz").status_code == 200


def test_development_mode_is_ready_200(monkeypatch):
    _main, client = _client(monkeypatch, production=False)
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_production_with_verified_scientific_path_is_200(monkeypatch):
    """الشاهد الموجب: الإنتاجُ الجاهز فعلاً لا يُرفَض — وإلّا صار الإصلاحُ 503 دائماً."""
    main, client = _client(monkeypatch, production=True)
    ready_status = {**main.wa.scientific_path_status(), "scientific_ready": True}
    monkeypatch.setattr(main.wa, "scientific_path_status", lambda: ready_status)
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["ready"] is True
