"""اختبارات سجلّ تشغيل الأتمتة — منطق نقيّ في الذاكرة (بلا قاعدة/شبكة).

يغطّي ``core.automation_ledger``: حساب المدّة/الحالة من العدّادات الحقيقيّة،
سعة الحلقة الحلقيّة، ترتيب الأحدث-أوّلاً، إجماليّات الملخّص، ودورة الصفر-حقول.
"""

import pytest
from core.automation_ledger import LEDGER, RunLedger


# ─── الحالة من العدّادات الحقيقيّة (لا اختلاق) ──────────────────────
def test_ok_when_no_errors():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 3)
    rec.mark_evaluated()
    rec.mark_evaluated()
    rec.mark_skipped()
    out = rec.finish()
    assert out.status == "ok"
    assert out.evaluated == 2
    assert out.skipped == 1
    assert out.errored == 0


def test_partial_when_some_errored_some_evaluated():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 2)
    rec.mark_evaluated()
    rec.mark_errored("fld_x", ValueError("no coords"))
    out = rec.finish()
    assert out.status == "partial"
    assert out.errored == 1
    assert out.errors == [{"field_id": "fld_x", "error": "no coords"}]


def test_error_when_all_errored():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 2)
    rec.mark_errored("a", "503")
    rec.mark_errored("b", "404")
    out = rec.finish()
    assert out.status == "error"
    assert out.evaluated == 0
    assert out.errored == 2


def test_zero_field_run_is_ok_with_note():
    ledger = RunLedger()
    out = ledger.start_run("alerts", 0).finish()
    assert out.status == "ok"
    assert out.note_ar is not None
    assert out.fields_total == 0


# ─── المدّة + الختم ─────────────────────────────────────────────────
def test_duration_ms_non_negative_and_finished_at_set():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 1)
    rec.mark_evaluated()
    out = rec.finish()
    assert out.duration_ms >= 0
    assert isinstance(out.duration_ms, int)
    assert out.finished_at is not None
    assert out.started_at is not None


def test_add_alerts_accumulates():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 2)
    rec.mark_evaluated()
    rec.add_alerts(3)
    rec.mark_evaluated()
    rec.add_alerts(2)
    out = rec.finish()
    assert out.alerts_created == 5


def test_finish_is_idempotent():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 1)
    rec.mark_evaluated()
    first = rec.finish()
    second = rec.finish()
    assert first is second
    assert len(ledger.recent()) == 1  # لم يُلحَق مرّتين


def test_custom_note_overrides_default():
    ledger = RunLedger()
    rec = ledger.start_run("alerts", 1)
    rec.mark_evaluated()
    out = rec.finish(note_ar="ملاحظة مخصّصة")
    assert out.note_ar == "ملاحظة مخصّصة"


# ─── الحلقة الحلقيّة: السعة + الترتيب ───────────────────────────────
def test_ring_buffer_caps_at_maxlen_drops_oldest():
    ledger = RunLedger(maxlen=3)
    for i in range(5):
        ledger.start_run(f"t{i}", 1).finish()
    recent = ledger.recent()
    assert len(recent) == 3  # سُقِف عند 3
    # الأحدث أوّلاً، والأقدم (t0, t1) سقطا
    assert [r["task_name"] for r in recent] == ["t4", "t3", "t2"]


def test_recent_newest_first():
    ledger = RunLedger()
    ledger.start_run("first", 1).finish()
    ledger.start_run("second", 1).finish()
    recent = ledger.recent()
    assert [r["task_name"] for r in recent] == ["second", "first"]


def test_recent_limit_truncates():
    ledger = RunLedger()
    for i in range(5):
        ledger.start_run(f"t{i}", 1).finish()
    assert len(ledger.recent(limit=2)) == 2
    assert ledger.recent(limit=0) == []


def test_recent_returns_dicts():
    ledger = RunLedger()
    ledger.start_run("alerts", 1).finish()
    rec = ledger.recent()[0]
    assert isinstance(rec, dict)
    for key in ("task_name", "started_at", "finished_at", "status", "duration_ms"):
        assert key in rec


# ─── الملخّص ────────────────────────────────────────────────────────
def test_summary_totals_across_buffer():
    ledger = RunLedger()
    r1 = ledger.start_run("a", 2)
    r1.mark_evaluated()
    r1.add_alerts(2)
    r1.finish()
    r2 = ledger.start_run("b", 2)
    r2.mark_evaluated()
    r2.mark_errored("x", "boom")
    r2.add_alerts(1)
    r2.finish()

    s = ledger.summary()
    assert s["total_runs"] == 2
    assert s["totals"]["evaluated"] == 2
    assert s["totals"]["errored"] == 1
    assert s["totals"]["alerts_created"] == 3
    assert s["last_run"]["task_name"] == "b"  # آخر دورة
    assert s["last_run"]["status"] == "partial"


def test_summary_empty_ledger():
    ledger = RunLedger()
    s = ledger.summary()
    assert s["total_runs"] == 0
    assert s["last_run"] is None
    assert s["totals"]["evaluated"] == 0
    assert s["buffer_capacity"] == 50


def test_module_singleton_shared():
    LEDGER.clear()
    LEDGER.start_run("singleton", 1).finish()
    assert len(LEDGER.recent()) == 1
    LEDGER.clear()
    assert LEDGER.recent() == []


# ─── مُعامِلة للحالة ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("evaluated", "errored", "expected"),
    [
        (3, 0, "ok"),
        (1, 1, "partial"),
        (0, 2, "error"),
        (0, 0, "ok"),
    ],
)
def test_status_matrix(evaluated, errored, expected):
    ledger = RunLedger()
    rec = ledger.start_run("alerts", evaluated + errored)
    for _ in range(evaluated):
        rec.mark_evaluated()
    for i in range(errored):
        rec.mark_errored(f"f{i}", "err")
    assert rec.finish().status == expected
