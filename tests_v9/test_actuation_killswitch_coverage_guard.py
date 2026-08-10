"""تكذيب حارس تغطية مفتاح الإيقاف (actuation_killswitch_coverage_guard).

يُثبِت أنّ الحارس:
- يمرّ على الشجرة الحاليّة (العيب المجمَّد `_compensate` مُسجَّل دَيناً معلَناً)؛
- يسقط على موضع إطلاق **جديد** غير مُغطّى وغير مُسجَّل (الحماية الفعليّة)؛
- يقبل موضعاً مُغطّى بالمفتاح؛
- يسقط على استثناء **بائت** صار مُغطّى (إنفاذ عكسيّ ⇒ يُنزَع فور هبوط الرقعة)؛
- لا يعدّ **تعريف** المُساعِد نفسه موضعَ إطلاق.

القياس سلوكيّ على الدالّة النقيّة `analyze` بمعطياتٍ مُركَّبة — لا يمسّ المسار الفيزيائيّ
المجمَّد ولا يعتمد على قاعدة أو خدمة.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_GUARD = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ci"
    / "actuation_killswitch_coverage_guard.py"
)
_spec = importlib.util.spec_from_file_location("akcg", _GUARD)
akcg = importlib.util.module_from_spec(_spec)
sys.modules["akcg"] = akcg
_spec.loader.exec_module(akcg)


# ── معطيات مُركَّبة ────────────────────────────────────────────────────────────
_UNCOVERED = """
async def emit_no_guard(device, cmd, payload):
    return await send_mqtt_command(device, cmd, payload)
"""

_COVERED = """
async def emit_with_guard(conn, device, cmd, payload, tenant_id):
    halted, reason = await is_actuation_halted(conn, tenant_id)
    if halted:
        return None
    return await send_mqtt_command(device, cmd, payload)
"""

_DEFINITION_ONLY = """
async def send_mqtt_command(device_id, command, payload):
    topic = f"sahool/actuator/{device_id}/command"
    return await mqtt.publish(topic, payload)
"""


def test_guard_passes_on_current_tree():
    """الشجرة الحاليّة: لا خطأ (العيب المجمَّد مُسجَّل، لا استثناء بائت)."""
    assert akcg.check() == []


def test_current_tree_reports_only_registered_frozen_debt():
    uncovered, stale = akcg.analyze(akcg._production_sources(), akcg.FROZEN_EXCEPTIONS)
    assert uncovered == [], f"مواضع غير مُسجَّلة غير متوقَّعة: {uncovered}"
    assert stale == [], f"استثناءات بائتة غير متوقَّعة: {stale}"
    # والعيب المجمَّد نفسه معلَن بمعرّف فجوته:
    assert (
        "services/actuator-service/actuator_runtime.py",
        "_compensate",
    ) in akcg.FROZEN_EXCEPTIONS


def test_unregistered_uncovered_callsite_is_flagged():
    """المطفرة الأساسيّة: موضع إطلاق جديد بلا مفتاح ⇒ يُرصَد."""
    uncovered, stale = akcg.analyze({"svc/new_path.py": _UNCOVERED}, exceptions={})
    assert ("svc/new_path.py", "emit_no_guard") in uncovered
    assert stale == []


def test_covered_callsite_is_accepted():
    uncovered, stale = akcg.analyze({"svc/ok.py": _COVERED}, exceptions={})
    assert uncovered == []
    assert stale == []


def test_registered_uncovered_callsite_is_not_flagged():
    """الدَّين المعلَن المجمَّد لا يكسر البوّابة."""
    exc = {("svc/new_path.py", "emit_no_guard"): "SOME-GAP-01"}
    uncovered, stale = akcg.analyze({"svc/new_path.py": _UNCOVERED}, exc)
    assert uncovered == []
    assert stale == []


def test_stale_exception_is_flagged():
    """إنفاذ عكسيّ: استثناء مُسجَّل صار مُغطّى ⇒ يُطالَب بنزعه."""
    exc = {("svc/ok.py", "emit_with_guard"): "SOME-GAP-01"}
    uncovered, stale = akcg.analyze({"svc/ok.py": _COVERED}, exc)
    assert uncovered == []
    assert ("svc/ok.py", "emit_with_guard") in stale


def test_emitter_definition_is_not_a_callsite():
    """تعريف المُساعِد نفسه ليس موضع إطلاق يُحرَس."""
    uncovered, stale = akcg.analyze({"svc/def.py": _DEFINITION_ONLY}, exceptions={})
    assert uncovered == []
    assert stale == []
