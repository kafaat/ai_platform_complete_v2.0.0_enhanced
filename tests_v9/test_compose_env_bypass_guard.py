"""حارس CI (SEC-1): منع اجتماع تجاوز RLS مع افتراض بيئة إنتاجيّة في أيّ compose.

الخلفيّة: ``docker-compose.fixed.yml`` يُفعّل ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` عمداً للتطوير
المحلّيّ (مسموح به في ``test_compose_rls_bypass_guard``). القدم الخفيّة (footgun): إن كان ملفّ
compose يُفعّل التجاوز *و* يُعيّن ``SAHOOL_ENV`` افتراضاً إلى ``production`` (سلسلة
``${SAHOOL_ENV:-production}`` أو قيمة حرفيّة ``production``)، فإنّ تشغيلاً عابراً يحصل على
بيئة إنتاجيّة + تجاوز عزل المستأجرين معاً — أسوأ اجتماع ممكن.

هذا الاختبار فحص ملفّات نقيّ (بلا Docker، بلا fastapi): يمسح كلّ ``docker-compose*.yml`` في
الجذر، وأيّ ملفّ يُفعّل التجاوز يجب ألّا يُعيّن ``SAHOOL_ENV`` إنتاجيّاً. يكمّل
``test_compose_rls_bypass_guard`` (ذاك يمنع التجاوز في الإنتاج؛ هذا يمنع افتراض بيئة
إنتاجيّة حيث التجاوز مسموح للتطوير).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# جذر المستودع (هذا الملفّ في tests_v9/ تحت الجذر مباشرةً).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_BYPASS_VAR = "SAHOOL_ALLOW_RLS_BYPASS_ROLE"
_ENV_VAR = "SAHOOL_ENV"
_TRUTHY = {"1", "true", "yes", "on"}


def _value_enables_bypass(raw_value: str) -> bool:
    """هل القيمة المسندة لـ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` تُفعّل التجاوز؟

    نفس منطق ``test_compose_rls_bypass_guard`` (مُكرَّر عمداً لإبقاء الحارسَين مستقلَّين).
    """
    v = raw_value.strip().strip("\"'").strip()
    m = re.fullmatch(r"\$\{[^:}-]+:?-(?P<default>[^}]*)\}", v)
    if m:
        return m.group("default").strip().strip("\"'").lower() in _TRUTHY
    if v.startswith("${") and v.endswith("}"):
        return False
    return v.lower() in _TRUTHY


def _env_defaults_production(raw_value: str) -> bool:
    """هل ``SAHOOL_ENV`` يُعيَّن (افتراضاً أو حرفيّاً) إلى ``production``؟

    يُغطّي: القيمة الحرفيّة ``production``، وصيغة الافتراض ``${SAHOOL_ENV:-production}``
    (أو ``${SAHOOL_ENV-production}``). ``${SAHOOL_ENV}`` بلا افتراض ⇒ يعتمد على البيئة
    الخارجيّة ولا يُعدّ افتراضاً إنتاجيّاً داخل الملفّ.
    """
    v = raw_value.strip().strip("\"'").strip()
    m = re.fullmatch(r"\$\{[^:}-]+:?-(?P<default>[^}]*)\}", v)
    if m:
        return m.group("default").strip().strip("\"'").lower() == "production"
    if v.startswith("${") and v.endswith("}"):
        return False
    return v.lower() == "production"


def _extract_env_value(stripped: str, var: str) -> str | None:
    """استخرج القيمة المسندة لمتغيّر بيئة من سطر compose (نمط خريطة أو قائمة)."""
    if stripped.startswith("#") or var not in stripped:
        return None
    if "=" in stripped and stripped.lstrip("- ").startswith(var):
        return stripped.split("=", 1)[1]
    if ":" in stripped and stripped.lstrip("- ").startswith(var):
        return stripped.split(":", 1)[1]
    return None


def _compose_enables_bypass(text: str) -> bool:
    for line in text.splitlines():
        value = _extract_env_value(line.strip(), _BYPASS_VAR)
        if value is not None and _value_enables_bypass(value):
            return True
    return False


def _compose_defaults_production_env(text: str) -> bool:
    for line in text.splitlines():
        value = _extract_env_value(line.strip(), _ENV_VAR)
        if value is not None and _env_defaults_production(value):
            return True
    return False


def _root_compose_files() -> list[Path]:
    files = sorted(_REPO_ROOT.glob("docker-compose*.yml"))
    assert files, "لم يُعثَر على أيّ docker-compose*.yml في جذر المستودع"
    return files


@pytest.mark.unit
def test_bypass_compose_never_defaults_production_env():
    """أيّ compose يُفعّل تجاوز RLS يجب ألّا يُعيّن SAHOOL_ENV افتراضاً إنتاجيّاً."""
    offenders = []
    for path in _root_compose_files():
        text = path.read_text(encoding="utf-8")
        if _compose_enables_bypass(text) and _compose_defaults_production_env(text):
            offenders.append(path.name)
    assert not offenders, (
        "ملفّات compose تجمع تجاوز RLS مع افتراض بيئة إنتاجيّة (production + bypass): "
        f"{offenders}. اجعل SAHOOL_ENV يفترض بيئة تطوير (${{SAHOOL_ENV:-development}}) "
        "في أيّ compose تطويريّ يُفعّل التجاوز — كي لا تجتمع البيئة الإنتاجيّة مع تعطيل العزل."
    )


@pytest.mark.unit
def test_fixed_compose_no_longer_enables_bypass():
    """v8-F9: ``docker-compose.fixed.yml`` صُلِّب — لم يعُد يُفعّل تجاوز RLS.

    (سابقاً كان يُفعّله للتطوير المحلّيّ لأنّه يتّصل بـsahool_user المُمتاز؛ الآن يتّصل
    بـsahool_app المقيّد الذي يُنشئه sahool-migrate، فلا حاجة لتعطيل حارس RLS.) الحارس
    الأعمّ ``test_bypass_compose_never_defaults_production_env`` يبقى فوق كلّ الملفّات.
    """
    path = _REPO_ROOT / "docker-compose.fixed.yml"
    assert path.exists(), "docker-compose.fixed.yml مفقود"
    text = path.read_text(encoding="utf-8")
    assert not _compose_enables_bypass(text), (
        "عاد docker-compose.fixed.yml لتفعيل SAHOOL_ALLOW_RLS_BYPASS_ROLE — "
        "احذفه؛ الاتّصال بـsahool_app المقيّد لا يحتاج تعطيل حارس RLS."
    )
