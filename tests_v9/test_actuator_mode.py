"""اختبار أوضاع المُشغِّل النقيّة (PR #394) — resolve_actuator_mode.

نمط الإغلاق المرن: real/simulation/disabled مع **حفظ السلوك الحاليّ** عند غياب العلم
(الاستنتاج من broker_url). يُختبَر حتميّاً بلا قاعدة ولا شبكة ولا بيئة.
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


# ── الاستنتاج من broker_url عند غياب العلم (يحفظ السلوك الحاليّ تماماً) ──
def test_inferred_real_when_broker_present():
    # لا علم + وسيط حقيقيّ ⇒ real (السلوك الحاليّ: ينشر فعليّاً).
    assert resolve_actuator_mode(None, "mqtt://sahool-fastbee:1883") == "real"
    assert resolve_actuator_mode("", "mqtt://sahool-fastbee:1883") == "real"


def test_inferred_disabled_when_broker_empty_or_disabled():
    # لا علم + وسيط فارغ/معطّل ⇒ disabled (السلوك الحاليّ: لا عمليّة، يُعيد False).
    assert resolve_actuator_mode(None, "") == "disabled"
    assert resolve_actuator_mode(None, None) == "disabled"
    assert resolve_actuator_mode("", "   ") == "disabled"
    assert resolve_actuator_mode(None, "disabled") == "disabled"
    assert resolve_actuator_mode(None, "disabled://whatever") == "disabled"


# ── قيمة مجهولة ⇒ تُتجاهَل ويُستنتَج من الوسيط (لا تُكسر، تتحفّظ) ──
def test_unknown_flag_falls_back_to_inference():
    # علم مجهول + وسيط حقيقيّ ⇒ يُستنتَج real (لا يُرفَع خطأ، لا يُعطَّل صامتاً).
    assert resolve_actuator_mode("bogus", "mqtt://broker:1883") == "real"
    # علم مجهول + لا وسيط ⇒ disabled (الأكثر تحفّظاً).
    assert resolve_actuator_mode("xyz", "") == "disabled"
    assert resolve_actuator_mode("on", None) == "disabled"
