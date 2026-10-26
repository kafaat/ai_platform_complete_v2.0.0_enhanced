"""FIELD-WEATHER-OVERLAY-HAS-A-READER-AND-NO-WRITER-01 — حالاتُ القارئ نقيّةً.

**العطل:** ``weather-signal-engine`` يقرأ ``field_weather_overlay`` ولا شيء في الشجرة
يكتبه. فكانت كلُّ دورةٍ تُسجّل «أُدرِجَت 0 إشارة» بمستوى INFO — سطرٌ يُقرَأ «لا خطر
طقسيّ» وحقيقتُه «لا بيانات». والكاتبُ لا يُضاف بلا قرار المالك ولا بلا هجرة (المخطّط لا
يحمل الساعات المُقيَّمة)، فالقارئ يُعلِن حالته بالاسم بدل أن يصمت.

هنا المنطقُ النقيّ وحده (``classify_cycle`` · ``describe_cycle`` · ``is_evaluable``)؛
ومسارُ الدورة نفسها مُختبَرٌ في ``test_signal_cycle_survives_one_bad_row.py``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "weather-signal-engine" / "src" / "main.py"


def _load_engine():
    """يُحمِّل العامل مع تعويضِ تبعيّتين لا يمسّهما المنطقُ محلَّ الاختبار."""
    stubs = {
        "asyncpg": types.ModuleType("asyncpg"),
        "core": types.ModuleType("core"),
        "core.weather_overlay_pipeline": types.ModuleType("core.weather_overlay_pipeline"),
    }
    stubs["core.weather_overlay_pipeline"].build_signal_records = lambda *a, **k: []
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("wx_signal_engine_states", SRC)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


engine = _load_engine()


def test_no_rows_ever_is_no_overlay_data():
    report = engine.classify_cycle(overlays=0, signals=0, newest_overlay_at=None)
    assert report.state == engine.STATE_NO_OVERLAY_DATA


def test_old_rows_only_is_stale_not_no_data():
    stamp = datetime(2026, 10, 1, tzinfo=UTC)
    report = engine.classify_cycle(overlays=0, signals=0, newest_overlay_at=stamp)
    assert report.state == engine.STATE_STALE_OVERLAY_DATA
    assert report.newest_overlay_at == stamp


def test_fresh_rows_that_cannot_be_evaluated_are_named():
    report = engine.classify_cycle(overlays=4, signals=0, unevaluable=4)
    assert report.state == engine.STATE_OVERLAY_NOT_EVALUABLE


def test_signals_produced_is_processed():
    assert engine.classify_cycle(overlays=2, signals=3).state == engine.STATE_PROCESSED
    # صفوفٌ قابلةٌ للتقييم لم تُطلِق إشارة = طقسٌ هادئٌ مرصود، لا «لا بيانات».
    assert engine.classify_cycle(overlays=2, signals=0).state == engine.STATE_PROCESSED


@pytest.mark.parametrize(
    ("overlay", "expected"),
    [
        ({"field_id": "f1"}, False),  # ما يُعيده استعلامُ v74 اليوم: لا عمود
        ({"hours_evaluated": 0}, False),
        ({"hours_evaluated": None}, False),
        ({"hours_evaluated": 12}, True),
    ],
)
def test_is_evaluable_requires_positive_evaluated_hours(overlay, expected):
    assert engine.is_evaluable(overlay) is expected


@pytest.mark.parametrize(
    "state",
    ["STATE_NO_OVERLAY_DATA", "STATE_STALE_OVERLAY_DATA", "STATE_OVERLAY_NOT_EVALUABLE"],
)
def test_a_no_signal_state_warns_on_entry_and_names_the_gap(state):
    report = engine.CycleReport(state=getattr(engine, state))
    level, msg = engine.describe_cycle(report, previous_state=None)
    assert level == logging.WARNING
    assert report.state in msg
    assert engine.GAP_ID in msg


def test_a_persisting_no_signal_state_does_not_rewarn_every_cycle():
    report = engine.CycleReport(state=engine.STATE_NO_OVERLAY_DATA)
    level, msg = engine.describe_cycle(report, previous_state=engine.STATE_NO_OVERLAY_DATA)
    assert level == logging.INFO
    assert engine.STATE_NO_OVERLAY_DATA in msg, "الحالةُ تُسمّى في كلّ دورة ولو بلا تحذير"


def test_processed_is_info_with_counts():
    report = engine.CycleReport(state=engine.STATE_PROCESSED, overlays=2, signals=5)
    level, msg = engine.describe_cycle(report, previous_state=engine.STATE_NO_OVERLAY_DATA)
    assert level == logging.INFO
    assert "5" in msg and engine.STATE_PROCESSED in msg
