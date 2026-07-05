"""حارس CI: منع تفعيل تجاوز RLS + اتّصال دور مُمتاز في أيّ compose (فحص ملفّات نقيّ، بلا Docker).

الخلفيّة (FINDING-001): ``core/db_role_guard.enforcement_active`` fail-closed افتراضيّاً؛
ضبط ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` إلى قيمة truthy يُعطّل الفرض ⇒ ينهار عزل المستأجرين
صامتاً إن اتّصلت الخدمة بدور يتجاوز RLS.

**تصلّب v8-F9:** ``docker-compose.fixed.yml`` كان يُفعّل التجاوز عمداً ويتّصل بدور
``sahool_user`` المُمتاز (superuser) على ~9 خدمات. صار الآن يتّصل بدور ``sahool_app``
المقيّد (NOBYPASSRLS) الذي يُنشئه ``sahool-migrate`` (apply_in_compose.sh)، وأُزيل
التجاوز — فلا ملفّ compose يُفعّل التجاوز أو يستعمل ``sahool_user`` في ``DATABASE_URL``.
هذا الاختبار يمسح كلّ ``docker-compose*.yml`` في جذر المستودع ويرفض أيّ انحدار.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# جذر المستودع (هذا الملفّ في tests_v9/ تحت الجذر مباشرةً).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# لا قائمة سماح تطويريّة بعد الآن: v8-F9 صلّب fixed.yml فلم يعد أيّ compose يُفعّل التجاوز.
_DEV_ALLOWLIST: set[str] = set()

_VAR = "SAHOOL_ALLOW_RLS_BYPASS_ROLE"
_TRUTHY = {"1", "true", "yes", "on"}


def _value_enables_bypass(raw_value: str) -> bool:
    """هل القيمة المسندة لـ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` تُفعّل التجاوز؟"""
    v = raw_value.strip().strip("\"'").strip()
    m = re.fullmatch(r"\$\{[^:}-]+:?-(?P<default>[^}]*)\}", v)
    if m:
        return m.group("default").strip().strip("\"'").lower() in _TRUTHY
    if v.startswith("${") and v.endswith("}"):
        return False
    return v.lower() in _TRUTHY


def _compose_enables_bypass(text: str) -> bool:
    """هل يحتوي نصّ compose على سطر (غير تعليق) يُفعّل ``SAHOOL_ALLOW_RLS_BYPASS_ROLE``؟"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or _VAR not in stripped:
            continue
        if "=" in stripped and stripped.lstrip("- ").startswith(_VAR):
            value = stripped.split("=", 1)[1]
        elif ":" in stripped:
            value = stripped.split(":", 1)[1]
        else:
            continue
        if _value_enables_bypass(value):
            return True
    return False


def _database_url_uses_superuser(text: str) -> list[str]:
    """أسطر ``DATABASE_URL`` (غير تعليق) التي تتّصل بدور ``sahool_user`` المُمتاز."""
    hits = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "DATABASE_URL" in stripped and "postgresql://sahool_user:" in stripped:
            hits.append(stripped[:100])
    return hits


def _root_compose_files() -> list[Path]:
    files = sorted(_REPO_ROOT.glob("docker-compose*.yml"))
    assert files, "لم يُعثَر على أيّ docker-compose*.yml في جذر المستودع"
    return files


@pytest.mark.unit
def test_no_compose_enables_rls_bypass():
    """لا ملفّ compose (بلا استثناء بعد v8-F9) يُفعّل تجاوز RLS."""
    offenders = [
        path.name
        for path in _root_compose_files()
        if path.name not in _DEV_ALLOWLIST
        and _compose_enables_bypass(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "ملفّات compose تُفعّل SAHOOL_ALLOW_RLS_BYPASS_ROLE (يُبطِل عزل المستأجرين): "
        f"{offenders}. أزِل المتغيّر (الاتّصال بدور sahool_app المقيّد لا يحتاجه)."
    )


@pytest.mark.unit
def test_no_compose_database_url_uses_superuser_role():
    """v8-F9: لا خدمة في أيّ compose تتّصل بـ``sahool_user`` المُمتاز عبر ``DATABASE_URL``.

    الدور المُمتاز (مالك الجداول/superuser) يتجاوز RLS ما لم يُفرَض FORCE على كلّ جدول؛
    التطبيق يجب أن يتّصل بـ``sahool_app`` (NOBYPASSRLS) والعمّال بـ``sahool_jobs``.
    """
    offenders = {}
    for path in _root_compose_files():
        hits = _database_url_uses_superuser(path.read_text(encoding="utf-8"))
        if hits:
            offenders[path.name] = hits
    assert not offenders, (
        "خدمات تتّصل بـsahool_user المُمتاز عبر DATABASE_URL (تتجاوز RLS): "
        f"{offenders}. استبدله بـsahool_app (تطبيق) أو sahool_jobs (عمّال)."
    )


@pytest.mark.unit
def test_fixed_compose_marked_non_canonical():
    """``docker-compose.fixed.yml`` يبقى مُعلَّماً «ليس القانونيّ» — كي لا يُخلَط بـv9.yml الإنتاجيّ."""
    path = _REPO_ROOT / "docker-compose.fixed.yml"
    assert path.exists(), "docker-compose.fixed.yml مفقود"
    text = path.read_text(encoding="utf-8")
    assert "ليس القانونيّ" in text or "docker-compose.v9.yml" in text, (
        "اختفى تمييز fixed.yml عن الإنتاجيّ — أعِد الإشارة إلى أنّ القانونيّ هو docker-compose.v9.yml."
    )
