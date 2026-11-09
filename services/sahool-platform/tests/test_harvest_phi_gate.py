"""بوّابة PHI على تسجيل الحصاد — المستهلك الإنتاجيّ لـ``phi_gate``.

كانت ``core.engines.pesticide.phi_gate`` (مهارة ``pesticide_phi_gate`` الحرجة للسلامة) بلا
مستدعٍ إنتاجيّ: نشاط حصاد أو دفعة حصاد يُقبَلان في اليوم التالي للرشّ. هنا:

* اختبارات نقيّة لقرار ``evaluate_harvest_phi`` (بلا قاعدة، بلا اتّصال وهميّ).
* اختبارات قرار التجاوز ``phi_override_record`` (409 / 422 / 403 / سجلّ).
* تأكيد مصدريّ أدنى أنّ المسارين يستدعيان البوّابة **قبل** الإدراج ويحفظان نتيجتها.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from core.authorization import UserRole, UserSchema
from core.engines.pesticide import (
    SprayRecord,
    evaluate_harvest_phi,
    phi_days_from_details,
    spray_product_from_details,
)
from fastapi import HTTPException

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[1]
SPRAY = date(2026, 10, 1)


def _spray(phi, on=SPRAY, product="كلوربيريفوس", aid="act_s1"):
    return SprayRecord(performed_on=on, phi_days=phi, product=product, activity_id=aid)


def _user(role: UserRole) -> UserSchema:
    return UserSchema(
        user_id=f"u_{role.value}",
        tenant_id="tnt_001",
        role=role,
        name_ar="test",
        farm_ids_access=[],
        is_active=True,
    )


# ─── القرار النقيّ ────────────────────────────────────────────────────────────
def test_three_days_after_spray_with_phi_14_is_refused_with_earliest_safe_date():
    check = evaluate_harvest_phi(SPRAY + timedelta(days=3), [_spray(14)])
    assert check.allowed is False
    assert check.days_since_spray == 3
    assert check.earliest_safe_date == date(2026, 10, 15)
    assert check.blocking_spray is not None and check.blocking_spray.phi_days == 14
    # الرسالة عربيّة وتسمّي المنتج وأقرب تاريخ آمن.
    assert "كلوربيريفوس" in check.message_ar
    assert "2026-10-15" in check.message_ar
    out = check.to_dict()
    assert out["earliest_safe_date"] == "2026-10-15"
    assert out["blocking_spray"]["product"] == "كلوربيريفوس"


def test_twenty_days_after_spray_with_phi_14_is_allowed():
    check = evaluate_harvest_phi(SPRAY + timedelta(days=20), [_spray(14)])
    assert check.allowed is True
    assert check.limitations == []
    assert check.earliest_safe_date is None


def test_exactly_phi_days_is_allowed_boundary_inclusive():
    assert evaluate_harvest_phi(SPRAY + timedelta(days=14), [_spray(14)]).allowed is True
    assert evaluate_harvest_phi(SPRAY + timedelta(days=13), [_spray(14)]).allowed is False


def test_unknown_phi_on_last_spray_warns_but_does_not_block():
    check = evaluate_harvest_phi(SPRAY + timedelta(days=1), [_spray(None)])
    assert check.allowed is True
    assert check.limitations == ["phi_unknown"]
    assert "PHI" in check.message_ar and "غير مسجَّلة" in check.message_ar


def test_older_spray_with_longer_phi_still_binds():
    # رشّة قديمة PHI=30 تحكم رغم أنّ الأحدث PHI=3 انقضت فترتها.
    old = _spray(30, on=SPRAY, product="قديم", aid="a_old")
    new = _spray(3, on=SPRAY + timedelta(days=10), product="جديد", aid="a_new")
    check = evaluate_harvest_phi(SPRAY + timedelta(days=15), [new, old])
    assert check.allowed is False
    assert check.blocking_spray.activity_id == "a_old"
    assert check.earliest_safe_date == SPRAY + timedelta(days=30)


def test_violation_still_blocks_when_latest_spray_phi_is_unknown():
    known = _spray(21, on=SPRAY, aid="a_known")
    unknown = _spray(None, on=SPRAY + timedelta(days=2), aid="a_unknown")
    check = evaluate_harvest_phi(SPRAY + timedelta(days=5), [known, unknown])
    assert check.allowed is False
    assert check.limitations == ["phi_unknown"]


def test_spray_after_harvest_date_and_no_spray_are_ignored():
    assert evaluate_harvest_phi(SPRAY, [_spray(14, on=SPRAY + timedelta(days=1))]).allowed
    check = evaluate_harvest_phi(SPRAY, [])
    assert check.allowed is True and check.limitations == []


def test_phi_and_product_are_read_from_spraying_details():
    assert phi_days_from_details({"phi_days": 14}) == 14
    assert phi_days_from_details({"phi": "7"}) == 7
    assert phi_days_from_details({"pre_harvest_interval_days": 7.2}) == 8  # يُقرَّب للأعلى
    assert phi_days_from_details({"phi_days": 0}) == 0
    for bad in ({"phi_days": -1}, {"phi_days": True}, {"phi_days": "abc"}, {}, None):
        assert phi_days_from_details(bad) is None
    assert spray_product_from_details({"product": " مانكوزيب "}) == "مانكوزيب"
    assert spray_product_from_details({"product_name": ""}) is None


# ─── قرار التجاوز ─────────────────────────────────────────────────────────────
def _blocked():
    return evaluate_harvest_phi(SPRAY + timedelta(days=3), [_spray(14)])


def test_no_override_refuses_with_409_naming_product_and_date():
    from api.field_context import phi_override_record

    with pytest.raises(HTTPException) as e:
        phi_override_record(_user(UserRole.OWNER), _blocked(), False, None)
    assert e.value.status_code == 409
    assert e.value.detail["code"] == "phi_not_elapsed"
    assert e.value.detail["earliest_safe_date"] == "2026-10-15"
    assert e.value.detail["product"] == "كلوربيريفوس"


def test_override_needs_a_reason_and_the_owner_permission():
    from api.field_context import phi_override_record

    with pytest.raises(HTTPException) as e:
        phi_override_record(_user(UserRole.OWNER), _blocked(), True, "  ")
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        phi_override_record(_user(UserRole.AGRONOMIST), _blocked(), True, "فحص مخبري سليم")
    assert e.value.status_code == 403
    # قيمة غير منطقيّة صريحة (نصّ "true") ليست تجاوزاً.
    with pytest.raises(HTTPException) as e:
        phi_override_record(_user(UserRole.OWNER), _blocked(), "true", "سبب")
    assert e.value.status_code == 409
    rec = phi_override_record(_user(UserRole.OWNER), _blocked(), True, "فحص مخبري سليم")
    assert rec["reason"] == "فحص مخبري سليم" and rec["by"] == "u_owner" and rec["at"]


def test_non_harvest_activity_details_pass_through_without_db():
    from api.field_context import activity_details_with_phi_gate

    req = SimpleNamespace(activity_type="spraying", details={"phi_days": 14})
    out = asyncio.run(activity_details_with_phi_gate(None, None, "fld_1", req))
    assert out == {"phi_days": 14}


# ─── تأكيد مصدريّ أدنى: البوّابة موصولة قبل الإدراج في المسارين ─────────────────
def _func_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    m = re.search(rf"^async def {name}\(.*?(?=^@router|\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


def test_create_activity_runs_the_phi_gate_before_insert_and_stores_its_result():
    body = _func_source(PLATFORM / "api/routers/fields.py", "create_activity")
    gate = body.index("await activity_details_with_phi_gate(conn, user, field_id, req)")
    assert gate < body.index("INSERT INTO activities")
    assert "json.dumps(details_out)" in body  # ما يُدرَج هو التفاصيل بعد البوّابة
    assert "details=details_out" in body  # وما يُعاد كذلك


def test_create_harvest_lot_runs_the_phi_gate_before_insert_and_records_it():
    body = _func_source(PLATFORM / "api/routers/harvest_traceability.py", "create_harvest_lot")
    gate = body.index("await harvest_lot_phi_check(conn, user, req, harvest_date)")
    assert gate < body.index("INSERT INTO harvest_lots")
    assert '"phi_check": phi' in body  # في حمولة HARVEST_LOT_CREATED وفي الاستجابة


def test_phi_check_reads_only_done_sprays_up_to_the_harvest_date():
    from api import field_context

    sql = " ".join(field_context._DONE_SPRAYS_SQL.split())
    assert "activity_type = 'spraying'" in sql and "status = 'done'" in sql
    assert "performed_on <= $2" in sql
    assert "evaluate_harvest_phi" in inspect.getsource(field_context.harvest_phi_check)
