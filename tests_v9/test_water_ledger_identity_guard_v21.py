"""حارس هويّة عامل دفتر المياه في الإنتاج (CT-03 · تدقيق الحاويات V21).

يقفل مساراً مُثبَتاً: عامل ``water_ledger`` كان يُقلع بلا هويّة خدمة حتى مع تفعيل جسر
عجز الماء المحكوم في الإنتاج — فيطرق باب decision-service بلا ``SAHOOL_AGENT_TOKEN``
فيُرفَض (401) بينما العامل نفسه لا يفشل مُغلَقاً. الحارس يفرض:

  (1) الجسر مُفعّل + إنتاج + توكن فارغ ⇒ رسالة رفض تذكر المتغيّر المطلوب؛
  (2) التطوير بلا توكن ⇒ لا خطأ (لا يُحجَب محلّيّاً)؛
  (3) الجسر مُعطَّل ⇒ لا خطأ ولو في الإنتاج بلا توكن؛
  (4) توكن حاضر ⇒ لا خطأ؛
  (5) الرسالة لا تُسرّب قيمة التوكن أبداً، بل غيابه فقط؛
  (6) مسار الإقلاع (loop_worker/water_ledger) يستدعي الحارس ويرمي فعليّاً.

نُشغّل استيراد الوحدة في **مفسّر فرعيّ نظيف** (subprocess) لعزل البيئة وجعل الفحص
حتميّاً بصرف النظر عن ترتيب السويت. منطق صرف (subprocess + قراءة ملفّات) — ``pytest -m unit``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "services" / "sahool-platform" / "api" / "water_decision_bridge.py"
WORKER = ROOT / "services" / "sahool-platform" / "api" / "phase_runtime_workers.py"

# متغيّرات قد تُسرّب من بيئة المُشغّل وتُفسد الحتميّة — نُزيلها ما لم يضبطها الاختبار.
_VOLATILE = (
    "SAHOOL_ENV",
    "SAHOOL_AGENT_TOKEN",
    "WATER_DEFICIT_DECISION_BRIDGE_ENABLED",
    "WATER_LEDGER_REQUIRE_IDENTITY",
)


def _identity_error(env: dict[str, str]) -> str:
    """يستورد water_decision_bridge.py في مفسّر نظيف ويطبع نتيجة الحارس (فارغ = لا خطأ)."""
    prog = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('wdb', {str(BRIDGE)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "print('ERR::' + (m.water_ledger_identity_startup_error() or ''))\n"
    )
    # `encoding` على الأب يفكّ ما يصل، ولا يُملي على **الابن** بماذا يكتب: مخرَجه
    # يُرمَّز بترميز لغة الآلة، فرسالة تحوي عربيّة أو «—» تُسقِط الابن نفسه بـ
    # UnicodeEncodeError تحت لغة غير UTF-8. المتّجهان يُغلقان معاً أو لا يُغلق أيّهما.
    full_env = {**os.environ, "PYTHONIOENCODING": "utf-8", **env}
    for k in _VOLATILE:
        if k not in env:
            full_env.pop(k, None)
    r = subprocess.run(
        [sys.executable, "-c", prog],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=90,
        encoding="utf-8",
    )
    assert r.returncode == 0, f"import/probe failed: {r.stderr[-800:]}"
    for line in r.stdout.splitlines():
        if line.startswith("ERR::"):
            return line[len("ERR::") :]
    raise AssertionError(f"no ERR:: marker in output: {r.stdout!r}")


def test_bridge_on_production_empty_token_refuses_start():
    # الجسر مُفعّل + إنتاج + توكن فارغ ⇒ رفض يذكر المتغيّر المطلوب.
    msg = _identity_error(
        {"SAHOOL_ENV": "production", "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true"}
    )
    assert msg and "SAHOOL_AGENT_TOKEN" in msg


def test_development_stays_runnable():
    # تطوير بلا توكن ⇒ لا خطأ حتى مع تفعيل الجسر.
    assert (
        _identity_error(
            {"SAHOOL_ENV": "development", "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true"}
        )
        == ""
    )


def test_bridge_off_is_ok_even_in_production():
    # الجسر مُعطَّل ⇒ لا خطأ ولو في الإنتاج بلا توكن (لا دفع مرشّحات أصلاً).
    assert _identity_error({"SAHOOL_ENV": "production"}) == ""
    assert (
        _identity_error(
            {"SAHOOL_ENV": "production", "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "false"}
        )
        == ""
    )


def test_token_present_is_ok():
    # توكن حاضر في الإنتاج + الجسر مُفعّل ⇒ لا خطأ.
    assert (
        _identity_error(
            {
                "SAHOOL_ENV": "production",
                "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true",
                "SAHOOL_AGENT_TOKEN": "a-real-agent-token",
            }
        )
        == ""
    )


def test_explicit_flag_arms_check_outside_production():
    # علَم صريح يُسلّح الفحص خارج الإنتاج (لا fallback صامت).
    msg = _identity_error(
        {
            "SAHOOL_ENV": "development",
            "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true",
            "WATER_LEDGER_REQUIRE_IDENTITY": "true",
        }
    )
    assert msg and "SAHOOL_AGENT_TOKEN" in msg


def test_error_never_leaks_token_value():
    # حتى لو حُقن توكن ثمّ أُفرِغ منطقيّاً، الرسالة تصف الغياب ولا تطبع أيّ قيمة سرّ.
    secret = "operator-agent-token-should-never-appear"
    # توكن قويّ ⇒ لا رسالة رفض أصلاً، فلا مكان لتسريبه.
    assert (
        _identity_error(
            {
                "SAHOOL_ENV": "production",
                "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true",
                "SAHOOL_AGENT_TOKEN": secret,
            }
        )
        == ""
    )
    # مسار الرفض (توكن فارغ) ⇒ الرسالة لا تحوي قيمة سرّ اختباريّة.
    msg = _identity_error(
        {"SAHOOL_ENV": "production", "WATER_DEFICIT_DECISION_BRIDGE_ENABLED": "true"}
    )
    assert secret not in msg


def test_worker_startup_wires_hard_fail():
    # تحقّق ساكن: مسار إقلاع water_ledger يستدعي الحارس ويرمي فعليّاً (رفض إقلاع لا تحذير).
    src = WORKER.read_text(encoding="utf-8")
    assert "water_ledger_identity_startup_error" in src
    assert "raise RuntimeError(identity_error)" in src
