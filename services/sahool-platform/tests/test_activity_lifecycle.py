"""دورة حياة النشاط الحقليّ — أجزاء صرفة (بلا قاعدة).

يغطّي: آلة انتقالات الحالة (planned→done|skipped فقط، الحالة نفسها idempotent، غيرها
409)، دمج القيم الفعليّة في details بمفاتيح دفتر المدخلات، حمولة أحداث النشاط
(تاريخا الخطّة والتنفيذ)، وأنّ المُخطَّط لا يُصدِر *_STARTED، وأنّ الإعادة تُفضّل
performed_on على occurred_at، وتجميع الكمّيّة الفعليّة في دفتر المدخلات.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from api.event_bus import EventType
from api.event_replay import FieldStateReconstructor
from api.field_aggregate import (
    FieldInvariantError,
    activity_event_for,
    activity_event_payload,
    check_activity_transition,
    merge_activity_actuals,
)
from api.field_models import ActivityTransitionRequest
from core.engines.input_traceability import InputApplication, build_input_ledger
from fastapi import HTTPException
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# ─── آلة الانتقالات ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("target", ["done", "skipped"])
def test_planned_transitions_apply(target):
    assert check_activity_transition("planned", target) is True


@pytest.mark.parametrize("state", ["done", "skipped"])
def test_same_target_state_is_idempotent_noop(state):
    assert check_activity_transition(state, state) is False


@pytest.mark.parametrize(
    ("current", "target"),
    [("done", "planned"), ("skipped", "done"), ("done", "skipped"), ("skipped", "planned")],
)
def test_other_transitions_refused_with_409(current, target):
    with pytest.raises(FieldInvariantError) as exc:
        check_activity_transition(current, target)
    assert exc.value.http_status == 409


# ─── طلب الانتقال ──────────────────────────────────────────────────────────


def test_request_rejects_planned_as_target():
    with pytest.raises(ValidationError):
        ActivityTransitionRequest(status="planned")


def test_done_requires_performed_on():
    req = ActivityTransitionRequest(status="done")
    with pytest.raises(HTTPException) as exc:
        req.validate_for_transition(None)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "performed_on_required"


def test_done_rejects_future_performed_on_but_tolerates_one_day():
    today = datetime.now(UTC).date()
    req = ActivityTransitionRequest(status="done")
    req.validate_for_transition(today + timedelta(days=1))  # فرق منطقة زمنيّة
    with pytest.raises(HTTPException) as exc:
        req.validate_for_transition(today + timedelta(days=3))
    assert exc.value.detail["code"] == "performed_on_in_future"


def test_skipped_carries_no_execution():
    ActivityTransitionRequest(status="skipped").validate_for_transition(None)
    for req, performed in (
        (ActivityTransitionRequest(status="skipped"), date(2026, 3, 1)),
        (ActivityTransitionRequest(status="skipped", actual_quantity=5), None),
    ):
        with pytest.raises(HTTPException) as exc:
            req.validate_for_transition(performed)
        assert exc.value.detail["code"] == "skipped_has_no_execution"


def test_negative_actuals_rejected():
    with pytest.raises(ValidationError):
        ActivityTransitionRequest(status="done", actual_quantity=-1)
    with pytest.raises(ValidationError):
        ActivityTransitionRequest(status="done", actual_cost=-0.5)


def test_actuals_drop_missing_values():
    req = ActivityTransitionRequest(status="done", actual_quantity=40, actual_unit="kg")
    assert req.actuals() == {"actual_quantity": 40, "actual_unit": "kg"}


# ─── دمج القيم الفعليّة ────────────────────────────────────────────────────


def test_merge_actuals_uses_ledger_keys_and_keeps_plan():
    planned = {"product_name": "يوريا", "quantity": 50, "unit": "kg", "note": "x"}
    merged = merge_activity_actuals(
        planned, {"actual_quantity": 42.5, "actual_unit": "kg", "actual_cost": 9000}
    )
    assert merged["quantity"] == 42.5
    assert merged["planned_quantity"] == 50  # الخطّة محفوظة لا ممحوّة
    assert merged["unit"] == "kg" and "planned_unit" not in merged  # لا تغيير
    assert merged["cost"] == 9000 and "planned_cost" not in merged  # لا خطّة سابقة
    assert merged["product_name"] == "يوريا" and merged["note"] == "x"
    assert planned["quantity"] == 50  # لا تعديل على المُدخَل


def test_merge_actuals_handles_none_details():
    assert merge_activity_actuals(None, {"actual_product": "NPK"}) == {"product_name": "NPK"}


# ─── أحداث النشاط ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("atype", ["planting", "irrigation", "harvest"])
def test_planned_never_emits_started(atype):
    assert activity_event_for(atype, "planned") == EventType.ACTIVITY_RECORDED
    assert activity_event_for(atype, "skipped") == EventType.ACTIVITY_RECORDED
    assert "STARTED" not in activity_event_for(atype, "done").name


def test_event_payload_carries_schedule_and_execution_dates():
    payload = activity_event_payload(
        "fld_1", None, "planting", "done", date(2026, 3, 1), date(2026, 3, 4)
    )
    assert payload == {
        "field_id": "fld_1",
        "season_id": None,
        "activity_type": "planting",
        "status": "done",
        "scheduled_for": "2026-03-01",
        "performed_on": "2026-03-04",
    }
    planned = activity_event_payload("fld_1", "s1", "harvest", "planned", "2026-06-01")
    assert planned["scheduled_for"] == "2026-06-01" and planned["performed_on"] is None


def _ev(event_type, occurred_at, payload):
    return {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "event_id": "e1",
        "payload": payload,
    }


def test_replay_prefers_payload_performed_on_over_occurred_at():
    state = FieldStateReconstructor.reconstruct(
        "field",
        "F1",
        [
            _ev(
                "operation.planting.completed",
                "2026-03-20T10:00:00",  # مزامنة متأخّرة من الموبايل
                {"field_id": "F1", "performed_on": "2026-03-04"},
            ),
            _ev(
                "operation.harvest.completed",
                "2026-07-10T10:00:00",
                {"field_id": "F1", "performed_on": "2026-07-01"},
            ),
        ],
    )
    assert state.planting_date == "2026-03-04"
    assert state.harvest_date == "2026-07-01"


def test_replay_falls_back_to_occurred_at_for_legacy_events():
    state = FieldStateReconstructor.reconstruct(
        "field", "F1", [_ev("operation.planting.completed", "2026-03-20T10:00:00", {})]
    )
    assert state.planting_date == "2026-03-20T10:00:00"


# ─── دفتر المدخلات: الكمّيّة الفعليّة per منتج+وحدة ─────────────────────────


def test_input_ledger_aggregates_quantity_per_product_and_unit():
    apps = [
        InputApplication("fertilization", product_name="يوريا", quantity=40, unit="kg"),
        InputApplication("fertilization", product_name="يوريا", quantity=10.5, unit="kg"),
        InputApplication("fertilization", product_name="يوريا", quantity=2, unit="L"),
        InputApplication("fertilization", product_name="يوريا", quantity=None, unit="kg"),
        InputApplication("planting", product_name="بذور قمح", quantity=120, unit="kg", cost=5),
    ]
    out = build_input_ledger(apps, field_id="f1")
    # المفاتيح القائمة باقية.
    assert out["by_input_type"]["fertilizer"]["count"] == 4
    assert out["total_cost"] == 5
    rows = {(q["input_type"], q["product_name"], q["unit"]): q for q in out["quantities"]}
    kg = rows[("fertilizer", "يوريا", "kg")]
    assert kg["quantity"] == 50.5
    assert kg["n_applications"] == 3 and kg["n_without_quantity"] == 1
    assert rows[("fertilizer", "يوريا", "L")]["quantity"] == 2  # لا جمع عبر الوحدات
    assert rows[("seed", "بذور قمح", "kg")]["quantity"] == 120
    # ترتيب النَسَب: البذرة أوّلاً.
    assert out["quantities"][0]["input_type"] == "seed"


def test_input_ledger_quantity_absent_is_declared_not_zero():
    out = build_input_ledger([InputApplication("spraying", product_name="مبيد")], field_id="f1")
    (row,) = out["quantities"]
    assert row["quantity"] is None and row["n_without_quantity"] == 1


def test_empty_input_ledger_has_empty_quantities():
    assert build_input_ledger([], field_id="f1")["quantities"] == []
