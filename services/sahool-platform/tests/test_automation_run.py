"""اختبارات تشكيل ملخّص تشغيل تقييم التنبيهات لكلّ الحقول — منطق نقيّ offline.

يغطّي helpers الشكل النقيّة (api.alert_rules.field_run_summary / summarize_run)
المستخدمة في endpoint /api/v1/automation/alerts/run وفي الجدولة الدوريّة.
لا حاجة لقاعدة أو شبكة — هذه دوال تجميع/تشكيل صرفة.
"""

from api.alert_rules import field_run_summary, summarize_run


# ─── field_run_summary: سطر حقل واحد ────────────────────────────────
def test_field_run_summary_success_shape():
    row = field_run_summary("fld_1", created=2, skipped=1)
    assert row == {"field_id": "fld_1", "created": 2, "skipped": 1}
    assert "error" not in row  # نجاح ⇒ لا مفتاح خطأ


def test_field_run_summary_defaults_zero():
    row = field_run_summary("fld_2")
    assert row == {"field_id": "fld_2", "created": 0, "skipped": 0}


def test_field_run_summary_error_zeros_counts():
    row = field_run_summary("fld_3", error="503: weather down")
    # الحقل المتعثّر: created/skipped=0 + رسالة خطأ صريحة (تدهور رشيق، لا اختلاق)
    assert row == {"field_id": "fld_3", "created": 0, "skipped": 0, "error": "503: weather down"}


def test_field_run_summary_coerces_to_int():
    row = field_run_summary("fld_4", created=True, skipped=False)
    assert row["created"] == 1
    assert row["skipped"] == 0
    assert isinstance(row["created"], int)


# ─── summarize_run: تجميع كلّ الحقول ────────────────────────────────
def test_summarize_run_aggregates_totals():
    rows = [
        field_run_summary("a", created=2, skipped=1),
        field_run_summary("b", created=0, skipped=3),
        field_run_summary("c", error="422: no coords"),
    ]
    out = summarize_run(rows)
    assert out["fields_total"] == 3
    assert out["fields_evaluated"] == 2  # a, b بلا خطأ
    assert out["fields_failed"] == 1  # c متعثّر
    assert out["created_total"] == 2
    assert out["skipped_total"] == 4
    assert out["per_field"] == rows  # التفصيل يُعاد كما هو


def test_summarize_run_empty():
    out = summarize_run([])
    assert out == {
        "fields_total": 0,
        "fields_evaluated": 0,
        "fields_failed": 0,
        "created_total": 0,
        "skipped_total": 0,
        "per_field": [],
    }


def test_summarize_run_all_failed():
    rows = [field_run_summary("x", error="503"), field_run_summary("y", error="404")]
    out = summarize_run(rows)
    assert out["fields_total"] == 2
    assert out["fields_evaluated"] == 0
    assert out["fields_failed"] == 2
    assert out["created_total"] == 0
    assert out["skipped_total"] == 0


def test_summarize_run_all_success():
    rows = [field_run_summary(f"f{i}", created=i, skipped=0) for i in range(4)]
    out = summarize_run(rows)
    assert out["fields_evaluated"] == 4
    assert out["fields_failed"] == 0
    assert out["created_total"] == 0 + 1 + 2 + 3


def test_summarize_run_per_field_preserves_order():
    rows = [field_run_summary(fid) for fid in ("z", "a", "m")]
    out = summarize_run(rows)
    assert [r["field_id"] for r in out["per_field"]] == ["z", "a", "m"]
