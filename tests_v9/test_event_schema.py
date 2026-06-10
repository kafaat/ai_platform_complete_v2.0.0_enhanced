"""Unit tests: unified event envelope + validation (core/event_schema)."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
_UUID = "22222222-2222-2222-2222-222222222222"


def _es():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(
        "event_schema", os.path.join(ROOT, "services/sahool-platform/core/event_schema.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["event_schema"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_valid_envelope_passes_and_autofills():
    es = _es()
    env = es.new_event("field.created", "field", _UUID, _UUID, source="mobile")
    assert es.validate_envelope(env) == []
    assert env.event_id and env.occurred_at  # auto-filled


@pytest.mark.unit
def test_invalid_envelope_reports_each_problem_honestly():
    es = _es()
    bad = es.EventEnvelope(
        event_type="NotDotted", entity_type="", entity_id="not-uuid", tenant_id="x", source="ghost"
    )
    errors = es.validate_envelope(bad)
    joined = " ".join(errors)
    assert "event_type" in joined and "entity_type" in joined
    assert "entity_id" in joined and "tenant_id" in joined and "source" in joined


@pytest.mark.unit
def test_to_emit_args_matches_emit_event_contract():
    es = _es()
    env = es.new_event("soil.sample.recorded", "field", _UUID, _UUID)
    args = env.to_emit_args()
    # نفس مفاتيح EventBus.emit / دالّة emit_event SQL (لا يعيد اختراع العقد)
    assert set(args) == {
        "event_type",
        "entity_type",
        "entity_id",
        "tenant_id",
        "payload",
        "source",
        "actor_id",
        "command_id",
    }


@pytest.mark.unit
def test_new_event_captures_correlation_thread():
    es = _es()
    # نستورد نفس وحدة core.correlation التي يستوردها new_event (لا نسخة منفصلة)،
    # وإلّا اختلفت الـContextVar.
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    import core.correlation as cm  # noqa: PLC0415

    cm.set_correlation("corr-evt")
    env = es.new_event("ai.suggestion.generated", "field", _UUID, _UUID)
    assert env.correlation_id == "corr-evt"  # خيط التتبّع التُقط تلقائيّاً
