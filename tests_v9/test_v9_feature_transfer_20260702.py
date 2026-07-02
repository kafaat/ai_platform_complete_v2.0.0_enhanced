from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))


def _nginx() -> str:
    return (ROOT / "nginx" / "nginx.v9.conf").read_text(encoding="utf-8")


def test_v9_contains_real_runtime_features_promoted_from_unified_light():
    services = _compose()["services"]
    for name in ["sahool-video-processor", "sahool-agriai-engine", "sahool-tts-service"]:
        assert name in services
        assert services[name]["build"]["context"] == "."
        assert "healthcheck" in services[name]


def test_v9_feature_services_use_v9_dns_and_correct_edge_port():
    services = _compose()["services"]
    video_env = services["sahool-video-processor"]["environment"]
    agriai_env = services["sahool-agriai-engine"]["environment"]
    assert video_env["EDGE_INFERENCE_URL"] == "http://sahool-edge:8100"
    assert agriai_env["EDGE_INFERENCE_URL"] == "http://sahool-edge:8100"
    assert video_env["MQTT_BROKER_URL"] == "mqtt://sahool-fastbee:1883"
    assert video_env["ZLMEDIA_API_URL"] in {
        "http://sahool-zlmediakit:80",
        "http://sahool-zlmediakit:8080",
    }


def test_v9_nginx_routes_promoted_services_and_tts_no_longer_returns_503():
    text = _nginx()
    for expected in [
        "upstream tts_backend         { server sahool-tts-service:8000;",
        "upstream video_backend       { server sahool-video-processor:8000;",
        "upstream agriai_backend      { server sahool-agriai-engine:8000;",
        "location /tts/",
        "location /api/video/",
        "location /api/agriai/",
    ]:
        assert expected in text
    tts_block = text.split("location /tts/", 1)[1].split("location", 1)[0]
    assert "proxy_pass http://tts_backend" in tts_block
    assert "return 503" not in tts_block


def test_v9_nginx_waits_for_promoted_services():
    services = _compose()["services"]
    deps = services["sahool-nginx"]["depends_on"]
    for name in ["sahool-video-processor", "sahool-agriai-engine", "sahool-tts-service"]:
        assert deps[name]["condition"] == "service_healthy"


def test_v9_csp_allows_configured_map_basemap_domains():
    text = _nginx()
    csp_lines = [line for line in text.splitlines() if "Content-Security-Policy" in line]
    assert csp_lines
    joined = "\n".join(csp_lines)
    assert "server.arcgisonline.com" in joined
    assert "basemaps.cartocdn.com" in joined
    assert "tile.openstreetmap.org" in joined


def test_v9_feature_transfer_gate_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/v9_feature_transfer_gate.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout
