"""حارس تصلّب الحاويات (SEC-2): كلّ ``services/*/Dockerfile`` يجب أن يعمل كمستخدم
غير جذريّ.

تشغيل الحاوية كـ``root`` يوسّع سطح الهجوم: أيّ ثغرة تنفيذ كود تمنح صلاحيّات الجذر
داخل الحاوية (كسر عزل أسهل، كتابة على نظام الملفّات، تصعيد إن اقترن بخطأ في الـ
runtime). الاصطلاح المُرسَّخ في المستودع هو مستخدم ``sahool`` (وفي حالة واحدة
``appuser``) عبر ``RUN useradd -m … && chown -R … /app`` ثمّ ``USER``.

هذا الحارس ساكن (مسح نصّيّ صرف، بلا استيراد fastapi ولا بناء صور) — وظيفة Unit
Tests. لكلّ ``Dockerfile`` نأخذ آخر تعليمة ``USER`` سارية (last-USER-wins، كما يفعل
Docker) ونؤكّد أنّها ليست ``root`` ولا ``0`` (ولا UID جذريّ). أرضيّة أمان: يجب
العثور على ≥20 ملفّ ``Dockerfile`` كي لا يمرّ الحارس فارغًا بصمت.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SERVICES = _ROOT / "services"

# تعليمة USER (تتجاهل السطور الفارغة/التعليقات). تلتقط الاسم/الـUID الأوّل فقط
# (Docker يسمح بـ``USER user:group`` — المستخدم هو ما قبل النقطتين).
_USER_DIRECTIVE = re.compile(r"^\s*USER\s+([^\s:]+)", re.IGNORECASE | re.MULTILINE)

# الحدّ الأدنى المتوقَّع لعدد صور الخدمات — شبكة أمان ضدّ حارس فارغ بصمت.
_MIN_SERVICE_DOCKERFILES = 20

# قائمة سماح موثّقة لخدمات تحتاج الجذر شرعًا. مُفضَّل أن تبقى فارغة؛ أضِف مدخلًا
# مع سبب واضح فقط إن كانت خدمة تتطلّب الجذر فعلًا (مثلًا ربط منفذ مميّز <1024).
# لا يوجد حاليًّا ما يبرّر ذلك (كلّ الخدمات خلف nginx على منافذ >1024).
_ROOT_ALLOWLIST: dict[str, str] = {}

# قيم USER التي تُعدّ جذريّة (اسم أو UID).
_ROOT_VALUES = {"root", "0"}


def _service_dockerfiles() -> list[Path]:
    if not _SERVICES.is_dir():
        return []
    return sorted(
        d / "Dockerfile" for d in _SERVICES.iterdir() if d.is_dir() and (d / "Dockerfile").is_file()
    )


def _effective_user(dockerfile_text: str) -> str | None:
    """آخر تعليمة ``USER`` سارية (last-USER-wins)، أو None إن غابت كليًّا."""
    matches = _USER_DIRECTIVE.findall(dockerfile_text)
    return matches[-1].strip() if matches else None


def test_all_service_dockerfiles_run_nonroot():
    dockerfiles = _service_dockerfiles()

    # شبكة أمان: الحارس ليس فارغًا بصمت.
    assert len(dockerfiles) >= _MIN_SERVICE_DOCKERFILES, (
        f"عُثر على {len(dockerfiles)} ملفّ Dockerfile فقط تحت services/؛ "
        f"المتوقَّع ≥{_MIN_SERVICE_DOCKERFILES}. تحقّق من المسار أو من انحدار حذف خدمات."
    )

    offenders: list[str] = []
    for dockerfile in dockerfiles:
        service = dockerfile.parent.name
        user = _effective_user(dockerfile.read_text(encoding="utf-8"))

        if service in _ROOT_ALLOWLIST:
            continue

        if user is None:
            offenders.append(f"{service}: لا توجد تعليمة USER (يعمل كـ root افتراضًا)")
        elif user.lower() in _ROOT_VALUES:
            offenders.append(f"{service}: USER={user} (جذريّ)")

    assert not offenders, "خدمات تعمل كـ root (SEC-2):\n  " + "\n  ".join(offenders)


def test_root_allowlist_entries_are_real_services():
    """أيّ مدخل في قائمة السماح يجب أن يشير إلى خدمة موجودة فعلًا (يمنع تعفّن القائمة)."""
    for service in _ROOT_ALLOWLIST:
        assert (_SERVICES / service / "Dockerfile").is_file(), (
            f"قائمة سماح الجذر تشير إلى خدمة غير موجودة: {service}"
        )
