"""tests_v9/test_harvest_custody_integrity.py — سلامة سلسلة الحيازة (نقيّ، بلا DB).

يغطّي محرّك core/engines/harvest_traceability بعد إصلاح المراجعة:
  ① البصمة v2 تغطّي كلّ حقل عمل مُخزَّن، وتُطبَّع (UTC · NUMERIC(12,2)) فتتحقّق بعد الرحلة.
  ② verify_event_hash: verified / legacy_hash (الصيغة القديمة) / mismatch / missing.
  ③ «كامل» = أوّل حدث حصاد + بيع + زمن مرتّب وبعد الحصاد + كتلة متوازنة + لا تلاعب،
     مع incomplete_reasons.
  ④ custody_event_refusal: المستقبل / قبل الحصاد / أسبق من آخر حدث / الكتلة.
  ⑤ حدود event_details (الحجم/العمق/NaN) في نموذج الطلب.
  ⑥ بنية الراوتر: إزالة التكرار بالبصمة قبل الفحوص، و422 قبل الإدراج.
"""

import inspect
import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from core.engines import harvest_traceability as ht  # noqa: E402

LOT = "hl_0123456789abcdef"


def _readback(event: dict) -> dict:
    """ما تُعيده القراءة بعد القاعدة: TIMESTAMPTZ → UTC ISO، NUMERIC → float."""
    out = dict(event)
    out["occurred_at"] = ht.parse_occurred_at(event["occurred_at"]).astimezone(UTC).isoformat()
    q = ht.normalize_quantity_kg(event.get("quantity_kg"))
    out["quantity_kg"] = float(q) if q is not None else None
    return out


def _event(**kw) -> dict:
    base = {
        "harvest_lot_id": LOT,
        "event_type": "storage",
        "occurred_at": "2026-03-01T10:00:00+03:00",
        "handler": "مخزن مأرب",
        "handler_role": "storage",
        "location_name": "مأرب",
        "quantity_kg": 100.005,
        "event_details": {"temp_c": 18, "notes": "جافّ"},
    }
    base.update(kw)
    return base


def _stamped(event: dict) -> dict:
    """حدث كما يكتبه الراوتر (بصمة v2) ثمّ يُقرأ."""
    e = dict(event)
    e["content_hash"] = ht.custody_event_hash_of(e, LOT)
    return _readback(e)


# ── ① البصمة v2 ─────────────────────────────────────────────────────────────


def test_v2_hash_is_offset_independent_and_verifies_after_round_trip():
    local = ht.custody_event_hash_of(_event(occurred_at="2026-03-01T10:00:00+03:00"), LOT)
    utc = ht.custody_event_hash_of(_event(occurred_at="2026-03-01T07:00:00Z"), LOT)
    assert local == utc
    assert ht.verify_event_hash(_stamped(_event()), LOT) == ht.HASH_VERIFIED


@pytest.mark.parametrize(
    "field,value",
    [
        ("handler", "شخص آخر"),
        ("handler_role", "trader"),
        ("location_name", "صنعاء"),
        ("quantity_kg", 99.0),
        ("event_details", {"temp_c": 30}),
        ("event_type", "transport"),
        ("occurred_at", "2026-03-01T11:00:00+03:00"),
    ],
)
def test_v2_hash_covers_every_persisted_business_field(field, value):
    stored = _stamped(_event())
    tampered = dict(stored)
    tampered[field] = value
    assert ht.verify_event_hash(tampered, LOT) == ht.HASH_MISMATCH


def test_quantity_normalised_like_numeric_12_2():
    assert ht.normalize_quantity_kg(100.005) == Decimal("100.01")
    assert ht.normalize_quantity_kg(7) == Decimal("7.00")
    assert ht.normalize_quantity_kg(None) is None


# ── ② التحقّق والصفوف القديمة ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "client_at", ["2026-03-01T10:00:00+03:00", "2026-03-01T07:00:00", "2026-03-01T07:00:00+00:00"]
)
def test_rows_hashed_with_old_formula_are_legacy_not_tampered(client_at):
    ev = _event(occurred_at=client_at)
    # الراوتر القديم: compute_event_hash(lot, type, datetime.fromisoformat(x).isoformat(), details)
    old_at = datetime.fromisoformat(client_at).isoformat()
    ev["content_hash"] = ht.compute_event_hash(LOT, ev["event_type"], old_at, ev["event_details"])
    assert ht.verify_event_hash(_readback(ev), LOT) == ht.HASH_LEGACY


