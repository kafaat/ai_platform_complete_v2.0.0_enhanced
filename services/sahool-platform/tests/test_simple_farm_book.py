from __future__ import annotations

import csv
import io
from pathlib import Path

from core.simple_farm_book import entries_csv, summarize_entries


def _entry(**over):
    base = {
        "entry_id": "e1",
        "entry_type": "expense",
        "direction": "outflow",
        "payment_method": "cash",
        "category": "fertilizer",
        "amount": 100.0,
        "currency": "YER",
        "party_id": None,
        "settles_entry_id": None,
    }
    return base | over


def test_cash_credit_debt_and_payment_summary() -> None:
    entries = [
        _entry(entry_id="cash-exp", amount=100),
        _entry(
            entry_id="credit-exp",
            payment_method="credit",
            party_id="supplier-1",
            amount=300,
        ),
        _entry(
            entry_id="credit-income",
            entry_type="income",
            direction="inflow",
            payment_method="credit",
            category="harvest_sale",
            party_id="customer-1",
            amount=500,
        ),
        _entry(
            entry_id="supplier-payment",
            entry_type="payment",
            payment_method="cash",
            party_id="supplier-1",
            settles_entry_id="credit-exp",
            amount=120,
        ),
        _entry(
            entry_id="customer-payment",
            entry_type="payment",
            direction="inflow",
            payment_method="cash",
            party_id="customer-1",
            settles_entry_id="credit-income",
            amount=200,
        ),
    ]
    out = summarize_entries(entries, area_ha=2)
    assert out["total_expenses"] == 400
    assert out["total_income"] == 500
    assert out["cash_balance_effect"] == -20
    assert out["total_payable"] == 180
    assert out["total_receivable"] == 300
    assert out["per_hectare"]["expense"] == 200


def test_reversing_entry_and_original_net_to_zero() -> None:
    # A reversal mirrors the original; both drop out of every total (append-only fix).
    entries = [
        _entry(entry_id="exp-1", amount=100),
        _entry(entry_id="exp-2", amount=250),
        _entry(entry_id="rev-of-1", amount=100, reverses_entry_id="exp-1"),
    ]
    out = summarize_entries(entries)
    assert out["entries_count"] == 1  # only exp-2 counts
    assert out["total_expenses"] == 250
    assert out["cash_balance_effect"] == -250


def test_csv_export_neutralizes_formula_injection() -> None:
    payload = entries_csv(
        [
            _entry(
                occurred_on="2026-07-23",
                category="=cmd|'/C calc'!A1",
                description="+HYPERLINK(1)",
                party_name="-2+3",
                receipt_document_id="@SUM(A1)",
            )
        ]
    )
    row = next(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    # Dangerous leading chars are defused with an apostrophe so no cell is a formula.
    assert row["category"].startswith("'=")
    assert row["description"].startswith("'+")
    assert row["party_name"].startswith("'-")
    assert row["receipt_document_id"].startswith("'@")


def test_multiple_currencies_are_not_silently_merged() -> None:
    out = summarize_entries([_entry(), _entry(entry_id="e2", currency="USD")])
    assert out == {
        "status": "multiple_currencies",
        "currencies": ["USD", "YER"],
        "entries_count": 2,
    }


def test_csv_has_utf8_bom_and_expected_rows() -> None:
    payload = entries_csv(
        [
            _entry(
                occurred_on="2026-07-23",
                party_name="مورد",
                farm_id="farm-1",
                field_id="field-1",
                season_id="season-1",
                description="سماد",
                receipt_document_id="doc-1",
            )
        ]
    )
    assert payload.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    assert rows[0]["entry_id"] == "e1"
    assert rows[0]["party_name"] == "مورد"


def test_migration_is_append_only_rls_and_idempotent() -> None:
    root = Path(__file__).resolve().parents[3]
    sql = (root / "migrations/v211_simple_farm_book.sql").read_text(encoding="utf-8")
    for token in (
        "UNIQUE (tenant_id, client_operation_id)",
        "request_digest CHAR(64) NOT NULL",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "BEFORE UPDATE OR DELETE",
        "reverses_entry_id",
        "receipt_document_id",
        "settles_entry_id",
    ):
        assert token in sql
    # The one-reversal-per-entry DB constraint ships as its own migration (v212):
    # merged v211 is never edited in place, so already-applied databases converge.
    v212 = (root / "migrations/v212_farm_book_one_reversal_index.sql").read_text(encoding="utf-8")
    assert "ux_farm_ledger_entries_one_reversal" in v212
    assert "WHERE reverses_entry_id IS NOT NULL" in v212
    entries = [
        line.strip()
        for line in (root / "migrations/MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    # The invariant is ORDER, not a snapshot of the tail. Every new migration is inserted
    # before v206_rls_final_hardening.sql (it re-covers RLS across everything preceding
    # it), so a hardcoded `entries[-7:]` broke on the next insertion and said nothing
    # about what actually matters. Assert the two things that do:
    #   1. v206 is last, exactly once;
    #   2. the farm-book chain keeps its relative order and precedes v206.
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries.count("v206_rls_final_hardening.sql") == 1
    chain = [
        "v211_simple_farm_book.sql",
        "v212_farm_book_one_reversal_index.sql",
        "v213_backfill_runs_single_scene.sql",
        "v214_field_irrigation_source_assignments.sql",
        "v215_yield_map_ingestion.sql",
        "v216_machinery_export.sql",
    ]
    positions = [entries.index(name) for name in chain]
    assert positions == sorted(positions), f"farm-book chain out of order: {positions}"
    assert positions[-1] < entries.index("v206_rls_final_hardening.sql")


def test_router_guards_scope_offline_conflict_and_exports() -> None:
    root = Path(__file__).resolve().parents[3]
    body = (root / "services/sahool-platform/api/routers/simple_farm_book.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "client_operation_id_payload_conflict",
        "payment_exceeds_remaining_debt",
        "receipt_document_not_found_for_tenant",
        "_assert_field_in_tenant",
        "entries_csv",
        "monthly_pdf",
        '"/api/v1/farm-book/balances"',
    ):
        assert token in body
    compile(body, "simple_farm_book.py", "exec")
