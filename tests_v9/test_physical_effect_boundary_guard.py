"""تكذيب حارس حدّ الأثر الفيزيائيّ — BRAIN-ACTUATOR-BYPASS-UNGUARDED-01.

الحارس يُجمّد حدّاً **سليماً اليوم**، فقيمته كلّها في أنّه يسقط حين يُخرَق. لذا تُبنى
هنا المسارات الأربعة التي وسّعناه لأجلها (HTTP · موضوع أمر على وسيط · استيراد عميل
المُشغِّل · غلاف يُخفي النداء) ويُؤكَّد التقاط كلّ واحد منها، ثمّ تُبنى ثلاث حالات
مشروعة ويُؤكَّد **عدم** التقاطها — لأنّ حارساً يصطاد المشروع يُعطَّل بعد أسبوع.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "physical_effect_boundary_guard", ROOT / "scripts/ci/physical_effect_boundary_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)


def _emits(code: str) -> set[str]:
    executable = guard._executable_source(code)
    return {name for name, rx in guard.EMISSION.items() if rx.search(executable)}


def _reaches(code: str) -> set[str]:
    return guard.reach_categories(guard._executable_source(code))


# ───────────────────────── المسارات الأربعة تُلتقَط ─────────────────────────


def test_http_actuator_endpoint_is_caught():
    """(١) نداء HTTP مباشر إلى المُشغِّل."""
    code = 'async def go(c):\n    return await c.post("http://actuator-service/v1/commands")\n'
    assert "http_actuator_endpoint" in _emits(code)


def test_nats_command_subject_is_caught():
    """(٢) موضوع أمر على الوسيط — الثغرة التي لم تكن مغطّاة إطلاقاً."""
    code = 'async def go(js):\n    await js.publish("sahool.actuator.dispatch.requested", b"{}")\n'
    assert "broker_command_publish" in _emits(code)


def test_mqtt_command_topic_is_caught():
    """(٢-ب) موضوع MQTT للأمر كذلك."""
    code = 'def go(c, dev):\n    c.publish(f"sahool/actuator/{dev}/command", b"on")\n'
    assert "broker_command_publish" in _emits(code)


def test_direct_actuator_client_import_is_caught():
    """(٣) استيراد عميل المُشغِّل مباشرةً."""
    assert "actuator_client_import" in _reaches("from actuator_runtime import publish_command\n")
    assert "actuator_client_import" in _reaches("import actuator_command\n")


def test_hiding_wrapper_import_is_caught():
    """(٤) الغلاف/المُرحِّل: بلوغ الأثر عبر طبقة الإدراج بدل إصدار مرشّح."""
    assert "relay_indirection_import" in _reaches("from core.dispatch_executor import execute\n")
    assert "relay_indirection_import" in _reaches("from api import phase_runtime_workers\n")


# ─────────────────── الحالات المشروعة **لا** تُلتقَط ───────────────────


def test_decision_candidate_emission_is_not_caught():
    """إصدار مرشّح قرار: مواضيع recommendation.* إعلانُ دورة حياة لا أمر."""
    code = (
        'SUBJECTS = {"created": "recommendation.created", "executed": "recommendation.executed"}\n'
        "async def publish(client, ev):\n    await client.publish(ev.subject(), ev.to_bytes())\n"
    )
    assert _emits(code) == set()
    assert _reaches(code) == set()


def test_non_executive_audit_read_is_not_caught():
    """قراءة تدقيقيّة/حالة: تعداد استدعاءات المُشغِّل ليس إطلاقاً له."""
    code = (
        "async def get_actuator_audit(user):\n"
        "    tools = registry.list_by_side_effect(SideEffectClass.ACTUATOR)\n"
        "    return [e for e in journal if e.tool_id in tools]\n"
    )
    assert _emits(code) == set()


def test_side_effect_free_contract_is_not_caught():
    """تصنيف الأثر الجانبيّ: تسمية الخطر ليست ارتكابه."""
    code = (
        "class SideEffectClass:\n"
        '    ACTUATOR = "actuator"\n'
        'TOOL = dict(tool_id="actuator.pump.start", side_effects=SideEffectClass.ACTUATOR, max_retries=0)\n'
    )
    assert _emits(code) == set()


def test_docstring_naming_the_forbidden_path_is_not_caught():
    """التوثيق يسمّي الممنوع بالنفي مشروعاً — التجريد بالـAST هو ما يمنع الإيجابيّة الكاذبة."""
    code = '"""لا يُطلِق MQTT مباشرةً على sahool/actuator/{device_id}/command."""\nX = 1\n'
    assert _emits(code) == set()
    assert "sahool/actuator/" in code  # النصّ الخام يحمل الرمز فعلاً


# ─────────────────────── قواعد العقد نفسها ───────────────────────


def test_live_tree_is_clean():
    """الشجرة الحيّة خضراء — الحدّ سليم اليوم، والحارس يُجمّده."""
    assert guard.check() == []


def test_allowlist_entry_inside_a_brain_zone_is_rejected(monkeypatch):
    """لا يُعالَج خرقٌ بترخيصه: إدخال سماح داخل منطقة دماغ يُسقِط الفحص."""
    contract = guard._contract()
    contract["allowlist"] = contract["allowlist"] + [
        {"path": "services/mcp_servers/weather_server.py", "category": "x", "why": "y"}
    ]
    monkeypatch.setattr(guard, "_contract", lambda: contract)
    errors = guard.check()
    assert any("قائمة السماح تحمل ملفّاً داخل منطقة دماغ" in e for e in errors)


def test_stale_allowlist_entry_is_rejected(monkeypatch):
    """إنفاذ عكسيّ (كعقد #735): إدخال بلا مسار حيّ مطابق يُسقِط الفحص."""
    contract = guard._contract()
    contract["allowlist"] = contract["allowlist"] + [
        {"path": "services/actuator-service/does_not_exist.py", "category": "x", "why": "y"}
    ]
    monkeypatch.setattr(guard, "_contract", lambda: contract)
    errors = guard.check()
    assert any("إدخال سماح بلا مسار أثر حيّ مطابق" in e for e in errors)


def test_removing_an_allowlist_entry_makes_the_live_emitter_fail(monkeypatch):
    """المُطلِق الحيّ غير المُدرَج يُسقِط الفحص **بالاسم** — لا يمرّ صامتاً."""
    contract = guard._contract()
    dropped = contract["allowlist"][0]["path"]
    contract["allowlist"] = contract["allowlist"][1:]
    monkeypatch.setattr(guard, "_contract", lambda: contract)
    errors = guard.check()
    assert any(dropped in e and "غير مُدرَج" in e for e in errors)
