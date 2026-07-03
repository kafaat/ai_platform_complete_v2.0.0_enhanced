from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_sam2_polygon_postprocessing_is_meter_configurable() -> None:
    src = read("services/sam2-inference/main.py")
    assert "SAM2_POLYGON_SIMPLIFY_TOLERANCE_M" in src
    assert "SAM2_POLYGON_DEDUP_TOLERANCE_M" in src
    assert "SIMPLIFY_TOLERANCE_M" in src
    assert "DEDUP_TOLERANCE_M" in src
    assert "_dedupe_ring" in src
    assert "make_valid" in src or "buffer(0)" in src


def test_sam2_polygon_postprocessing_env_is_exposed_to_compose_and_examples() -> None:
    compose = read("docker-compose.v9.yml")
    env = read(".env.example")
    assert "SAM2_POLYGON_SIMPLIFY_TOLERANCE_M" in compose
    assert "SAM2_POLYGON_DEDUP_TOLERANCE_M" in compose
    assert "SAM2_POLYGON_SIMPLIFY_TOLERANCE_M=3" in env
    assert "SAM2_POLYGON_DEDUP_TOLERANCE_M=0.5" in env
