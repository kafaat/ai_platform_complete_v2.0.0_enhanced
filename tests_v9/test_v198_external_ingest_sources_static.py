"""حارس ساكن v198 (SCOUT-INGEST-01 / B1.2b) — سجلّ الاعتماد + resolver آمن + مالك مُصرَّح.

يؤكّد (بلا قاعدة): RLS FORCE (مسافة واحدة، درس #179) + WITH CHECK + resolver SECURITY DEFINER +
REVOKE FROM PUBLIC · تسجيل الهجرة في المُشغّلَين + الملكيّة · **حسم مالك الدالّة في bootstrap**
(دور sahool_ingest_resolver: NOSUPERUSER BYPASSRLS + ALTER FUNCTION OWNER) في كلا سكربتَي bootstrap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MIG = _ROOT / "migrations" / "v198_external_ingest_sources.sql"
_MANIFEST = _ROOT / "migrations" / "MANIFEST.txt"
_RUNNER = _ROOT / "scripts_v9" / "run_migrations.sql"
_OWNERSHIP = _ROOT / "docs" / "architecture" / "db_ownership.yml"
_BOOTSTRAP = _ROOT / "migrations" / "bootstrap_postgres.sh"
_COMPOSE_BOOT = _ROOT / "migrations" / "apply_in_compose.sh"


def _sql() -> str:
    return _MIG.read_text(encoding="utf-8")


def test_rls_force_single_space_and_with_check() -> None:
    s = _sql()
    assert "ALTER TABLE external_ingest_sources FORCE ROW LEVEL SECURITY;" in s  # مسافة واحدة
    assert "WITH CHECK" in s and "app.current_tenant" in s
    assert "NULLIF(current_setting(" in s


def test_resolver_is_security_definer_and_revoked_from_public() -> None:
    s = _sql()
    assert "CREATE OR REPLACE FUNCTION resolve_ingest_source" in s
    assert "SECURITY DEFINER" in s
    assert "enabled = true" in s  # يعيد المُفعَّل فقط
    assert "REVOKE ALL ON FUNCTION resolve_ingest_source(TEXT) FROM PUBLIC" in s


def test_registered_in_runners_and_ownership() -> None:
    name = "v198_external_ingest_sources.sql"
    assert name in _MANIFEST.read_text(encoding="utf-8")
    assert name in _RUNNER.read_text(encoding="utf-8")
    own = _OWNERSHIP.read_text(encoding="utf-8")
    assert "external_ingest_sources:" in own and name in own


def test_owner_role_settled_in_both_bootstraps() -> None:
    """حسم مالك الدالّة (سؤال FORCE↔DEFINER): دور BYPASSRLS يملك الدالّة، في كلا السكربتَين."""
    for path in (_BOOTSTRAP, _COMPOSE_BOOT):
        b = path.read_text(encoding="utf-8")
        assert "sahool_ingest_resolver" in b, f"دور المالك غائب: {path.name}"
        assert "BYPASSRLS" in b
        assert "ALTER FUNCTION resolve_ingest_source(TEXT) OWNER TO sahool_ingest_resolver" in b
        assert "GRANT SELECT ON external_ingest_sources TO sahool_ingest_resolver" in b
