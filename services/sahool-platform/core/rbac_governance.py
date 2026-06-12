"""core/rbac_governance.py — حوكمة الأذونات: الاستعلام العكسي + معاينة التغيير.

الفكرة (مُستلهَمة من ممارسات RBAC متعدّد المستأجرين الموثّقة — WorkOS/NinjaOne/
techosquare — لا من ContiNew كأداة): RBAC وحده لا يكفي؛ يحتاج **حوكمة**:
  • الإجابة الفوريّة على "من يستطيع تنفيذ X؟" (effective access query)
  • معاينة أثر تغيير دور **قبل** تطبيقه (Preview → Validate → Apply)
  • تمييز الصلاحيّات الحرجة (السلامة) التي يجب أن تُمنَح بحذر

ما يبنيه (الفجوة المسدودة):
  • authorization.has_permission (هل هذا يقدر؟) ✓ موجود
  • authorization.audit_user_permissions (ماذا يقدر هذا؟) ✓ موجود
  • **who_can(permission)** (من يقدر على X؟) ✗ — السؤال الأمني الجوهري
  • **معاينة تغيير الدور** (ما الذي يكتسبه/يفقده؟) ✗

⚠ المبدأ:
  • حتمي بالكامل: استعلام على _ROLE_PERMISSIONS (مصدر واحد للحقيقة)
  • معاينة قبل تطبيق (لا تغيير صلاحيّة أعمى)
  • تمييز الصلاحيّات الحرجة (PESTICIDE_APPROVE/HARVEST_AUTHORIZE/USER_CHANGE_ROLE)
  • لا يستبدل auth — يضيف طبقة حوكمة/شفافيّة فوقه

⚠ هذا للحوكمة والشفافيّة. الفرض الفعلي يبقى في require_permission (auth).
"""

from __future__ import annotations

from core.authorization import (
    _ROLE_PERMISSIONS,
    Permission,
    UserRole,
    is_safety_critical_permission,
)


def who_can(permission: Permission) -> dict:
    """يُجيب: أيّ الأدوار تملك هذه الصلاحيّة؟ (الاستعلام العكسي الأمني).

    السؤال الذي تؤكّده كلّ مصادر RBAC: "من يستطيع تنفيذ X؟" — للتدقيق الأمني.
    """
    roles_with = [role.value for role, perms in _ROLE_PERMISSIONS.items() if permission in perms]
    return {
        "permission": permission.value,
        "roles_with_permission": roles_with,
        "role_count": len(roles_with),
        "is_safety_critical": is_safety_critical_permission(permission),
        "note_ar": (
            f"{len(roles_with)} دور يملك '{permission.value}'. "
            + (
                "⚠ صلاحيّة حرجة (سلامة) — راجع من يملكها بعناية."
                if is_safety_critical_permission(permission)
                else "صلاحيّة عاديّة."
            )
        ),
    }


def permission_matrix() -> dict:
    """مصفوفة كاملة: كلّ دور × كلّ صلاحيّة (شفافيّة كاملة للحوكمة).

    يُجيب على "من يقدر على ماذا" لكلّ النظام دفعةً — للتدقيق الدوري.
    """
    all_perms = sorted(
        {p for perms in _ROLE_PERMISSIONS.values() for p in perms}, key=lambda p: p.value
    )
    matrix = {}
    for role in _ROLE_PERMISSIONS:
        matrix[role.value] = {
            "permissions": sorted(p.value for p in _ROLE_PERMISSIONS[role]),
            "count": len(_ROLE_PERMISSIONS[role]),
            "has_safety_critical": any(
                is_safety_critical_permission(p) for p in _ROLE_PERMISSIONS[role]
            ),
        }
    return {
        "roles": list(matrix.keys()),
        "total_permissions": len(all_perms),
        "matrix": matrix,
        "safety_critical_permissions": sorted(
            p.value for p in all_perms if is_safety_critical_permission(p)
        ),
    }


def preview_role_change(current_role: str, new_role: str) -> dict:
    """يعاين أثر تغيير دور **قبل** تطبيقه: ما يُكتسَب/يُفقَد (Preview→Apply).

    مبدأ RBAC: لا تغيير صلاحيّة أعمى. يُظهر بالضبط ما سيتغيّر، مع تنبيه
    إن كان التغيير يمنح صلاحيّات حرجة (تصعيد) أو يسحبها.
    """
    try:
        cur = UserRole(current_role)
        new = UserRole(new_role)
    except ValueError as e:
        return {"error_ar": f"دور غير صالح: {e}"}

    cur_perms = _ROLE_PERMISSIONS.get(cur, set())
    new_perms = _ROLE_PERMISSIONS.get(new, set())

    gained = new_perms - cur_perms
    lost = cur_perms - new_perms

    gained_critical = [p.value for p in gained if is_safety_critical_permission(p)]
    lost_critical = [p.value for p in lost if is_safety_critical_permission(p)]

    # تصعيد = اكتساب أيّ صلاحيّة جديدة (لا مقارنة أعداد فقط): قد يكتسب الدور
    # الجديد صلاحيّة حرجة مع بقاء العدد ثابتاً لفقدانه أخرى — وذلك تصعيد يستحقّ
    # المراجعة. أيّ مكسب صلاحيّة = اتّساع للقدرة.
    is_escalation = bool(gained)

    return {
        "from_role": current_role,
        "to_role": new_role,
        "gained_permissions": sorted(p.value for p in gained),
        "lost_permissions": sorted(p.value for p in lost),
        "gained_count": len(gained),
        "lost_count": len(lost),
        "is_escalation": is_escalation,
        "gained_safety_critical": gained_critical,
        "lost_safety_critical": lost_critical,
        "warning_ar": (
            f"⚠ تصعيد صلاحيّات: يكتسب {len(gained_critical)} صلاحيّة حرجة "
            f"({', '.join(gained_critical)}) — راجع بعناية."
            if gained_critical
            else f"سحب {len(lost_critical)} صلاحيّة حرجة — تأكّد أنّه مقصود."
            if lost_critical
            else f"تغيير عادي: +{len(gained)} / -{len(lost)} صلاحيّة (لا حرجة)."
        ),
        "audit_note_ar": (
            "سجّل هذا التغيير (من غيّر، متى، السبب) في سجلّ تدقيق append-only — "
            "كي تُجيب لاحقاً: 'من رقّى هذا المستخدم ومتى؟'"
        ),
    }
