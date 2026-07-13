#!/usr/bin/env python3
"""Static ratchet for v183 DB-owned immutable content lineage (renumbered from P0-fix v182)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
s = (ROOT / "migrations/v183_decision_lineage_integrity_hardening.sql").read_text()
for token in (
    "ALTER TABLE review_decisions ADD COLUMN IF NOT EXISTS tenant_id",
    "ALTER TABLE review_decisions FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation ON review_decisions",
    "ALTER COLUMN source_content_digest SET NOT NULL",
    "ALTER COLUMN content_digest SET NOT NULL",
    "VALIDATE CONSTRAINT",
    "NEW.content_digest := sahool_",
    "append-only; create a new governed row instead",
    "BEFORE UPDATE OR DELETE",
):
    assert token in s, token
manifest = (ROOT / "migrations/MANIFEST.txt").read_text()
runner = (ROOT / "scripts_v9/run_migrations.sql").read_text()
for n in range(167, 183):
    assert f"v{n}_" in manifest, f"v{n} missing from manifest"
assert "migrations/v183_decision_lineage_integrity_hardening.sql" in runner
print("decision lineage v183 guard: PASS")
