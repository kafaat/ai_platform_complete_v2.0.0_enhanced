"""Phase 23 guard — v123 RLS hardening preserves USING (qual-preserving WITH CHECK).

v122 backfilled WITH CHECK but replaced each policy's USING with a constructed
tenant-only predicate (safe for the pure-tenant policies it touched, but an unsafe
pattern). v123 is the corrected successor: it derives WITH CHECK from the policy's
EXISTING USING qual without modifying USING, so ownership/role/service conditions
survive. These static guards lock that contract in and keep v123 the manifest tail.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V123 = ROOT / "migrations/v123_rls_with_check_preserve_using.sql"


def test_v123_exists_and_is_catalog_driven_idempotent():
    sql = V123.read_text(encoding="utf-8")
    assert "pg_policies" in sql, "v123 must be catalog-driven (reads pg_policies)"
    assert "with_check IS NULL" in sql, "v123 must only touch policies lacking WITH CHECK"
    assert "ALTER POLICY" in sql and "WITH CHECK" in sql
    assert "RAISE EXCEPTION" in sql, "v123 must fail-closed if any tenant write policy stays unchecked"


def test_v123_preserves_using_qual_and_does_not_construct_replacement():
    """The core contract: USING is taken from the existing qual (pol.qual), and the
    migration does NOT build a tenant-only predicate to overwrite USING (the v122 footgun)."""
    sql = V123.read_text(encoding="utf-8")
    # USING is fed from the catalog qual, mirrored into WITH CHECK.
    assert "pol.qual" in sql, "v123 must preserve the existing USING via pol.qual"
    assert "USING (%s) WITH CHECK (%s)" in sql, "v123 must keep USING and add WITH CHECK"
    # Must NOT reconstruct a tenant-only predicate and assign it to USING (v122's pattern).
    assert "predicate := " not in sql, (
        "v123 must not construct a replacement predicate for USING (that is the v122 footgun)"
    )


def test_v123_is_last_manifest_entry():
    entries = [
        ln.strip()
        for ln in (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert entries[-1] == "v123_rls_with_check_preserve_using.sql", (
        f"v123 must be the LAST manifest entry (catalog-driven tail); got {entries[-1]}"
    )


def test_v123_listed_in_legacy_runner():
    runner = (ROOT / "scripts_v9/run_migrations.sql").read_text(encoding="utf-8")
    assert "migrations/v123_rls_with_check_preserve_using.sql" in runner