def test_legacy_row_with_changed_details_is_mismatch():
    ev = _event()
    old_at = datetime.fromisoformat(ev["occurred_at"]).isoformat()
    ev["content_hash"] = ht.compute_event_hash(LOT, ev["event_type"], old_at, ev["event_details"])
    row = _readback(ev)
    row["event_details"] = {"temp_c": 40}
    assert ht.verify_event_hash(row, LOT) == ht.HASH_MISMATCH


def test_missing_hash_is_reported_as_missing():
    assert ht.verify_event_hash(_readback(_event()), LOT) == ht.HASH_MISSING


# ── ③ الاكتمال ──────────────────────────────────────────────────────────────

_LOT = {"harvest_lot_id": LOT, "harvest_date": "2026-03-01", "quantity_kg": 500.0}


def _chain(*specs):
    out = []
    for i, (etype, at, qty) in enumerate(specs, start=1):
        e = _stamped(
            _event(event_type=etype, occurred_at=at, quantity_kg=qty, event_details={"i": i})
        )
        e["custody_event_id"] = i
        out.append(e)
    return out


def test_complete_chain_verified():
    out = ht.assemble_traceability(
        _LOT,
        _chain(
            ("harvest", "2026-03-01T08:00:00+03:00", 500),
            ("storage", "2026-03-02T08:00:00+03:00", 500),
            ("sales", "2026-03-05T08:00:00+03:00", 300),
            ("sales", "2026-03-06T08:00:00+03:00", 200),
        ),
    )
    chain = out["chain"]
    assert chain["complete"] is True and chain["incomplete_reasons"] == []
    assert chain["hash_verified"] is True
    assert all(e["hash_verified"] is True for e in out["custody_chain"])


def test_harvest_somewhere_is_not_enough_first_event_must_be_harvest():
    out = ht.assemble_traceability(
        _LOT,
        _chain(
            ("storage", "2026-03-01T09:00:00+03:00", None),
            ("harvest", "2026-03-01T10:00:00+03:00", None),
            ("sales", "2026-03-02T10:00:00+03:00", None),
        ),
    )
    assert out["chain"]["started_at_harvest"] is False
    assert out["chain"]["complete"] is False
    assert "first_event_not_harvest" in out["chain"]["incomplete_reasons"]


def test_event_before_harvest_date_and_backdated_record_are_incomplete():
    events = _chain(
        ("harvest", "2026-02-20T08:00:00+03:00", None),  # قبل تاريخ الحصاد بأيّام
        ("sales", "2026-03-05T08:00:00+03:00", None),
        ("storage", "2026-03-03T08:00:00+03:00", None),  # سُجِّل بعد البيع بزمن أسبق
    )
    reasons = ht.assemble_traceability(_LOT, events)["chain"]["incomplete_reasons"]
    assert "occurred_before_harvest_date" in reasons
    assert "non_monotonic_occurred_at" in reasons


def test_outgoing_quantity_beyond_lot_is_incomplete():
    events = _chain(
        ("harvest", "2026-03-01T08:00:00+03:00", 500),
        ("sales", "2026-03-05T08:00:00+03:00", 400),
        ("sales", "2026-03-06T08:00:00+03:00", 200),
    )
    reasons = ht.assemble_traceability(_LOT, events)["chain"]["incomplete_reasons"]
    assert reasons == ["outgoing_quantity_exceeds_lot"]


def test_tampered_event_makes_chain_unverified_and_incomplete():
    events = _chain(
        ("harvest", "2026-03-01T08:00:00+03:00", 500),
        ("sales", "2026-03-05T08:00:00+03:00", 500),
    )
    events[1]["handler"] = "مشترٍ مختلف"
    out = ht.assemble_traceability(_LOT, events)
    assert out["chain"]["hash_verified"] is False
    assert "hash_mismatch" in out["chain"]["incomplete_reasons"]
    assert out["custody_chain"][1]["hash_status"] == ht.HASH_MISMATCH


def test_legacy_rows_do_not_claim_full_verification_nor_tampering():
    events = _chain(
        ("harvest", "2026-03-01T08:00:00+03:00", 500),
        ("sales", "2026-03-05T08:00:00+03:00", 500),
    )
    ev = events[0]
    old_at = "2026-03-01T08:00:00+03:00"
    ev["content_hash"] = ht.compute_event_hash(LOT, "harvest", old_at, ev["event_details"])
    out = ht.assemble_traceability(_LOT, events)
    assert out["custody_chain"][0]["hash_status"] == ht.HASH_LEGACY
    assert out["custody_chain"][0]["hash_verified"] is None
    assert out["chain"]["hash_verified"] is None
    assert out["chain"]["complete"] is True


