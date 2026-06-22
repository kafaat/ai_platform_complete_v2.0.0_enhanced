"""حارس CI: منع تفعيل تجاوز RLS في أيّ compose إنتاجيّ (فحص ملفّات نقيّ، بلا Docker).

الخلفيّة (FINDING-001): ``core/db_role_guard.enforcement_active`` fail-closed افتراضيّاً؛
ضبط ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` إلى قيمة truthy يُعطّل الفرض ⇒ ينهار عزل المستأجرين
صامتاً إن اتّصلت الخدمة بدور يتجاوز RLS. ``docker-compose.fixed.yml`` يُفعّله عمداً للتطوير
المحلّيّ (سلسلة ``${SAHOOL_ALLOW_RLS_BYPASS_ROLE:-1}`` على ~9 خدمات). أيّ compose آخر يجب
ألّا يُفعّله. هذا الاختبار يمسح كلّ ``docker-compose*.yml`` في جذر المستودع ويرفض أيّ
انحدار: compose جديد/مُعدَّل يُفعّل التجاوز (خارج قائمة السماح التطويريّة) يُفشِل الاختبار.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# جذر المستودع (هذا الملفّ في tests_v9/ تحت الجذر مباشرةً).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# قائمة السماح التطويريّة الصريحة: ملفّات compose يُسمَح لها بتفعيل تجاوز RLS (dev فقط).
# أيّ ملفّ خارجها يُعدّ هدفاً إنتاجيّاً محتملاً ⇒ يُمنَع عليه التفعيل.
_DEV_ALLOWLIST = {"docker-compose.fixed.yml"}

# نمط القيمة المُفعِّلة لـSAHOOL_ALLOW_RLS_BYPASS_ROLE داخل سطر environment في YAML.
# نلتقط القيمة المسندة (بعد ':' الأولى لاسم المتغيّر) ثمّ نقرّر إن كانت truthy/افتراض-truthy.
_VAR = "SAHOOL_ALLOW_RLS_BYPASS_ROLE"
_TRUTHY = {"1", "true", "yes", "on"}


def _value_enables_bypass(raw_value: str) -> bool:
    """هل القيمة المسندة لـ``SAHOOL_ALLOW_RLS_BYPASS_ROLE`` تُفعّل التجاوز؟

    تُغطّي: قيمة حرفيّة truthy (``1``/``true``/...)، وصيغة الافتراض في compose
    ``${VAR:-1}`` / ``${VAR:-true}`` (الافتراض truthy ⇒ ON إن لم تُضبَط البيئة).
    القيم falsy الصريحة (``0``/``false``) أو الافتراض falsy ``${VAR:-0}`` ⇒ لا تُفعّل.
    """
    v = raw_value.strip().strip("\"'").strip()
    # صيغة ${VAR:-default} أو ${VAR-default}: القرار على القيمة الافتراضيّة.
    m = re.fullmatch(r"\$\{[^:}-]+:?-(?P<default>[^}]*)\}", v)
    if m:
        return m.group("default").strip().strip("\"'").lower() in _TRUTHY
    # ${VAR} بلا افتراض ⇒ يعتمد على البيئة الخارجيّة؛ نعدّه غير مُفعِّل ضمن الملفّ نفسه.
    if v.startswith("${") and v.endswith("}"):
        return False
    return v.lower() in _TRUTHY


def _compose_enables_bypass(text: str) -> bool:
    """هل يحتوي نصّ compose على سطر يُفعّل ``SAHOOL_ALLOW_RLS_BYPASS_ROLE``؟"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or _VAR not in stripped:
            continue
        # نمط environment الخريطيّ: ``SAHOOL_ALLOW_RLS_BYPASS_ROLE: <value>``
        # أو نمط القائمة: ``- SAHOOL_ALLOW_RLS_BYPASS_ROLE=<value>``.
        if "=" in stripped and stripped.lstrip("- ").startswith(_VAR):
            value = stripped.split("=", 1)[1]
        elif ":" in stripped:
            value = stripped.split(":", 1)[1]
        else:
            continue
        if _value_enables_bypass(value):
            return True
    return False


def _root_compose_files() -> list[Path]:
    files = sorted(_REPO_ROOT.glob("docker-compose*.yml"))
    assert files, "لم يُعثَر على أيّ docker-compose*.yml في جذر المستودع"
    return files


@pytest.mark.unit
def test_no_prod_compose_enables_rls_bypass():
    """كلّ compose خارج قائمة السماح التطويريّة يجب ألّا يُفعّل تجاوز RLS."""
    offenders = []
    for path in _root_compose_files():
        if path.name in _DEV_ALLOWLIST:
            continue
        if _compose_enables_bypass(path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert not offenders, (
        "ملفّات compose إنتاجيّة تُفعّل SAHOOL_ALLOW_RLS_BYPASS_ROLE (يُبطِل عزل المستأجرين): "
        f"{offenders}. أزِل المتغيّر، أو أضِفه لقائمة السماح التطويريّة عمداً إن كان dev فقط."
    )


@pytest.mark.unit
def test_dev_allowlist_compose_actually_enables_bypass():
    """قائمة السماح ليست stale: كلّ ملفّ فيها يُفعّل التجاوز فعلاً (وإلّا فلا داعي لاستثنائه)."""
    for name in _DEV_ALLOWLIST:
        path = _REPO_ROOT / name
        assert path.exists(), f"ملفّ قائمة السماح غير موجود: {name}"
        assert _compose_enables_bypass(path.read_text(encoding="utf-8")), (
            f"{name} في قائمة السماح لكنّه لا يُفعّل التجاوز — أزِله من القائمة."
        )


@pytest.mark.unit
def test_fixed_compose_keeps_dev_only_warning():
    """``docker-compose.fixed.yml`` يحتفظ بتحذيره «تطوير محلّيّ فقط» — كي لا يصير هدفاً إنتاجيّاً صامتاً."""
    path = _REPO_ROOT / "docker-compose.fixed.yml"
    assert path.exists(), "docker-compose.fixed.yml مفقود"
    text = path.read_text(encoding="utf-8")
    assert "تطوير محلّيّ فقط" in text, (
        "اختفى تحذير «تطوير محلّيّ فقط» من docker-compose.fixed.yml — أعِده، "
        "فهو ما يبرّر تفعيل تجاوز RLS فيه (dev) ويمنع تحوّله لهدف إنتاجيّ."
    )
