"""عزل المستأجِر في تصدير تقرير العمليّة (operation_report_csv) — تشديد SEC.

كان `POST /api/v1/reports/operation` يثق بـ`tenant_id` من جسم الطلب لتصدير CSV ⇒ مستأجِر
قد يُصدّر/يخلط حقول مستأجِر آخر. الإصلاح: يرفض عدم تطابق tenant_id (الطلب أو أيّ حقل) مع
المستأجِر المُتحقَّق ⇒ 403. المقارنة بـ`str()` على الطرفين (UUID/str) كي لا تَكسِر الشرعيّ.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def reports_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    # استورِد api.main أوّلاً (يُكمِل تهيئته ويستورد الموجِّهات في نهايته) قبل
    # الوصول إلى reports — تفادياً للاستيراد الدائريّ (main ⇄ routers.reports).
    import api.main  # noqa: F401
    from api.routers import reports

    return reports


def _user(reports_mod, tenant: str):
    from core.canonical_schemas import UserSchema

    return UserSchema(user_id="u", tenant_id=tenant, role="owner", name_ar="x")


def _req(reports_mod, *, body_tenant: str, field_tenants: list[str]):
    from api.main import OperationReportRequest, ReportFieldInput

    return OperationReportRequest(
        tenant_id=body_tenant,
        operation_name_ar="تقرير",
        period_start="2026-01-01",
        period_end="2026-01-31",
        fields=[
            ReportFieldInput(field_id=f"f{i}", field_name_ar="حقل", tenant_id=t)
            for i, t in enumerate(field_tenants)
        ],
    )


def test_matching_tenant_exports_ok(reports_mod):
    """مستأجِر مطابق (طلب + كلّ الحقول) ⇒ يُصدَّر CSV (لا 403، الحالة الشرعيّة لا تَكسِر)."""
    user = _user(reports_mod, "t1")
    req = _req(reports_mod, body_tenant="t1", field_tenants=["t1", "t1"])
    out = reports_mod.operation_report_csv(req, user=user)
    assert isinstance(out, str) and "حقل" in out


def test_body_tenant_mismatch_denied(reports_mod):
    """tenant_id في الجسم ≠ مستأجِر التوكن ⇒ 403 tenant_mismatch."""
    from fastapi import HTTPException

    user = _user(reports_mod, "t1")
    req = _req(reports_mod, body_tenant="t2", field_tenants=["t1"])
    with pytest.raises(HTTPException) as ei:
        reports_mod.operation_report_csv(req, user=user)
    assert ei.value.status_code == 403
    assert ei.value.detail == "tenant_mismatch"


def test_field_tenant_mismatch_denied(reports_mod):
    """حقل بمستأجِر آخر (خلط) ⇒ 403 field_not_owned_by_tenant."""
    from fastapi import HTTPException

    user = _user(reports_mod, "t1")
    req = _req(reports_mod, body_tenant="t1", field_tenants=["t1", "t2"])
    with pytest.raises(HTTPException) as ei:
        reports_mod.operation_report_csv(req, user=user)
    assert ei.value.status_code == 403
    assert ei.value.detail == "field_not_owned_by_tenant"
