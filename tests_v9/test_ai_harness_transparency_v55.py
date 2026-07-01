"""حارس إسقاط شفافيّة الـHarness (V55 — المرحلة ٥).

يفرض: الإسقاط يعكس رؤية النموذج/قدراته/أدواته/موافقاته بصدق، بلا تسريب حمولة خام.
منطق صرف (``-m unit``).
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


HT = _load("services/ai_agronomist/harness_transparency.py", "sahool_harness_transparency_v55")


def _obs(**kw):
    base = {
        "field_id": "f1",
        "active_layer": "truecolor",
        "selected_date": "2026-06-01",
        "raster": {"state": "ready", "ready": True},
        "weather_source": "open-meteo",
        "notes": ["ملاحظة صادقة"],
        "blind": False,
        "policy": {
            "allowed_capabilities": ["can_read_field_data"],
            "data_sharing_level": "local_only",
        },
    }
    base.update(kw)
    return base


def test_projects_what_model_sees():
    t = HT.build_transparency(observation=_obs())
    assert t["sees"]["field_id"] == "f1"
    assert t["sees"]["raster_ready"] is True
    assert t["sees"]["blind"] is False
    assert t["capabilities"] == ["can_read_field_data"]
    assert t["data_sharing_level"] == "local_only"
    assert t["notes"] == ["ملاحظة صادقة"]


def test_tool_calls_projected_without_raw_payload():
    tc = {
        "tool": "get_field_state",
        "outcome": "executed",
        "risk": "low",
        "capability": "can_read_field_data",
        "requires_approval": False,
        "reason": "read_allowed",
        "data": {"secret_field_values": "must-not-leak"},  # حمولة خام
    }
    t = HT.build_transparency(observation=_obs(), tool_calls=[tc])
    view = t["tool_calls"][0]
    assert view["tool"] == "get_field_state" and view["outcome"] == "executed"
    assert "data" not in view  # لا تسريب حمولة خام
    assert "secret_field_values" not in str(view)


def test_pending_approvals_projected():
    pa = {"id": "req-1", "tool": "send_recommendation", "risk": "high", "status": "pending"}
    t = HT.build_transparency(observation=_obs(), pending_approvals=[pa])
    assert t["pending_approvals"][0]["id"] == "req-1"
    assert t["pending_approvals"][0]["status"] == "pending"


def test_empty_observation_defaults_blind():
    t = HT.build_transparency(observation=None)
    assert t["sees"]["blind"] is True
    assert t["capabilities"] == []
    assert t["data_sharing_level"] == "local_only"
    assert t["tool_calls"] == [] and t["pending_approvals"] == []
