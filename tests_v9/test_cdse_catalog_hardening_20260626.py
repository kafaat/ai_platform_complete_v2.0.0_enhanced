from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import cdse_client  # noqa: E402


def test_rfc3339_normalizes_bare_dates_and_utc_offsets():
    assert cdse_client._to_rfc3339("2026-06-26") == "2026-06-26T00:00:00Z"
    assert cdse_client._to_rfc3339("2026-06-26T10:00:00+00:00") == "2026-06-26T10:00:00Z"
    assert cdse_client._to_rfc3339("2026-06-26T10:00:00Z") == "2026-06-26T10:00:00Z"


@pytest.mark.parametrize("value, expected", [(-5, 0.0), (40, 40.0), (120, 100.0), ("bad", 40.0)])
def test_cloud_percentage_is_provider_safe(value, expected):
    assert cdse_client._clamp_cloud_pct(value) == expected


def test_search_scenes_falls_back_when_provider_rejects_filter(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = str(body)

        def json(self):
            return self._body

    def fake_post(url, json, headers, timeout):  # noqa: A002
        calls.append(json)
        if len(calls) == 1:
            return Response(400, {"error": "bad filter"})
        return Response(
            200,
            {
                "features": [
                    {"id": "ok", "properties": {"eo:cloud_cover": 10}},
                    {"id": "cloudy", "properties": {"eo:cloud_cover": 90}},
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", type("Httpx", (), {"post": staticmethod(fake_post)}))
    client = cdse_client.CdseClient(base_url="https://example.test")
    monkeypatch.setattr(client, "token", lambda: "token")

    scenes = client.search_scenes(
        bbox=[44.0, 15.0, 44.1, 15.1],
        time_from="2026-06-20",
        time_to="2026-06-26",
        max_cloud_pct=40,
    )

    assert [s["id"] for s in scenes] == ["ok"]
    assert "filter" in calls[0]
    assert "filter" not in calls[1]
    assert calls[0]["datetime"] == "2026-06-20T00:00:00Z/2026-06-26T00:00:00Z"


def test_search_scenes_rejects_invalid_bbox_before_network(monkeypatch):
    client = cdse_client.CdseClient(base_url="https://example.test")
    monkeypatch.setattr(client, "token", lambda: "token")
    with pytest.raises(ValueError):
        client.search_scenes(bbox=[44, 15, 43, 16], time_from="2026-06-20", time_to="2026-06-26")
