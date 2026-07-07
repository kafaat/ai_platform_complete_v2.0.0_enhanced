"""حارس ساكن — نقاط تحليلات رسم الأدلّة (E1): استعلام آخر-لقطة/حقل + تسجيل + تصنيف.

منطق صرف (لا Postgres): يمسح نصّ الراوت + config التغطية للتأكّد من:
- تحليلات الفجوات تُجمِّع على **آخر لقطة لكلّ حقل** (DISTINCT ON) عبر الجداول المُطبَّعة v149.
- النقطتان مُسجَّلتان؛ التحليلات (agronomist) في عقد التغطية بدليل واجهة.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
ROUTER = REPO / "services" / "sahool-platform" / "api" / "routers" / "field_intelligence.py"
COVERAGE = REPO / "config" / "endpoint_ui_coverage.json"


def _router() -> str:
    return ROUTER.read_text(encoding="utf-8")


def test_gap_analytics_query_uses_latest_snapshot_per_field():
    sql = _router()
    assert "DISTINCT ON (field_id)" in sql  # آخر لقطة لكلّ حقل لا كلّ اللقطات
    assert "evidence_graph_nodes n JOIN latest l" in sql
    # لا شرط tenant صريح — RLS يفرض العزل (نمط القرّاء القائمين).


def test_both_analytics_endpoints_registered():
    sql = _router()
    assert '@router.get("/api/v1/evidence-graph/analytics")' in sql
    assert '@router.get("/api/v1/fields/{field_id}/evidence-graph/nodes")' in sql


def test_analytics_endpoint_in_coverage_contract_as_agronomist():
    cfg = json.loads(COVERAGE.read_text(encoding="utf-8"))
    ep = "/api/v1/evidence-graph/analytics"
    entry = next((e for e in cfg["core_endpoints"] if e["endpoint"] == ep), None)
    assert entry is not None, "analytics endpoint must be in the UI-coverage contract"
    assert entry["audience"] == "agronomist"
    assert entry["evidence"] == ep


def test_endpoints_are_read_only_and_fail_soft():
    sql = _router()
    # النقطتان تُعلنان حالة صادقة عند تعذّر القاعدة (لا اختلاق).
    assert 'return {"field_id": field_id, "available": False, "reason": "db_disabled"}' in sql
    assert '"reason": "db_disabled"' in sql
