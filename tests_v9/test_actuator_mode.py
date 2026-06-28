"""اختبار أوضاع المُشغِّل النقيّة (PR #394 ⇒ fail-safe) — resolve_actuator_mode.

real/simulation/disabled مع علم صريح؛ وعند **غياب العلم ⇒ fail-safe `simulation`**
(سلامة فيزيائيّة: وجود وسيط ≠ موافقة تشغيل، real يتطلّب opt-in صريحاً). يُختبَر حتميّاً.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]

from shared.actuator_mode import resolve_actuator_mode  # noqa: E402


# ── علم صريح صالح يُحترَم (غير حسّاس للحالة/المسافات) ──
def test_explicit_real():
    # علم real صريح ⇒ real حتى لو كان الوسيط معطّلاً (العلم يَغلِب الاستنتاج).
    assert resolve_actuator_mode("real", "") == "real"
    assert resolve_actuator_mode("real", "disabled") == "real"
    assert resolve_actuator_mode("real", "mqtt://broker:1883") == "real"


def test_explicit_simulation():
    # simulation صريح ⇒ simulation بصرف النظر عن الوسيط.
    assert resolve_actuator_mode("simulation", "mqtt://broker:1883") == "simulation"
    assert resolve_actuator_mode("simulation", "") == "simulation"
    assert resolve_actuator_mode("simulation", "disabled") == "simulation"


def test_explicit_disabled():
    assert resolve_actuator_mode("disabled", "mqtt://broker:1883") == "disabled"
    assert resolve_actuator_mode("disabled", "") == "disabled"


def test_explicit_case_and_whitespace_insensitive():
    assert resolve_actuator_mode(" Real ", "") == "real"
    assert resolve_actuator_mode("SIMULATION", "mqtt://b:1883") == "simulation"
    assert resolve_actuator_mode("  Disabled", "mqtt://b:1883") == "disabled"


# ── غياب العلم ⇒ fail-safe simulation (سلامة فيزيائيّة، يعكس PR #394 بوعي) ──
def test_unset_flag_is_failsafe_simulation():
    # لا علم ⇒ simulation مهما كان الوسيط (وجود وسيط ≠ موافقة تشغيل فيزيائيّ).
    assert resolve_actuator_mode(None, "mqtt://sahool-fastbee:1883") == "simulation"
    assert resolve_actuator_mode("", "mqtt://sahool-fastbee:1883") == "simulation"
    assert resolve_actuator_mode(None, "") == "simulation"
    assert resolve_actuator_mode(None, None) == "simulation"
    assert resolve_actuator_mode("", "   ") == "simulation"
    # broker_url لم يَعُد يُرجّح real (وُسِّع الافتراضيّ liberally للتوافق).
    assert resolve_actuator_mode(None) == "simulation"


def test_unknown_flag_is_failsafe_simulation():
    # علم مجهول ⇒ simulation (لا يُرفَع خطأ، لا يُرجّح real — الأكثر أماناً).
    assert resolve_actuator_mode("bogus", "mqtt://broker:1883") == "simulation"
    assert resolve_actuator_mode("xyz", "") == "simulation"
    assert resolve_actuator_mode("on", None) == "simulation"


def test_real_requires_explicit_opt_in():
    # real لا يقع إلّا بتعيين صريح — لا استنتاج من وجود الوسيط.
    assert resolve_actuator_mode("real", "mqtt://sahool-fastbee:1883") == "real"
    assert resolve_actuator_mode(None, "mqtt://sahool-fastbee:1883") != "real"
