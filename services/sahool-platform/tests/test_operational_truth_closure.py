from decimal import Decimal
from pathlib import Path

from core.operational_truth import content_digest, reconciliation_status

ROOT = Path(__file__).resolve().parents[3]


def test_digest_is_canonical_and_reconciliation_is_calculated():
    assert content_digest({"b": 2, "a": 1}) == content_digest({"a": 1, "b": 2})
    assert reconciliation_status(Decimal("10"), Decimal("10.00"), "matched") == "matched"
    assert reconciliation_status(Decimal("10"), Decimal("9"), "difference") == "difference"


def test_reconciliation_rejects_claim_that_conflicts_with_amounts():
    try:
        reconciliation_status(Decimal("10"), Decimal("9"), "matched")
    except ValueError as exc:
        assert "conflicts" in str(exc)
    else:
        raise AssertionError("mismatched claim must fail closed")


def test_s3_s11_migrations_are_append_only_tenant_bound_and_before_final_catalog():
    s3 = (ROOT / "migrations/v209_historical_weather_sor.sql").read_text()
    s11 = (ROOT / "migrations/v210_erp_reconciliation_ledger.sql").read_text()
    for sql in (s3, s11):
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "FORCE ROW LEVEL SECURITY" in sql
        assert "BEFORE UPDATE OR DELETE" in sql
        assert "current_setting('app.current_tenant'" in sql
    entries = [
        line.strip()
        for line in (ROOT / "migrations/MANIFEST.txt").read_text().splitlines()
        if line.strip().endswith(".sql")
    ]
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries.index("v209_historical_weather_sor.sql") < len(entries) - 1
    assert entries.index("v210_erp_reconciliation_ledger.sql") < len(entries) - 1


def test_operational_truth_router_has_idempotency_and_pit_contracts():
    src = (ROOT / "services/sahool-platform/api/routers/operational_truth.py").read_text()
    for token in (
        "source_record_payload_conflict",
        "provider_event_payload_conflict",
        "as_known_at",
        "at least one historical weather measurement is required",
        "as_known_at_must_include_timezone",
        "_assert_field_in_tenant",
        "season_not_found_for_field",
        "erp_projection_outbox_not_found",
    ):
        assert token in src
