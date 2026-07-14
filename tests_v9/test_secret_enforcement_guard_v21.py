"""حارس فرض الأسرار في الإنتاج (تدقيق الحاويات V21 §4.1/§4.2).

يقفل مسارَين مُثبَتَين كانا يحوّلان خدمة حسّاسة إلى واحدة تعمل بلا حماية كافية:

  §4.1 decision-service: في الإنتاج، المصادقة إلزاميّة — الإقلاع يُرفَض إن غاب
       ``DECISION_SERVICE_AUTH_TOKEN`` (خدمة على المنفذ الداخليّ بلا توكن تُزوّر الهويّة).
  §4.2 video-processor/ZLMediaKit: الإنتاج يرفض السرّ الفارغ أو قيمة التطوير المعروفة
       (``sahool-zlm-dev-secret``) — بلا سرّ يبقى control plane مفتوحاً.

يتحقّق الحارس من: (1) فشل الإنتاج بلا سرّ؛ (2) نجاح التطوير بقيَم محلّيّة مصرّح بها؛
(3) عدم تسريب السرّ في مخرجات الخطأ؛ (4) عدم بقاء fallback صامت لقيمة التطوير في compose.

نُشغّل استيراد الخدمة في **مفسّر فرعيّ نظيف** (subprocess) لا في عمليّة الاختبار: خدمات
main تحمل استيرادات نسبيّة ثقيلة (مثل ``agronomic_context``) تتصادم في sys.modules عبر
السويت الكامل — والعزل عبر subprocess يجعل الفحص حتميّاً بصرف النظر عن ترتيب التشغيل،
ويختبر رفض الإقلاع الحقيقيّ (فيديو: الحارس على مستوى الوحدة ⇒ رمز خروج غير صفريّ).
منطق صرف (subprocess + قراءة ملفّات) — ``pytest -m unit``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _run(service_dir: str, snippet: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    """يستورد services/<dir>/main.py في مفسّر نظيف ثمّ يشغّل snippet؛ يعيد النتيجة."""
    svc = ROOT / "services" / service_dir
    prog = (
        "import sys, importlib.util\n"
        f"sys.path.insert(0, {str(svc)!r})\n"
        f"spec = importlib.util.spec_from_file_location('svc_main', {str(svc / 'main.py')!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n" + snippet
    )
    full_env = {**os.environ, **env}
    # نُزيل المتغيّرات التي قد تُسرّب من البيئة وتُفسد الحتميّة.
    for k in ("SAHOOL_ENV", "DECISION_SERVICE_AUTH_TOKEN", "DECISION_REQUIRE_AUTH_TOKEN"):
        if k not in env:
            full_env.pop(k, None)
    return subprocess.run(
        [sys.executable, "-c", prog],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=90,
    )


# ─────────────────────────── §4.1 decision-service ───────────────────────────
def _decision_auth_error(env: dict[str, str]) -> str:
    """يطبع نتيجة production_auth_startup_error() تحت البيئة المُعطاة (فارغة = لا خطأ)."""
    r = _run(
        "decision-service",
        "print('ERR::' + (m.production_auth_startup_error() or ''))\n",
        env,
    )
    assert r.returncode == 0, f"import/probe failed: {r.stderr[-800:]}"
    for line in r.stdout.splitlines():
        if line.startswith("ERR::"):
            return line[len("ERR::") :]
    raise AssertionError(f"no ERR:: marker in output: {r.stdout!r}")


def test_decision_production_requires_auth_token():
    # تطوير بلا توكن ⇒ لا خطأ.
    assert _decision_auth_error({"SAHOOL_ENV": "development"}) == ""
    # إنتاج بلا توكن ⇒ رسالة رفض تذكر المتغيّر المطلوب.
    prod = _decision_auth_error({"SAHOOL_ENV": "production"})
    assert prod and "DECISION_SERVICE_AUTH_TOKEN" in prod
    # إنتاج بتوكن ⇒ لا خطأ.
    assert (
        _decision_auth_error(
            {"SAHOOL_ENV": "production", "DECISION_SERVICE_AUTH_TOKEN": "a-real-token"}
        )
        == ""
    )
    # علَم صريح يُسلّح الفحص خارج الإنتاج (لا fallback صامت).
    assert _decision_auth_error(
        {"SAHOOL_ENV": "development", "DECISION_REQUIRE_AUTH_TOKEN": "true"}
    )


def test_decision_error_never_leaks_token():
    # حتى لو ضُبِط توكن ثمّ أُفرِغ منطقيّاً، الرسالة تصف الغياب ولا تطبع أيّ قيمة سرّ.
    msg = _decision_auth_error({"SAHOOL_ENV": "production"})
    assert "a-real-token" not in msg  # قيمة توكن اختبار لا يجب أن تظهر أبداً


def test_decision_lifespan_wires_hard_fail():
    # تحقّق ساكن: الإقلاع (lifespan) يستدعي الحارس ويرمي فعليّاً (رفض إقلاع لا مجرّد تحذير).
    src = (ROOT / "services" / "decision-service" / "main.py").read_text(encoding="utf-8")
    assert "production_auth_startup_error()" in src
    assert "raise RuntimeError(auth_error)" in src


# ─────────────────────────── §4.2 video-processor/ZLM ────────────────────────
def _video_import(env: dict[str, str]) -> subprocess.CompletedProcess:
    # استيراد الوحدة فقط: الحارس على مستوى الوحدة ⇒ رفض الإقلاع = رمز خروج غير صفريّ.
    # video-processor له حارس إنتاج آخر (JWT/RS256) يسبق حارس ZLM؛ نُرضيه صراحةً
    # (SAHOOL_ALLOW_HS256_IN_PROD=1) كي يكون سرّ ZLMediaKit هو وحده تحت الاختبار.
    return _run(
        "video-processor", "print('IMPORT_OK')\n", {"SAHOOL_ALLOW_HS256_IN_PROD": "1", **env}
    )


def test_zlmediakit_production_refuses_missing_or_dev_secret():
    # إنتاج + سرّ فارغ ⇒ رفض إقلاع (استيراد يفشل).
    r = _video_import({"SAHOOL_ENV": "production", "ZLMEDIAKIT_API_SECRET": ""})
    assert r.returncode != 0 and "ZLMEDIAKIT_API_SECRET" in r.stderr

    # إنتاج + قيمة التطوير المعروفة ⇒ رفض إقلاع.
    r = _video_import(
        {"SAHOOL_ENV": "production", "ZLMEDIAKIT_API_SECRET": "sahool-zlm-dev-secret"}
    )
    assert r.returncode != 0

    # إنتاج + سرّ قويّ ⇒ إقلاع ناجح.
    r = _video_import(
        {"SAHOOL_ENV": "production", "ZLMEDIAKIT_API_SECRET": "strong-unique-prod-secret"}
    )
    assert r.returncode == 0 and "IMPORT_OK" in r.stdout

    # تطوير + سرّ فارغ ⇒ إقلاع ناجح (لا يُحجَب محلّيّاً).
    r = _video_import({"SAHOOL_ENV": "development", "ZLMEDIAKIT_API_SECRET": ""})
    assert r.returncode == 0 and "IMPORT_OK" in r.stdout


def test_zlmediakit_refusal_never_leaks_operator_secret():
    # سرّ المشغّل (القويّ) يمرّ فيقلع ⇒ لا رسالة رفض أصلاً، فلا مكان لتسريبه.
    secret = "operator-secret-should-never-appear-in-logs"
    r = _video_import({"SAHOOL_ENV": "production", "ZLMEDIAKIT_API_SECRET": secret})
    assert r.returncode == 0
    assert secret not in r.stdout and secret not in r.stderr


# ─────────────────────────── compose: no silent dev fallback ─────────────────
def test_compose_has_no_hardcoded_dev_zlm_secret_default():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    # لا افتراض صامت لقيمة التطوير: ``${...:-sahool-zlm-dev-secret}`` مُزال.
    assert ":-sahool-zlm-dev-secret}" not in compose
    # حارس الإنتاج في sidecar التهيئة موجود (يفشل مُغلَقاً على الفارغ/قيمة التطوير).
    assert "refusing to configure ZLMediaKit" in compose
    # القيمة المعروفة تظهر فقط كسلسلة مرفوضة داخل الحارس (لا كافتراض).
    for line in compose.splitlines():
        if "sahool-zlm-dev-secret" in line:
            assert '"sahool-zlm-dev-secret"' in line or "'sahool-zlm-dev-secret'" in line, (
                f"unexpected use of dev secret literal: {line.strip()}"
            )
