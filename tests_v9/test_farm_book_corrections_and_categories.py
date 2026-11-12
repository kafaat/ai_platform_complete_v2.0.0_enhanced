"""Corrections, categories and windows in the simple farm book (append-only ledger).

The farm book never edits a stored entry: a mistake is corrected by a *reversing entry*
(``reverses_entry_id``) that mirrors the original, and a credit purchase is closed by
*payment* entries (``settles_entry_id``). Each test below states the accounting property
the reports must keep, on ``core.simple_farm_book.summarize_entries`` (pure) and, where the
property is enforced when an entry is written, on the router's write-time checks.

Properties:

* a reversal counts against the ORIGINAL's category, so the per-category sums over monthly
  windows equal the season (all-time) breakdown, and no category appears that exists only
  on a reversal (case a/f; the defect reproduced on main 85625c4);
* an as-of cut-off between an original and its reversal keeps the original in full (c);
* payments reduce the payable to their party; overpayment is refused when written (d);
* reversing a credit entry that already has payments, or paying an entry that is a
  reversal or has been reversed, is refused when written: the report cannot represent the
  result (the party's payable would go negative and silently cancel another debt) (e).
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
ROUTER = PLATFORM / "api" / "routers" / "simple_farm_book.py"


def _load_core():
    # Loaded by path: several services ship a top-level ``core`` package.
    return _load("farm_book_core_under_test", PLATFORM / "core" / "simple_farm_book.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


summarize_entries = _load_core().summarize_entries


def _entry(entry_id: str, **over) -> dict:
    base = {
        "entry_id": entry_id,
        "entry_type": "expense",
        "direction": "outflow",
        "payment_method": "cash",
        "category": "fertilizer",
        "amount": 100000.0,
        "currency": "YER",
        "party_id": None,
        "settles_entry_id": None,
        "reverses_entry_id": None,
    }
    if over.get("entry_type") == "income":
        base["direction"] = "inflow"
    return base | over


def _reversal_of(original: dict, entry_id: str, **over) -> dict:
    """A reversing row as the router's summary query returns it: the reversal's own fields
    plus ``original_category`` carried from the original through the LEFT JOIN."""
    row = {
        **original,
        "entry_id": entry_id,
        "reverses_entry_id": original["entry_id"],
        "original_category": original["category"],
    }
    return row | over


def _assert_months_add_up_by_category(months: list[list[dict]]) -> None:
    season = summarize_entries([e for month in months for e in month])
    reports = [summarize_entries(month) for month in months]
    for key in ("expense_breakdown", "income_breakdown"):
        categories = set(season[key]).union(*(r[key] for r in reports))
        for category in categories:
            monthly = sum(r[key].get(category, 0.0) for r in reports)
            assert monthly == season[key].get(category, 0.0), (key, category, reports, season)
    real = {e["category"] for month in months for e in month if not e.get("reverses_entry_id")}
    phantom = {
        c for r in reports for key in ("expense_breakdown", "income_breakdown") for c in r[key]
    }
    assert phantom <= real, (
        f"a category that exists only on a reversal reached a report: {phantom - real}"
    )
    for key in ("total_expenses", "total_income", "net", "cash_balance_effect"):
        assert sum(r[key] for r in reports) == season[key], key


# --------------------------------------------------------------------------- case a / b / f


def test_a_cross_month_reversal_with_a_different_category_nets_in_the_original_category():
    e1 = _entry("E1", category="fertilizer", occurred_on="2026-12-10")
    e2 = _reversal_of(e1, "E2", category="تصحيح", occurred_on="2027-01-05")
    assert summarize_entries([e1, e2])["expense_breakdown"] == {}
    assert summarize_entries([e1])["expense_breakdown"] == {"fertilizer": 100000.0}
    assert summarize_entries([e2])["expense_breakdown"] == {"fertilizer": -100000.0}
    _assert_months_add_up_by_category([[e1], [e2]])


def test_b_cross_month_reversal_with_the_same_category_nets_per_category():
    e1 = _entry("E1", occurred_on="2026-12-10")
    e2 = _reversal_of(e1, "E2", occurred_on="2027-01-05")
    other = _entry("E3", category="seed", amount=4000.0, occurred_on="2027-01-08")
    _assert_months_add_up_by_category([[e1], [e2, other]])
    assert summarize_entries([e1, e2, other])["expense_breakdown"] == {"seed": 4000.0}


def test_a_reversal_row_without_a_carried_category_falls_back_to_its_own():
    # Rows from a caller that does not carry ``original_category`` keep the old behaviour.
    e1 = _entry("E1")
    e2 = _reversal_of(e1, "E2")
    e2.pop("original_category")
    assert summarize_entries([e2])["expense_breakdown"] == {"fertilizer": -100000.0}


def test_f_cross_month_income_reversal_nets_receivable_and_income_category():
    i1 = _entry(
        "I1",
        entry_type="income",
        category="harvest_sale",
        payment_method="credit",
        party_id="customer-1",
        amount=50000.0,
        occurred_on="2026-12-20",
    )
    i2 = _reversal_of(i1, "I2", category="تصحيح", occurred_on="2027-01-03")
    _assert_months_add_up_by_category([[i1], [i2]])
    december, january = summarize_entries([i1]), summarize_entries([i2])
    assert december["income_breakdown"] == {"harvest_sale": 50000.0}
    assert december["total_receivable"] == 50000.0
    assert january["income_breakdown"] == {"harvest_sale": -50000.0}
    season = summarize_entries([i1, i2])
    assert season["total_receivable"] == 0
    assert season["income_breakdown"] == {}


# --------------------------------------------------------------------------- case c


def test_c_as_of_cut_off_between_original_and_reversal_keeps_the_original():
    e1 = _entry("E1", payment_method="credit", party_id="supplier-1", occurred_on="2026-12-10")
    e2 = _reversal_of(e1, "E2", category="تصحيح", occurred_on="2027-01-05")
    as_of_dec_31 = summarize_entries([e1])
    assert as_of_dec_31["total_expenses"] == 100000.0
    assert as_of_dec_31["total_payable"] == 100000.0
    assert as_of_dec_31["expense_breakdown"] == {"fertilizer": 100000.0}
    after_both = summarize_entries([e1, e2])
    assert after_both["total_expenses"] == 0
    assert after_both["total_payable"] == 0
    assert after_both["expense_breakdown"] == {}


# --------------------------------------------------------------------------- case d / e


def _credit_purchase() -> dict:
    return _entry("C1", payment_method="credit", party_id="supplier-1", amount=12000.0)


def _payment(entry_id: str, amount: float) -> dict:
    return _entry(
        entry_id,
        entry_type="payment",
        party_id="supplier-1",
        settles_entry_id="C1",
        settled_entry_type="expense",
        amount=amount,
    )


def test_d_payments_reduce_the_party_payable_to_zero():
    credit = _credit_purchase()
    first = summarize_entries([credit, _payment("P1", 5000.0)])
    assert (first["total_payable"], first["cash_balance_effect"]) == (7000.0, -5000.0)
    assert first["total_expenses"] == 12000.0  # a payment is not a second expense
    second = summarize_entries([credit, _payment("P1", 5000.0), _payment("P2", 7000.0)])
    assert (second["total_payable"], second["cash_balance_effect"]) == (0.0, -12000.0)
    assert second["total_expenses"] == 12000.0


def _function_source(name: str) -> str:
    source = ROUTER.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name} not found in {ROUTER}")


def _selected_columns(function_source: str) -> set[str]:
    """Columns of the ``SELECT … FROM farm_ledger_entries … FOR UPDATE`` that locks the
    referenced original inside a write-time check."""
    match = re.search(r"SELECT(.*?)FROM farm_ledger_entries", function_source, re.S)
    assert match, function_source
    return {c.strip().split(".")[-1] for c in match.group(1).split(",")}


def test_d_overpayment_is_refused_when_written():
    body = _function_source("_prepare_payment")
    assert "payment_exceeds_remaining_debt" in body
    assert "FOR UPDATE" in body  # concurrent payments serialise on the original row


def test_e_reversing_a_settled_credit_entry_is_refused_when_written():
    body = _function_source("_assert_reversal")
    assert "settles_entry_id=$2" in body, "the reversal check must look for settlements"
    assert "cannot_reverse_entry_with_settlements" in body


def test_e_paying_a_reversal_or_a_reversed_entry_is_refused_when_written():
    body = _function_source("_prepare_payment")
    assert "reverses_entry_id" in _selected_columns(body)
    assert "cannot_settle_a_reversal" in body
    assert "cannot_settle_reversed_entry" in body


# --------------------------------------------------------------------------- write-time mirror


def test_a_reversal_must_mirror_the_original_category_and_allocation_when_written():
    body = _function_source("_assert_reversal")
    columns = _selected_columns(body)
    for column in ("category", "farm_id", "field_id", "season_id", "occurred_on"):
        assert column in columns, column
    assert "req.category" in body
    assert "reversal_must_mirror_original" in body
    assert "reversal_cannot_predate_original" in body


def test_the_summary_query_carries_the_original_category_and_allocation():
    body = _function_source("_fetch_entries")
    assert re.search(r"\w+\.category AS original_category", body), body
    assert re.search(r"\w+\.entry_id\s*=\s*e\.reverses_entry_id", body), body
    filters = _function_source("_entry_filters")
    assert "reverses_entry_id" in filters or "orig." in filters, (
        "dimension filters must follow the original for a reversing row"
    )


# --------------------------------------------------------------------------- case g


def test_g_mixed_currencies_in_one_window_are_never_summed():
    e1 = _entry("E1", currency="YER")
    usd = _entry("E2", currency="USD", amount=10.0)
    assert summarize_entries([e1, usd])["status"] == "multiple_currencies"
    # A reversal mirrors its original's currency, so cancelling never mixes currencies.
    e3 = _reversal_of(usd, "E3")
    assert summarize_entries([e1, usd, e3])["status"] == "ok"


# --------------------------------------------------------------------------- case h / i


def _load_costing():
    return _load("farm_costing_under_test", PLATFORM / "core" / "farm_costing.py")


def test_h_operations_ledger_has_no_negative_cost_correction_path():
    # A wrong operation cost cannot be offset by a negative line: the costing core refuses
    # it, so a correction needs its own mechanism (none exists yet; see the PR notes).
    costing = _load_costing()
    line = costing.ActualCostLine("op1", "s1", "fertilizer", actual_cost=-500.0)
    with pytest.raises(ValueError):
        costing.compute_profitability("s1", revenue=0.0, cost_lines=[line])


def test_i_no_module_sums_the_farm_book_with_the_operations_ledger():
    # The same purchase may be recorded as an operation's analytic cost and as a farm-book
    # expense; there is no link column between the two, so adding them double counts.
    readers = [
        path
        for path in sorted((ROOT / "services").rglob("*.py"))
        if "farm_ledger_entries" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert readers, "the farm book's table must be read somewhere"
    for path in readers:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "farm_operation_ledger" not in text, (
            f"{path} reads both books; farm-book expenses and operation costs for the same "
            "purchase would be double counted"
        )
