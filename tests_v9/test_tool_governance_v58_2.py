"""تحقّق V58.2b — تصلّب حوكمة استدعاء الأدوات (تحقّق الوسائط + تعقيم النتائج).

يغطّي بنود v57.5/v58.2 لتقوية أساس الوكيل (v55/v56):

- ``validate_tool_args``: يرفض غير-القاموس، الحقل المطلوب المفقود، القيمة خارج enum؛
  ويقبل الوسائط الصحيحة (مع تجاهل الاختياريّ الغائب).
- ``malformed_result``: مغلّف صريح غير-منفَّذ (fail-closed) لا يتطلّب موافقة.
- ``sanitize_tool_result``: allowlist للحقول، تجريد HTML/zero-width، سقف حجم، وسم المصدر؛
  ولا يرفع استثناءً أبداً.
- **العقد**: كلّ أداة ``mutating`` صارت ``requires_approval`` (الثابت يُفرَض وقت البناء)،
  وثلاث أدوات v55 المتوسّطة (create_scouting_task/request_imagery_backfill/draft_recommendation)
  صارت تتطلّب موافقة صراحةً في السجلّ والمرآة معاً.
- **حلقة الأدوات**: الوسائط المشوّهة تُرفَض قبل أيّ تنفيذ/طلب موافقة، ونتائج القراءة تُعقَّم
  قبل عودتها للنموذج بينما تبقى مغلّفات الموافقة كما هي.

منطق صرف — وظيفة Unit Tests (لا خدمات، لا نموذج حيّ).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_governance as G  # noqa: E402
from services.ai_agronomist import tool_loop as L  # noqa: E402
from shared.ai import tool_registry as REG  # noqa: E402


# ── تحقّق الوسائط ────────────────────────────────────────────────────────────
def test_validate_rejects_non_dict():
    ok, reason = G.validate_tool_args("get_field_state", ["not", "a", "dict"])
    assert ok is False
    assert reason == "invalid_arguments_not_object"


def test_validate_rejects_missing_required():
    ok, reason = G.validate_tool_args("get_field_state", {})  # field_id مطلوب
    assert ok is False
    assert reason == "missing_required:field_id"


def test_validate_rejects_empty_required():
    ok, reason = G.validate_tool_args("get_field_state", {"field_id": ""})
    assert ok is False
    assert reason == "missing_required:field_id"


def test_validate_rejects_bad_enum():
    ok, reason = G.validate_tool_args(
        "detect_field_boundaries", {"bbox": [1, 2, 3, 4], "source": "thermal"}
    )
    assert ok is False
    assert reason == "invalid_enum:source"


def test_validate_accepts_good_args_and_optional_absent():
    ok, reason = G.validate_tool_args("get_truecolor_scene", {"field_id": "f1"})  # date اختياريّ
    assert ok is True
    assert reason is None


def test_validate_accepts_valid_enum_case_insensitive():
    ok, _ = G.validate_tool_args(
        "detect_field_boundaries", {"bbox": [1, 2, 3, 4], "source": "NDVI"}
    )
    assert ok is True


# ── مغلّف الفشل ──────────────────────────────────────────────────────────────
def test_malformed_result_is_fail_closed():
    r = G.malformed_result("get_field_state", "call-1", "missing_required:field_id")
    assert r["outcome"] == "malformed_tool_call"
    assert r["requires_approval"] is False
    assert r["data"] is None
    assert r["result_summary"] == "rejected:missing_required:field_id"
    assert r["tool_call_id"] == "call-1"


# ── تعقيم النتائج ────────────────────────────────────────────────────────────
def test_sanitize_strips_html_and_allowlists_fields():
    dirty = {
        "tool": "get_field_state",
        "outcome": "executed",
        "data": {"note": "<script>alert(1)</script>حالة الحقل"},
        "secret_internal": "must-not-pass",  # ليس في allowlist
    }
    out = G.sanitize_tool_result(dirty)
    assert out["_sanitized"] is True
    assert out["_source"] == "governed_tool"
    assert "secret_internal" not in out
    assert "<script>" not in str(out)
    assert "حالة الحقل" in str(out)  # المحتوى الشرعيّ باقٍ


def test_sanitize_caps_oversized_payload():
    out = G.sanitize_tool_result(
        {"tool": "get_index_timeline", "outcome": "executed", "data": {"x": "y" * 20000}}
    )
    assert out["data"] == "[omitted:result_too_large]"
    assert out["result_summary"] == "truncated_oversized_result"


def test_sanitize_never_raises_on_non_dict():
    out = G.sanitize_tool_result("not-a-dict")  # type: ignore[arg-type]
    assert out["outcome"] == "sanitized_non_dict_result"
    assert out["_sanitized"] is True


# ── العقد: كلّ أداة مُعدِّلة تتطلّب موافقة ─────────────────────────────────────
def test_every_mutating_tool_requires_approval():
    for t in REG.TOOLS:
        if t.mutating:
            assert t.requires_approval, f"أداة مُعدِّلة بلا موافقة: {t.name}"


def test_construction_rejects_mutating_without_approval():
    with pytest.raises(ValueError):
        REG.ToolSpec("bad_mut", "x", "medium", REG.CAN_CREATE_TASKS, True, False)


def test_v55_medium_tools_now_require_approval():
    for name in ("create_scouting_task", "request_imagery_backfill", "draft_recommendation"):
        spec = REG.get_tool(name)
        assert spec is not None
        assert spec.mutating is True
        assert spec.requires_approval is True, name


# ── حلقة الأدوات: رفض المشوّه قبل التنفيذ + تعقيم نتائج القراءة ────────────────
def _fetcher(name, params):
    return {"index": "ndvi", "value": 0.42}


def test_loop_rejects_malformed_before_execution():
    audit: list[dict] = []
    out = L.run_tool_calls(
        [{"tool": "get_field_state", "params": {}, "id": "c1"}],  # field_id مفقود
        allowed_capabilities=["can_read_field_data"],
        fetcher=_fetcher,
        tenant_id="t1",
        actor="ai",
        timestamp="2026-07-01T00:00:00Z",
        audit_saver=audit.append,
    )
    res = out["tool_calls"][0]
    assert res["outcome"] == "malformed_tool_call"
    assert res["tool_call_id"] == "c1"
    assert len(audit) == 1  # المشوّه دُوِّن أيضاً


def test_loop_sanitizes_read_results_but_not_pending():
    out = L.run_tool_calls(
        [
            {"tool": "get_field_state", "params": {"field_id": "f1"}, "id": "r1"},
            {
                "tool": "create_scouting_task",
                "params": {"field_id": "f1", "zone": "z"},
                "id": "m1",
            },
        ],
        allowed_capabilities=["can_read_field_data", "can_create_tasks"],
        fetcher=_fetcher,
        tenant_id="t1",
        actor="ai",
        timestamp="2026-07-01T00:00:00Z",
    )
    by_id = {r["tool_call_id"]: r for r in out["tool_calls"]}
    # نتيجة القراءة مُعقَّمة (موسومة)
    assert by_id["r1"]["_sanitized"] is True
    assert by_id["r1"]["_source"] == "governed_tool"
    # مغلّف الموافقة غير مُعقَّم (يحمل approval_id/input_hash للواجهة)
    assert by_id["m1"]["outcome"] == L.OUTCOME_PENDING_APPROVAL
    assert "_sanitized" not in by_id["m1"]
    assert by_id["m1"]["approval_id"]
    assert len(out["pending_approvals"]) == 1
