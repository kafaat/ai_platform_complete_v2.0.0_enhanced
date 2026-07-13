"""حارس ساكن: content_digest عمود أوّليّ يُنتشَر عبر سلسلة القرار (v167).

الفجوة (شهادة البيئة الحيّة، المرحلة 4): السلسلة كانت تُنتشِر النَّسَب بـ
candidate_lineage_id (16-hex، أعلى تصادماً) فقط؛ الـcontent_digest الكامل (sha256، 64-hex)
كان مدفوناً في decision_value JSONB وغير قابل للفهرسة/الاستعلام عبر الجداول. هذا الحارس
يمنع انحدار الإغلاق: الهجرة تُضيف العمود المفهرَس، والتوصيل يملؤه من الرأس (decision_record)
ويُنتشِره للحلقات الأدنى بالبحث عبر decision_id. منطق صرف (قراءة ملفّات) — `pytest -m unit`.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = _ROOT / "migrations" / "v167_mpc_content_digest_lineage.sql"
_PERSIST = _ROOT / "services" / "decision-service" / "persistence.py"
_BRIDGE = _ROOT / "services" / "sahool-platform" / "api" / "lexicographic_mpc_bridge.py"
_SOLVER = _ROOT / "services" / "sahool-platform" / "api" / "lexicographic_irrigation_mpc.py"

_CHAIN_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
)


def _read(rel: pathlib.Path) -> str:
    return rel.read_text(encoding="utf-8")


# ── الهجرة تُضيف العمود المفهرَس على كلّ جداول السلسلة (إضافيّة، NULL-able، idempotent) ──
def test_migration_adds_content_digest_column_and_indexes():
    src = _read(_MIGRATION)
    for table in _CHAIN_TABLES:
        assert f"ALTER TABLE {table}" in src, f"عمود مفقود لـ{table}"
        assert f"idx_{table}_content_digest" in src, f"فهرس تتبّع مفقود لـ{table}"
    assert src.count("ADD COLUMN IF NOT EXISTS content_digest TEXT") == len(_CHAIN_TABLES)
    # الفهارس مُقيَّدة بالمستأجِر (تتّسق مع RLS).
    assert src.count("(tenant_id, content_digest)") == len(_CHAIN_TABLES)
    # additive/idempotent: لا DROP، لا NOT NULL على العمود الجديد.
    assert "DROP COLUMN" not in src
    assert "content_digest TEXT NOT NULL" not in src


# ── الهجرة مُسجَّلة في كلا المُشغّلَين (بوّابة الإنتاج تفشل إن نقصت من run_migrations) ──
def test_migration_registered_in_both_runners():
    manifest = _read(_ROOT / "migrations" / "MANIFEST.txt")
    runner = _read(_ROOT / "scripts_v9" / "run_migrations.sql")
    assert "v167_mpc_content_digest_lineage.sql" in manifest
    assert "v167_mpc_content_digest_lineage.sql" in runner


# ── الرأس: content_digest يُستخرَج من decision_value ويُدرَج في decision_record ──
def test_decision_record_persists_content_digest_from_evidence():
    src = _read(_PERSIST)
    assert '(payload.decision_value or {}).get("content_digest")' in src, (
        "content_digest يجب أن يُستخرَج من decision_value مثل candidate_lineage_id"
    )
    # INSERT + ON CONFLICT يشملان العمود (COALESCE يحفظ القيمة السابقة عند الغياب).
    assert (
        "content_digest = COALESCE(EXCLUDED.content_digest, decision_record.content_digest)" in src
    )


# ── دالّة انتشار server-side: تقرأ الـdigest من الرأس داخل معاملة المستأجِر ──
def test_lookup_helper_reads_from_head_row():
    src = _read(_PERSIST)
    assert "async def _lookup_content_digest" in src
    assert (
        "SELECT content_digest FROM decision_record WHERE tenant_id=$1::uuid AND decision_id=$2"
        in src
    )


# ── الحلقات الأدنى تُنتشِر الـdigest server-side (لا ثقة بقيمة العميل) ──
def test_downstream_links_propagate_content_digest():
    src = _read(_PERSIST)
    # كلّ حلقة أدنى: تربط المستأجِر + تبحث عن الـdigest + تُدرِجه مع COALESCE.
    for table in ("dispatch_decisions", "outcome_record", "recommendation_outcomes"):
        assert (
            f"content_digest = COALESCE(EXCLUDED.content_digest, {table}.content_digest)" in src
        ), f"{table} يجب أن يُنتشِر content_digest مع COALESCE"
    # ثلاثة استدعاءات انتشار (dispatch + outcome + recommendation).
    assert src.count("await _lookup_content_digest(") == 3


# ── الرأس المُنتِج: الجسر يضع content_digest في decision_value (وإلا بقي العمود NULL) ──
def test_bridge_writes_content_digest_into_evidence():
    bridge = _read(_BRIDGE)
    assert '"content_digest": digest' in bridge
    # to_dict للقرار (=decision_value) يحمل content_digest — مصدر الاستخراج في الرأس.
    solver = _read(_SOLVER)
    assert '"content_digest": self.content_digest' in solver
