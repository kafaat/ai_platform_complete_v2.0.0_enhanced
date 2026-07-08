"""حارس ساكن — ترحيل v149 (evidence_graph_nodes/edges): RLS + فهارس + FK + تسجيل.

لا يمكن اختبار العزل تكامليّاً هنا (يحتاج Postgres)، فنُثبّت ساكناً:
- الجدولان يُنشآن بـFORCE RLS + سياسة tenant_isolation (نمط v148).
- FK إلى field_evidence_snapshots + ON DELETE CASCADE + UNIQUE per snapshot (لا تكرار).
- فهارس (tenant/field/زمن + snapshot) موجودة.
- مُسجَّل في MANIFEST **و** run_migrations.sql. لا أعمدة أسرار.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MIG = REPO / "migrations" / "v149_evidence_graph_nodes_edges.sql"


def _sql() -> str:
    return MIG.read_text(encoding="utf-8")


def test_both_tables_have_force_rls_and_policy():
    sql = _sql()
    for t in ("evidence_graph_nodes", "evidence_graph_edges"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in sql
        assert f"CREATE POLICY tenant_isolation ON {t}" in sql
    assert sql.count("FORCE ROW LEVEL SECURITY") >= 2
    assert "current_setting('app.current_tenant', true)" in sql and "WITH CHECK" in sql


def test_fk_cascade_and_unique_per_snapshot():
    sql = _sql()
    assert "REFERENCES field_evidence_snapshots (id) ON DELETE CASCADE" in sql
    assert "UNIQUE (snapshot_id, node_id)" in sql  # لا تكرار عقدة/لقطة
    assert "UNIQUE (snapshot_id, edge_id)" in sql


def test_required_indexes_present():
    sql = _sql()
    assert "idx_evidence_graph_nodes_snapshot" in sql
    assert "idx_evidence_graph_edges_snapshot" in sql
    assert "idx_evidence_graph_nodes_tenant_field_time" in sql


def test_no_secret_columns():
    sql = _sql().lower()
    for bad in ("password", "token", "secret", "credential"):
        assert bad not in sql


def test_registered_in_both_runners():
    manifest = (REPO / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    run = (REPO / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v149_evidence_graph_nodes_edges.sql" in manifest
    assert "v149_evidence_graph_nodes_edges.sql" in run