def test_empty_chain_reasons():
    reasons = ht.assemble_traceability(_LOT, [])["chain"]["incomplete_reasons"]
    assert reasons == ["no_events", "no_sales_event"]


# ── ④ رفض الكتابة ───────────────────────────────────────────────────────────

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def _refusal(**kw):
    args = {
        "event_type": "storage",
        "occurred_at": datetime(2026, 3, 5, 9, 0, tzinfo=UTC),
        "quantity_kg": Decimal("100"),
        "lot_quantity_kg": Decimal("500"),
        "harvest_date": "2026-03-01",
        "last_occurred_at": datetime(2026, 3, 4, 9, 0, tzinfo=UTC),
        "outgoing_kg_so_far": Decimal("0"),
        "now": NOW,
    }
    args.update(kw)
    return ht.custody_event_refusal(**args)


def test_valid_event_is_accepted():
    assert _refusal() is None
    # زمن مساوٍ لآخر حدث مسموح، وكذا انحراف ساعة صغير.
    assert _refusal(occurred_at=datetime(2026, 3, 4, 9, 0, tzinfo=UTC)) is None
    assert _refusal(occurred_at=NOW + timedelta(minutes=5)) is None


def test_future_event_refused():
    assert _refusal(occurred_at=NOW + timedelta(hours=2)) is not None


def test_event_before_harvest_date_refused_but_timezone_slack_allowed():
    assert _refusal(occurred_at=datetime(2026, 2, 27, tzinfo=UTC), last_occurred_at=None)
    # 2026-02-28T22:00Z = 03-01 01:00 بتوقيت اليمن — يوم الحصاد نفسه.
    assert (
        _refusal(occurred_at=datetime(2026, 2, 28, 22, 0, tzinfo=UTC), last_occurred_at=None)
        is None
    )


def test_backdated_event_refused():
    assert _refusal(occurred_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC)) is not None


def test_mass_balance_refused():
    assert _refusal(quantity_kg=Decimal("600")) is not None
    assert _refusal(event_type="sales", quantity_kg=Decimal("300")) is None
    assert (
        _refusal(event_type="sales", quantity_kg=Decimal("300"), outgoing_kg_so_far=Decimal("250"))
        is not None
    )
    # النقل لا يستهلك من الدفعة.
    assert (
        _refusal(event_type="transport", quantity_kg=Decimal("300"), outgoing_kg_so_far=400) is None
    )


# ── ⑤ حدود event_details ────────────────────────────────────────────────────


def _req(**kw):
    from api.harvest_models import CustodyEventCreateRequest

    payload = {"event_type": "storage", "occurred_at": "2026-03-05T09:00:00+03:00"}
    payload.update(kw)
    return CustodyEventCreateRequest(**payload)


def test_event_details_bounds():
    from pydantic import ValidationError

    assert _req(event_details={"a": {"b": {"c": {"d": 1}}}}).event_details  # عمق 4 مقبول
    with pytest.raises(ValidationError):
        _req(event_details={"a": {"b": {"c": {"d": {"e": 1}}}}})
    with pytest.raises(ValidationError):
        _req(event_details={"blob": "x" * 9000})
    with pytest.raises(ValidationError):
        _req(event_details={"v": float("nan")})
    with pytest.raises(ValidationError):
        _req(quantity_kg=float("inf"))


# ── ⑥ بنية الراوتر ──────────────────────────────────────────────────────────


def test_router_dedupes_by_hash_before_checks_and_refuses_422_before_insert():
    import api.main  # noqa: F401 — initialise api.main before importing the router
    import api.routers.harvest_traceability as route

    src = inspect.getsource(route.add_custody_event)
    assert "compute_custody_event_hash(" in src and "compute_event_hash(" not in src
    lock = src.index("FOR UPDATE")
    dedupe = src.index("AND content_hash = $2")
    assert lock < dedupe < src.index("transition_refusal(")
    assert src.index("status_code=422", src.index("custody_event_refusal(")) < src.index(
        "INSERT INTO custody_chain_events"
    )
    # الكمّيّة المُدرَجة هي المُطبَّعة نفسها التي بُصِمت.
    assert "quantity_kg=quantity," in src
    assert "req.quantity_kg,\n" not in src, (
        "the raw request quantity must pass the mass check before it is inserted"
    )
