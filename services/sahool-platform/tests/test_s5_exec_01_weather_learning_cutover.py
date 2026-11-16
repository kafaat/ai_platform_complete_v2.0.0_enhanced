from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_weather_decision_cutover_has_service_only_authoritative_branch():
    p = ROOT / "services/sahool-platform/api/routers/weather.py"
    t = p.read_text()
    s = t.index("async def _persist_weather_decision_record")
    e = t.index("def _recommendation_payload_from_plan", s)
    b = t[s:e]
    cs = b.index("if mode.strict_decision_service_required:")
    ce = b.index("    assert_platform_may_write_decision_sor", cs)
    cut = b[cs:ce]
    assert "conn.execute" not in cut
    assert "_emit_domain_event" not in cut
    assert "await _mirror_decision_to_service" in cut
    assert "authoritative" in cut and "persisted" in cut


# ── قطعُ `online_learning_updates`: كان مؤجَّلاً بـGATE-01، ونُفِّذ بتفويضٍ يمسّ ملفّه ──
# كانت هنا ملاحظةٌ تشرح ردَّ القطع إلى نصّ `main`: `api/phase_runtime_store.py` مسارٌ مجمَّد،
# ولم يكن هناك تفويضٌ `ISSUED` يمسّه. وصدر `GATE01-ADJ-2026-11-03-001` بقرار المالك
# («ارفع القيود وافتح الآن»)، ومسّ الملفّ لربط GUC المستأجر داخل المعاملة. فأسقط حارسُ
# S5-EXEC-01 التأجيلَ كما صُمِّم، وصار العقد مفروضاً، وهذه الحالة نظيرةُ حالة `weather.py`.
# فرعُ القطع خاملٌ ما لم يُطلَب `decision_service_sor` وتكتمل بوّاباته. لا تفعيل هنا.


def test_learning_update_cutover_has_service_only_authoritative_branch():
    p = ROOT / "services/sahool-platform/api/phase_runtime_store.py"
    t = p.read_text()
    s = t.index('update = outputs.get("online_learning_update") or {}')
    e = t.index('scenario = outputs.get("scenario_result") or {}', s)
    b = t[s:e]
    cs = b.index("if mode.strict_decision_service_required:")
    ce = b.index("if update and not service_owns_learning_update:", cs)
    cut = b[cs:ce]
    assert "conn.execute" not in cut and "_tenant_execute" not in cut
    assert "INSERT INTO online_learning_updates" not in cut
    assert "await _mirror_learning_update_to_service" in cut
    assert "authoritative" in cut and "persisted" in cut
    assert "service_owns_learning_update = True" in cut
    # The local write and its SoR guard stay after the branch, on the platform path only.
    tail = b[ce:]
    assert tail.index(
        'assert_platform_may_write_decision_sor("online_learning_updates")'
    ) < tail.index("INSERT INTO online_learning_updates")


def _unproven():
    import sys

    sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from api.phase_runtime_store import _unproven_learning_update_fields

    return _unproven_learning_update_fields


_SENT = {"update_id": "lu_1", "review_status": "approved", "agronomically_approved": True}


def test_the_pre_w2_03_service_reply_does_not_prove_the_learning_update():
    """The decision-service reply before W2-03 (main.py record_learning_update).

    It carried authoritative/persisted, but no write outcome and no review echo: the service
    inserted ON CONFLICT DO NOTHING and had no review columns, so the cutover must refuse a
    reply of that shape instead of reporting a success that dropped the review.
    """
    today = {
        "accepted": True,
        "authoritative": True,
        "persisted": True,
        "tenant_id": "t1",
        "update_id": "lu_1",
        "traceability_status": "traceable",
    }
    assert _unproven()(today, "t1", _SENT) == ["write", "review_status", "agronomically_approved"]


def test_a_reply_for_another_tenant_or_id_is_not_proof():
    reply = {
        "tenant_id": "t2",
        "update_id": "lu_other",
        "write": "inserted",
        "review_status": "approved",
        "agronomically_approved": True,
    }
    assert _unproven()(reply, "t1", _SENT) == ["tenant_id", "update_id"]


def test_a_complete_reply_is_accepted():
    reply = {
        "tenant_id": "t1",
        "update_id": "lu_1",
        "write": "updated",
        "review_status": "approved",
        "agronomically_approved": True,
    }
    assert _unproven()(reply, "t1", _SENT) == []


def test_an_exact_resend_read_back_as_unchanged_is_proof():
    """W2-03: an identical resend stores nothing new; the service says ``unchanged`` and reads
    the review back from the stored row, which equals what was sent."""
    reply = {
        "tenant_id": "t1",
        "update_id": "lu_1",
        "write": "unchanged",
        "review_status": "approved",
        "agronomically_approved": True,
    }
    assert _unproven()(reply, "t1", _SENT) == []


def test_a_stored_review_that_differs_from_the_sent_one_is_not_proof():
    reply = {
        "tenant_id": "t1",
        "update_id": "lu_1",
        "write": "unchanged",
        "review_status": "unreviewed",
        "agronomically_approved": False,
    }
    assert _unproven()(reply, "t1", _SENT) == ["review_status", "agronomically_approved"]


def test_the_decision_service_reply_carries_every_field_the_strict_check_reads():
    """Contract binding across the two services, read from source: every key the platform's
    strict check reads is a key the decision-service reply builds."""
    src = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
    start = src.index('@app.post("/v1/learning/updates")')
    reply = src[start : src.index("return _mirror_ack(", start)]
    for key in ("tenant_id", "update_id", "write", "review_status", "agronomically_approved"):
        assert f'"{key}":' in reply, key
