"""حارس نطاق السياق المُتجاوِز لـRLS (HIGH-001 — البُعد الجديد من شهادة الإنتاج).

هذه الجولة أدخلت سياقَين يتجاوزان RLS قصداً:
  • auth: app.current_role='admin' على كلّ اتّصالات المسبح (ليقرأ users بالبريد قبل
    معرفة المستأجِر). فأيّ استعلام في auth يرى كلّ المستأجرين.
  • sahool_jobs (BYPASSRLS): المرسِل (event_outbox) والمجدوِل (الطقس).

الخطر الجديد: لو لمس استعلامٌ تحت أحد هذين السياقين **جدولاً مستأجَراً آخر** (غير نطاقه)
لتسرّبت بياناته عبر المستأجرين (fail-closed لا يحميه — السياق متجاوِز). هذا الحارس
يثبت أنّ كلّ سياق محصور بجداول نطاقه (تدقيق فرديّ موثّق في docs/audits).
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))

# جداول نطاق الهويّة المسموح لـauth لمسها تحت سياق admin (موثّقة في التدقيق).
# invitations: جدول هويّة (إلحاق أعضاء بمستأجِر قائم) تديره خدمة auth. آمن تحت سياق
# admin لأنّ نقاطه تُنطّق المستأجِر يدويّاً (list يُرشّح بـtenant_id الداعي؛ accept/
# revoke عبر token فريد) — لا قراءة عابرة للمستأجرين.
# mfa_recovery_codes / mfa_audit_events (v128): جداول هويّة MFA تديرها خدمة auth تحت سياق
# admin — لها RLS مُنطّق بالمستأجِر مع هروب خدمة (نمط audit_log/v87)، فلا قراءة عابرة للمستأجرين.
_AUTH_DOMAIN_TABLES = {
    "users",
    "audit_log",
    "invitations",
    "mfa_recovery_codes",
    "mfa_audit_events",
}

# مرسِل/مجدوِل sahool_jobs: نطاقه فقط.
# processed_events: مخزن تعاضُد الاستهلاك (v91) — جدول بنية تحتيّة عالميّ بلا tenant_id
# (لا بيانات مستأجِر تتسرّب، مفتاحه event_id فقط). المرسِل يُطالِب الحدث فيه تحت BYPASSRLS
# قبل النشر (idempotent consumption، at-most-once) — ضمن نطاقه عمداً.
# outbox_delivery_attempts: سجلّ محاولات التسليم الجنائيّ append-only (v140) — يملكه المرسِل
# نفسه، يُكتَب صفّ لكلّ محاولة تحت سياق sahool_jobs ذاته. عليه RLS+FORCE (v140) وtenant_id
# من الحدث، لكنّ العامل **يكتب فقط** (INSERT) بـtenant_id الصحيح للحدث تحت BYPASSRLS — لا
# مسار قراءة عابر للمستأجرين هنا. ضمن النطاق عمداً (قراءة المستأجِر تُعزَل بـRLS).
_JOBS_SCOPE = {
    "services/sahool-platform/api/event_bus.py": {
        "event_outbox",
        "events",
        "processed_events",
        "outbox_delivery_attempts",
    },
    "services/sahool-platform/api/weather_automation.py": {
        "weather_automation_cache",
        "weather_automation_locations",
    },
}

# كلمات SQL التي تسبق اسم جدول.
_TBL_RE = re.compile(r"\b(?:FROM|INTO|JOIN|UPDATE)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
_CREATE_RE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _real_tables() -> set[str]:
    """كلّ أسماء الجداول الفعليّة من الهجرات — لتصفية ضجيج SQL (SET/aliases ليست جداول)."""
    out = set()
    mig = os.path.join(BASE, "migrations")
    for fn in os.listdir(mig):
        if fn.endswith(".sql"):
            with open(os.path.join(mig, fn), encoding="utf-8") as f:
                out |= {m.group(1).lower() for m in _CREATE_RE.finditer(f.read())}
    return out


def _sql_tables(path: str) -> set[str]:
    """أسماء **الجداول الفعليّة** المُشار إليها في SQL داخل ملفّ (يتقاطع مع جداول الهجرات
    فيسقط ضجيج الكلمات المفتاحيّة/الـaliases تلقائيّاً)."""
    real = _real_tables()
    found = set()
    with open(os.path.join(BASE, path), encoding="utf-8") as f:
        for line in f:
            if line.lstrip().startswith(("from ", "import ")) or " import " in line:
                continue
            for m in _TBL_RE.finditer(line):
                tok = m.group(1).lower()
                if tok in real:
                    found.add(tok)
    return found


def test_auth_admin_context_scoped_to_identity_tables():
    """auth (سياق admin يتجاوز RLS) يجب أن يلمس جداول الهويّة فقط — وإلّا تسرّب عابر."""
    tables = _sql_tables("services/auth/main.py")
    # رشّح كلمات SQL الشائعة التي ليست جداول (e.g. أسماء CTE/aliases نادرة) بالاقتصار
    # على ما يُعرَّف فعلاً كجدول مُستأجَر؛ لكن الأصل: ⊆ نطاق الهويّة.
    out_of_scope = tables - _AUTH_DOMAIN_TABLES
    assert out_of_scope == set(), (
        f"auth يلمس جداول خارج نطاق الهويّة تحت سياق admin (تسرّب عابر للمستأجرين محتمل): "
        f"{sorted(out_of_scope)}. أضِفها لـ_AUTH_DOMAIN_TABLES بعد تدقيق، أو استعمل سياق مستأجِر."
    )


@pytest.mark.parametrize("path,scope", list(_JOBS_SCOPE.items()))
def test_jobs_context_scoped(path, scope):
    """مسارات sahool_jobs (تتجاوز RLS) محصورة بجداول نطاقها فقط."""
    tables = _sql_tables(path)
    out_of_scope = tables - scope
    assert out_of_scope == set(), (
        f"{path} (يعمل بدور sahool_jobs المتجاوِز) يلمس جداول خارج نطاقه: {sorted(out_of_scope)}"
    )
