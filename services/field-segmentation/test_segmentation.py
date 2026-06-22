#!/usr/bin/env python3
"""
اختبارات وحدة لخدمة تقطيع الحقل (offline، pytest، @unit).

تغطّي عقد الصدق:
  • manual → هندسة Polygon مغلقة صالحة + source=manual (مسار حقيقيّ).
  • auto بلا نموذج مُهيّأ → 503 صادق (model_not_configured) — لا تلفيق.
  • hybrid بلا نموذج مُهيّأ → 503 صادق.
  • تحقّق المضلّع (NaN/خارج المدى/رؤوس ناقصة) → 422.
  • مصادقة توكن الخدمة (X-Agent-Token).

التشغيل:
  cd services/field-segmentation && PYTHONPATH=. pytest -m unit -q
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.unit

_TOKEN = "test-agent-token"


def _load_app(monkeypatch, *, model_path: str = "", backend: str = ""):
    """يحمّل main بقيم بيئة محدّدة (الخدمة تقرأها وقت الاستيراد)."""
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _TOKEN)
    if model_path:
        monkeypatch.setenv("SEGMENTATION_MODEL_PATH", model_path)
    else:
        monkeypatch.delenv("SEGMENTATION_MODEL_PATH", raising=False)
    if backend:
        monkeypatch.setenv("SEGMENTATION_BACKEND", backend)
    else:
        monkeypatch.delenv("SEGMENTATION_BACKEND", raising=False)
    sys.modules.pop("main", None)
    import main  # noqa: WPS433

    return importlib.reload(main)


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    mod = _load_app(monkeypatch)  # لا نموذج مُهيّأ افتراضاً
    return TestClient(mod.app)


def _hdr() -> dict:
    return {"X-Agent-Token": _TOKEN}


# ── ١. المسار اليدويّ حقيقيّ → هندسة + source=manual ──
def test_manual_returns_closed_geometry(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "manual", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "manual"
    assert body["source"] == "manual"
    ring = body["geometry"]["coordinates"][0]
    assert body["geometry"]["type"] == "Polygon"
    # الحلقة أُغلِقت (الرأس الأوّل = الأخير).
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_manual_accepts_geojson(client):
    gj = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]],
    }
    r = client.post("/segment", json={"mode": "manual", "user_polygon": gj}, headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "manual"


# ── ٢. auto/hybrid بلا نموذج → 503 صادق ──
def test_auto_without_model_returns_503(client):
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "model_not_configured"
    assert "SEGMENTATION_MODEL_PATH" in detail["note_ar"]


def test_hybrid_without_model_returns_503(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "hybrid", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "model_not_configured"


# ── ٣. تحقّق المضلّع (مسار حقيقيّ يرفض القمامة) ──
def test_manual_rejects_out_of_range(client):
    poly = [[999.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_rejects_too_few_points(client):
    poly = [[46.0, 24.0], [46.1, 24.0]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_requires_polygon(client):
    r = client.post("/segment", json={"mode": "manual"}, headers=_hdr())
    assert r.status_code == 422, r.text


# ── ٤. مصادقة توكن الخدمة ──
def test_missing_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly})
    assert r.status_code == 401, r.text


def test_wrong_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "manual", "user_polygon": poly},
        headers={"X-Agent-Token": "wrong"},
    )
    assert r.status_code == 401, r.text


# ── ٥. صحّة/جاهزيّة ──
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["service"] == "field-segmentation"


def test_readyz_reports_model_state(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["model_configured"] is False
