"""حارس عقد ترحيل MFA (V29.6.1) — تأكيدات ساكنة على SQL الترحيل v129 تعمل في طبقة
``unit`` (لا تحتاج Postgres)، فتلتقط أيّ انحدار في عقد الأمان أبكر من اختبار التكامل.

يكمّل ``test_mfa_hardening_integration_v29_5.py`` الذي يثبت السلوك نفسه على Postgres حيّ:
- **recovery بلا self-read:** سياسة ``mfa_recovery_codes`` خدمة-فقط (``current_role='admin'``)
  ولا تكشف تجزئات الرموز للمستخدم — يجب ألّا تشير إلى ``current_user_id``/``current_tenant``.
- **audit append-only:** trigger ``trg_append_only_mfa_audit_events`` يمنع UPDATE/DELETE عبر
  ``sahool_block_mutation`` (سجلّ تدقيق غير قابل للتزوير).
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

_V129 = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "v129_mfa_hardening_followup.sql"
)


def _sql() -> str:
    return open(_V129, encoding="utf-8").read()


def _policy_block(sql: str, name: str) -> str:
    """يستخرج جملة ``CREATE POLICY <name> ... ;`` (حتى الفاصلة المُنهية)."""
    m = re.search(rf"CREATE POLICY\s+{re.escape(name)}\b.*?;", sql, re.IGNORECASE | re.DOTALL)
    assert m, f"لم يُعثَر على CREATE POLICY {name} في v129"
    return m.group(0)


def test_recovery_codes_policy_is_service_only_no_self_read():
    sql = _sql()
    block = _policy_block(sql, "mfa_recovery_codes_policy")
    # خدمة-فقط: هروب الدور admin حاضر …
    assert "current_role" in block and "'admin'" in block, block
    # … ولا كشف ذاتيّ لتجزئات الرموز (لا مستخدم/مستأجِر في شرط recovery).
    assert "current_user_id" not in block, (
        "انحدار: سياسة mfa_recovery_codes تسمح بقراءة ذاتيّة لتجزئات الرموز "
        "(current_user_id) — يجب أن تبقى خدمة-فقط (role='admin')."
    )
    assert "current_tenant" not in block, (
        "انحدار: سياسة mfa_recovery_codes مُوسَّعة بالمستأجِر — يجب أن تبقى خدمة-فقط."
    )


def test_audit_events_is_append_only_trigger_present():
    sql = _sql()
    m = re.search(
        r"CREATE TRIGGER\s+trg_append_only_mfa_audit_events\b.*?;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "انحدار: trigger trg_append_only_mfa_audit_events مفقود من v129 (audit غير محميّ)"
    trg = m.group(0)
    assert re.search(r"BEFORE\s+UPDATE\s+OR\s+DELETE", trg, re.IGNORECASE), (
        "trigger append-only يجب أن يعترض UPDATE و DELETE معاً."
    )
    assert "mfa_audit_events" in trg
    assert "sahool_block_mutation" in trg, (
        "trigger يجب أن ينفّذ sahool_block_mutation (يرفع استثناءً يمنع التحوير)."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
