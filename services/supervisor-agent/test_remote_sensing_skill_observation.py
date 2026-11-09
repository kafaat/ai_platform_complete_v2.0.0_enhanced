"""NDVI skill output is an observation, not an irrigation/harvest instruction."""

import asyncio
import json
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _p in (_REPO_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from skills.remote_sensing_skill import RemoteSensingSkill  # noqa: E402

pytestmark = pytest.mark.unit

_INSTRUCTIONS = ("ري فوري", "استعد للحصاد", "زراعة عاجلة", "قد يحتاج إلى ري")


class _FakeMCP:
    def __init__(self, payload):
        self.payload = payload

    async def call_tool(self, server, tool, args):
        return {"content": [{"type": "text", "text": json.dumps(self.payload)}]}


def _run(payload):
    skill = RemoteSensingSkill(_FakeMCP(payload))
    return asyncio.run(skill.execute("ndvi", field_id="f1", tenant_id="t"))


@pytest.mark.parametrize("mean", [0.1, 0.3, 0.5, 0.7, 0.9])
def test_no_irrigation_or_harvest_instruction_at_any_band(mean):
    out = _run({"mean": mean, "date": "2026-06-01", "scene_id": "S2A_X", "quality": "good"})
    assert out["type"] == "ndvi_report"
    text = json.dumps(out, ensure_ascii=False)
    for phrase in _INSTRUCTIONS:
        assert phrase not in text
    assert out["recommendation"] is None
    assert "يحتاج تحقّقاً ميدانياً" in out["observation_note"]
    assert "سياق المرحلة والرطوبة" in out["observation_note"]
    assert out["requires_field_verification"] is True


def test_missing_cloud_coverage_is_unknown_not_zero():
    out = _run({"mean": 0.5})
    assert out["cloud_coverage_pct"] is None


def test_cloud_coverage_fraction_and_pct_are_carried():
    assert _run({"mean": 0.5, "cloud_coverage": 0.123})["cloud_coverage_pct"] == 12.3
    assert _run({"mean": 0.5, "cloud_coverage_pct": 7})["cloud_coverage_pct"] == 7.0


def test_scene_date_quality_fields_are_carried():
    out = _run(
        {
            "mean": 0.42,
            "date": "2026-06-01",
            "scene_id": "S2A_X",
            "quality": {"gate": "pass"},
            "source": "raster-service",
            "real_data": True,
            "index": "ndvi",
        }
    )
    assert out["scene_id"] == "S2A_X"
    assert out["acquisition_date"] == "2026-06-01"
    assert out["quality"] == {"gate": "pass"}
    assert out["observation_source"] == "raster-service"
    assert out["real_data"] is True
    assert out["index"] == "ndvi"


@pytest.mark.parametrize("bad", [None, "0.5", float("nan"), True])
def test_unusable_mean_is_an_error(bad):
    assert _run({"mean": bad})["type"] == "error"
