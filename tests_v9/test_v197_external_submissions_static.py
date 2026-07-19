"""حارس ساكن v197 (SCOUT-INGEST-01 / B1.2a) — عقد RLS الحرفيّ + immutability كسمة + التزامن.

يؤكّد على مصدر الهجرة (بلا قاعدة): FORCE RLS + WITH CHECK + ``current_setting('app.current_tenant')`` ·
trigger BEFORE DELETE (raw غير قابل للمحو — سمة لا grant) · dedup فريد ·
تسجيل الهجرة في كلا المُشغّلَين وفي db_ownership.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MIG = _ROOT / "migrations" / "v197_external_submissions_ingest.sql"
_MANIFEST = _ROOT / "migrations" / "MANIFEST.txt"
_RUNNER = _ROOT / "scripts_v9" / "run_migrations.sql"
_OWNERSHIP = _ROOT / "docs" / "architecture" / "db_ownership.yml"


def _sql() -> str:
    return _MIG.read_text(encoding="utf-8")


def test_rls_force_enabled() -> None:
    s = _sql()
    assert "ENABLE ROW LEVEL SECURITY" in s
    assert "FORCE  ROW LEVEL SECURITY" in s or "FORCE ROW LEVEL SECURITY" in s


def test_policy_has_using_and_with_check_on_tenant_guc() -> None:
    s = _sql()
    assert "CREATE POLICY tenant_isolation" in s
    assert "WITH CHECK" in s
    # داخل DO/EXECUTE تُضاعَف علامات الاقتباس؛ نطابق الجوهر بصرف النظر عن التصعيد.
    assert "app.current_tenant" in s
    assert "NULLIF(current_setting(" in s  # سياق فارغ لا يطابق ⇒ fail-closed
    assert "USING" in s


def test_append_only_delete_trigger_is_a_property_not_a_grant() -> None:
    """immutability عبر trigger BEFORE DELETE يرفع استثناء — لا اعتماد على غياب grant."""
    s = _sql()
    assert "BEFORE DELETE ON external_submissions" in s
    assert "RAISE EXCEPTION" in s
    assert "external_submissions_forbid_delete" in s


def test_dedup_unique_index_and_status_check() -> None:
    s = _sql()
    assert "UNIQUE INDEX" in s and "(tenant_id, idempotency_key)" in s
    assert "trust_status IN ('untrusted','accepted','quarantined')" in s


def test_migration_registered_in_both_runners_and_ownership() -> None:
    name = "v197_external_submissions_ingest.sql"
    assert name in _MANIFEST.read_text(encoding="utf-8")
    assert name in _RUNNER.read_text(encoding="utf-8")
    own = _OWNERSHIP.read_text(encoding="utf-8")
    assert "external_submissions:" in own and name in own
