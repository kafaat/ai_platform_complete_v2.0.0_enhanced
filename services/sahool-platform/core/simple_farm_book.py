"""Pure calculations and exports for the farmer-facing simple farm book."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any


def _drop_reversed(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude append-only corrections from totals: a reversing entry and the
    original it cancels both net to zero, so neither should count. Everything else
    passes through unchanged (order preserved)."""
    reversed_ids = {str(e["reverses_entry_id"]) for e in entries if e.get("reverses_entry_id")}
    return [
        e
        for e in entries
        if not e.get("reverses_entry_id") and str(e.get("entry_id") or "") not in reversed_ids
    ]


def summarize_entries(entries: list[dict[str, Any]], *, area_ha: float | None = None) -> dict:
    entries = _drop_reversed(entries)
    currencies = {str(e["currency"]) for e in entries}
    if len(currencies) > 1:
        return {
            "status": "multiple_currencies",
            "currencies": sorted(currencies),
            "entries_count": len(entries),
        }
    currency = next(iter(currencies), "YER")
    expenses = income = cash_balance = 0.0
    expense_breakdown: dict[str, float] = defaultdict(float)
    income_breakdown: dict[str, float] = defaultdict(float)
    payable: dict[str, float] = defaultdict(float)
    receivable: dict[str, float] = defaultdict(float)

    by_id = {str(e["entry_id"]): e for e in entries}
    for entry in entries:
        amount = float(entry["amount"])
        kind = entry["entry_type"]
        direction = entry["direction"]
        party = str(entry.get("party_id") or "")
        if kind == "expense":
            expenses += amount
            expense_breakdown[str(entry["category"])] += amount
            if entry["payment_method"] == "cash":
                cash_balance -= amount
            else:
                payable[party] += amount
        elif kind == "income":
            income += amount
            income_breakdown[str(entry["category"])] += amount
            if entry["payment_method"] == "cash":
                cash_balance += amount
            else:
                receivable[party] += amount
        elif kind == "payment":
            original = by_id.get(str(entry.get("settles_entry_id") or ""))
            original_type = (original or {}).get("entry_type") or entry.get("settled_entry_type")
            if original_type == "expense":
                payable[party] -= amount
                cash_balance -= amount
            elif original_type == "income":
                receivable[party] -= amount
                cash_balance += amount
            elif direction == "outflow":
                cash_balance -= amount
            else:
                cash_balance += amount

    total_payable = sum(max(0.0, value) for value in payable.values())
    total_receivable = sum(max(0.0, value) for value in receivable.values())
    net = income - expenses
    per_ha = None
    if area_ha is not None and area_ha > 0:
        per_ha = {
            "expense": round(expenses / area_ha, 2),
            "income": round(income / area_ha, 2),
            "net": round(net / area_ha, 2),
        }
    return {
        "status": "ok",
        "currency": currency,
        "entries_count": len(entries),
        "total_expenses": round(expenses, 2),
        "total_income": round(income, 2),
        "net": round(net, 2),
        "cash_balance_effect": round(cash_balance, 2),
        "total_payable": round(total_payable, 2),
        "total_receivable": round(total_receivable, 2),
        "expense_breakdown": dict(expense_breakdown),
        "income_breakdown": dict(income_breakdown),
        "per_hectare": per_ha,
    }


_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Neutralize spreadsheet formula injection in exported cells.

    A farmer-supplied category/description/party name beginning with ``= + - @``
    (or a leading tab/CR) is treated as a formula by Excel/LibreOffice on open. We
    prefix such text cells with an apostrophe so they render as literal text; csv
    quoting alone does NOT prevent this. Non-string values pass through unchanged.
    """
    if isinstance(value, str) and value.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


def entries_csv(entries: list[dict[str, Any]]) -> bytes:
    out = io.StringIO()
    fields = [
        "entry_id",
        "occurred_on",
        "entry_type",
        "payment_method",
        "category",
        "amount",
        "currency",
        "party_name",
        "farm_id",
        "field_id",
        "season_id",
        "description",
        "receipt_document_id",
    ]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for entry in entries:
        writer.writerow({key: _csv_safe(value) for key, value in entry.items()})
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def monthly_pdf(entries: list[dict[str, Any]], summary: dict, title: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("reportlab_not_installed") from exc
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    width, height = A4
    y = height - 50
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, title)
    y -= 28
    pdf.setFont("Helvetica", 10)
    for label, value in (
        ("Currency", summary.get("currency")),
        ("Expenses", summary.get("total_expenses")),
        ("Income", summary.get("total_income")),
        ("Net", summary.get("net")),
        ("Cash effect", summary.get("cash_balance_effect")),
        ("Payable", summary.get("total_payable")),
        ("Receivable", summary.get("total_receivable")),
    ):
        pdf.drawString(40, y, f"{label}: {value}")
        y -= 16
    y -= 8
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, y, "Date | Type | Payment | Category | Amount")
    y -= 15
    pdf.setFont("Helvetica", 8)
    for entry in entries:
        if y < 45:
            pdf.showPage()
            y = height - 45
            pdf.setFont("Helvetica", 8)
        line = (
            f"{entry.get('occurred_on')} | {entry.get('entry_type')} | "
            f"{entry.get('payment_method')} | {entry.get('category')} | "
            f"{entry.get('amount')} {entry.get('currency')}"
        )
        pdf.drawString(40, y, line[:115])
        y -= 13
    pdf.save()
    return stream.getvalue()
