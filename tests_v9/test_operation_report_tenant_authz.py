"""عزل المستأجِر في تصدير تقرير العمليّة (CSV) — operation_report_csv.

يقفل إصلاح IDOR: جسم الطلب لا يفرض tenant_id ولا يخلط حقول مستأجِر آخر. مقارنة بـ
``str()`` على الطرفين (user.tenant_id قد يكون UUID) — تطابق ⇒ CSV؛ اختلاف الطلب ⇒ 403
tenant_mismatch؛ حقل بمستأجِر مختلف ⇒ 403 field_not_owned_by_tenant.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.main import OperationReportRequest, ReportFieldInput
    from api.routers.reports import operation_report_csv
    from fastapi import HTTPException
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def _user(tid):
    return SimpleNamespace(tenant_id=tid)


def _req(tid, field_tid):
    return OperationReportRequest(
        tenant_id=tid,
        operation_name_ar="تقرير",
        period_start="2026-01-01",
        period_end="2026-01-31",
        fields=[ReportFieldInput(field_id="f1", field_name_ar="حقل", tenant_id=field_tid)],
    )


def test_matching_tenant_produces_csv():
    """مستأجِر مطابق (طلب + حقل) ⇒ CSV (لا 403، الحالة الشرعيّة لا تُكسَر)."""
    out = operation_report_csv(_req("t1", "t1"), _user("t1"))
    assert isinstance(out, str) and out


def test_request_tenant_mismatch_403():
    """tenant_id في الجسم ≠ مستأجِر التوكن ⇒ 403 tenant_mismatch."""
    with pytest.raises(HTTPException) as ei:
        operation_report_csv(_req("t2", "t2"), _user("t1"))
    assert ei.value.status_code == 403
    assert ei.value.detail == "tenant_mismatch"


def test_field_tenant_mismatch_403():
    """حقل بمستأجِر مختلف ⇒ 403 field_not_owned_by_tenant (منع خلط CSV عابر)."""
    with pytest.raises(HTTPException) as ei:
        operation_report_csv(_req("t1", "t2"), _user("t1"))
    assert ei.value.status_code == 403
    assert ei.value.detail == "field_not_owned_by_tenant"


def test_str_uuid_compatibility():
    """user.tenant_id كـUUID والجسم str ⇒ يتطابقان بـstr() (لا 403 كاذب للجميع)."""
    u = uuid.UUID("11111111-1111-1111-1111-111111111111")
    out = operation_report_csv(_req(str(u), str(u)), _user(u))
    assert isinstance(out, str) and out
