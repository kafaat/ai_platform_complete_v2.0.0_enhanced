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

# مَفصِلٌ واحد داخل الوحدة — شكلُ رقعة M-01 بعينه.
_COVERED_VIA_HINGE = """
async def _consult(conn, tenant_id, field_id, valve_id):
    return await is_actuation_halted(conn, tenant_id, field_id=field_id, valve_id=valve_id)

async def emit_via_hinge(conn, device, cmd, payload, tenant_id, field_id):
    halted, reason = await _consult(conn, tenant_id, field_id, device)
    if halted:
        return None
    return await send_mqtt_command(device, cmd, payload)
"""

# مَفصِلان متتاليان — خارج المدى المُعلَن (مستوىً واحد).
_COVERED_VIA_TWO_HOPS = """
async def _inner(conn, tenant_id):
    return await is_actuation_halted(conn, tenant_id)

async def _outer(conn, tenant_id):
    return await _inner(conn, tenant_id)

async def emit_via_two_hops(conn, device, cmd, payload, tenant_id):
    halted, reason = await _outer(conn, tenant_id)
    if halted:
        return None
    return await send_mqtt_command(device, cmd, payload)
"""

# المَفصِل في وحدةٍ أخرى — لا يُعَدّ (يقتضي حلّ الاستيرادات).
_HINGE_IN_ANOTHER_MODULE = """
from .helpers import consult_elsewhere

async def emit_via_foreign_hinge(conn, device, cmd, payload, tenant_id):
    halted, reason = await consult_elsewhere(conn, tenant_id)
    if halted:
        return None
    return await send_mqtt_command(device, cmd, payload)
"""


def test_guard_passes_on_current_tree():
    """الشجرة الحاليّة: لا خطأ (العيب المجمَّد مُسجَّل، لا استثناء بائت)."""
    assert akcg.check() == []


def test_current_tree_has_no_uncovered_and_no_stale_licence():
    uncovered, stale = akcg.analyze(akcg._production_sources(), akcg.FROZEN_EXCEPTIONS)
    assert uncovered == [], f"مواضع غير مُسجَّلة غير متوقَّعة: {uncovered}"
    assert stale == [], f"استثناءات بائتة غير متوقَّعة: {stale}"


def test_the_compensation_path_is_no_longer_licensed_to_fire_unguarded():
    """الترخيص يُنزَع بزوال سببه — وإلّا رخّص لعطلٍ لم يعد قائماً.

    كان هذا التأكيد يفرض **وجود** `_compensate` في `FROZEN_EXCEPTIONS`، فصار بعد
    هبوط الرقعة يُثبِّت ترخيصاً ميّتاً: من ينزع الاستشارة غداً يمرّ أخضر.
    """
    key = ("services/actuator-service/actuator_runtime.py", "_compensate")
    assert key not in akcg.FROZEN_EXCEPTIONS, (
        "`_compensate` صار يستشير المفتاح ⇒ لا يجوز بقاء ترخيصه"
    )


def test_the_compensation_path_reads_as_covered_through_its_hinge():
    """التغطية الحقيقيّة عبر `_consult_killswitch` — لا استدعاءٌ مباشر.

    هذه هي الحالة التي أخفق فيها الإنفاذ العكسيّ أوّل مرّة: الحارس كان يقرأ
    الاستدعاء المباشر وحده، فقرأ الرقعة «غير مُغطّاة» وأبقى الترخيص حيّاً.
    """
    sources = akcg._production_sources()
    rel = "services/actuator-service/actuator_runtime.py"
    uncovered, stale = akcg.analyze(sources, {(rel, "_compensate"): "SOME-GAP-01"})
    assert (rel, "_compensate") in stale, (
        "لو قُرِئت غير مُغطّاة لَما بات الاستثناء — وهو العمى بعينه"
    )


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


def test_coverage_through_one_same_module_hinge_is_accepted():
    """مَفصِلٌ واحد داخل الوحدة تغطيةٌ — وإلّا اتُّهِمت رقعةٌ صحيحة زوراً."""
    uncovered, stale = akcg.analyze({"svc/hinge.py": _COVERED_VIA_HINGE}, exceptions={})
    assert uncovered == [], f"اتّهامٌ كاذب لدالّة تستشير عبر مَفصِل: {uncovered}"
    assert stale == []


def test_a_licence_over_a_hinge_covered_function_is_reported_stale():
    """الحالة التي أخفق فيها الإنفاذ العكسيّ: التغطية عبر مَفصِل ⇒ الترخيص بائت."""
    exc = {("svc/hinge.py", "emit_via_hinge"): "SOME-GAP-01"}
    uncovered, stale = akcg.analyze({"svc/hinge.py": _COVERED_VIA_HINGE}, exc)
    assert uncovered == []
    assert ("svc/hinge.py", "emit_via_hinge") in stale


def test_two_hop_indirection_is_not_counted_as_coverage():
    """حدٌّ مُعلَن يُقاس: مستوىً واحد لا سلسلة — لا نزعم ما لا نتتبّع."""
    uncovered, stale = akcg.analyze({"svc/two.py": _COVERED_VIA_TWO_HOPS}, exceptions={})
    assert ("svc/two.py", "emit_via_two_hops") in uncovered


def test_a_hinge_in_another_module_is_not_counted_as_coverage():
    """حدٌّ ثانٍ مُعلَن: المَفصِل يُجمَع من الوحدة نفسها، فالمستورَد لا يُعَدّ."""
    uncovered, stale = akcg.analyze(
        {"svc/foreign.py": _HINGE_IN_ANOTHER_MODULE}, exceptions={}
    )
    assert ("svc/foreign.py", "emit_via_foreign_hinge") in uncovered
