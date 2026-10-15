"""Review persistence must preserve agronomic approval independently of traceability."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agronomic_review_is_stored_on_insert_and_conflict():
    content = (ROOT / "services/sahool-platform/api/phase_runtime_store.py").read_text(encoding="utf-8")
    assert "review_status, agronomically_approved, agronomic_review" in content
    assert "review_status = EXCLUDED.review_status" in content
    assert "agronomically_approved = EXCLUDED.agronomically_approved" in content
    assert "agronomic_review = EXCLUDED.agronomic_review" in content
    assert '_lin["review_status"]' in content
    assert '_lin["agronomically_approved"]' in content
    assert '_lin["review"]' in content


def test_legacy_updates_remain_explicitly_unreviewed_and_false():
    sql = (ROOT / "migrations/v234_learning_agronomic_review.sql").read_text(encoding="utf-8")
    assert "DEFAULT 'unreviewed'" in sql
    assert "DEFAULT FALSE" in sql
    assert "chk_oluj_agronomic_approval_consistency" in sql
    assert "review_status = 'approved'" in sql
    assert "jsonb_array_length" in sql
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert manifest.count("v234_learning_agronomic_review.sql") == 1
    assert manifest.index("v234_learning_agronomic_review.sql") < manifest.index("v206_rls_final_hardening.sql")
