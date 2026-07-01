"""حارس سياق الرصد الموحَّد (V55 — المرحلة ٣).

يفرض الصدق في الغياب: لقطة رصد منقوصة تحمل ملاحظات صريحة وعلَم ``blind``، ولا تدّعي
جاهزيّة غير متحقَّقة. منطق صرف (``-m unit``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


OBS = _load("services/ai_agronomist/observation_context.py", "sahool_observation_v55")


def test_ready_field_is_not_blind():
    obs = OBS.build_observation(
        field_id="f1",
        active_layer="truecolor",
        selected_date="2026-06-01",
        raster_state=OBS.RASTER_READY,
        weather_source="open-meteo",
        policy={
            "allowed_capabilities": ["can_read_field_data"],
            "data_sharing_level": "local_only",
        },
    )
    assert obs["blind"] is False
    assert obs["raster"]["ready"] is True
    assert obs["policy"]["data_sharing_level"] == "local_only"
    assert not any("TrueColor" in n for n in obs["notes"])


def test_truecolor_not_rendered_is_honest_and_blind():
    obs = OBS.build_observation(field_id="f1", raster_state=OBS.RASTER_NOT_RENDERED)
    assert obs["blind"] is True
    assert any("TrueColor" in n and "تشغيل تجهيز" in n for n in obs["notes"])


def test_no_field_selected_is_blind_with_note():
    obs = OBS.build_observation(field_id=None, raster_state=OBS.RASTER_READY)
    assert obs["blind"] is True
    assert any("لم يُختَر حقل" in n for n in obs["notes"])


def test_cdse_not_configured_note():
    obs = OBS.build_observation(field_id="f", raster_state=OBS.RASTER_NOT_CONFIGURED)
    assert any("Copernicus غير مُهيّأة" in n for n in obs["notes"])


def test_backfill_running_note():
    obs = OBS.build_observation(
        field_id="f", raster_state=OBS.RASTER_READY, weather_source="x", backfill_status="running"
    )
    assert any("تجهيز الصور قيد التنفيذ" in n for n in obs["notes"])


def test_api_errors_capped_and_noted():
    obs = OBS.build_observation(
        field_id="f",
        raster_state=OBS.RASTER_READY,
        weather_source="x",
        last_api_errors=[f"err{i}" for i in range(20)],
    )
    assert len(obs["last_api_errors"]) == 10  # سقف
    assert any("أخطاء API" in n for n in obs["notes"])


def test_unknown_weather_source_note():
    obs = OBS.build_observation(field_id="f", raster_state=OBS.RASTER_READY, weather_source=None)
    assert any("مصدر الطقس غير معروف" in n for n in obs["notes"])


def test_policy_defaults_are_safe():
    obs = OBS.build_observation(field_id="f", raster_state=OBS.RASTER_READY, weather_source="x")
    assert obs["policy"]["data_sharing_level"] == "local_only"
    assert obs["policy"]["allowed_capabilities"] == []
