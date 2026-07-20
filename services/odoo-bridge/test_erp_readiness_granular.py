"""وحدة: جاهزيّة ERPNext التفصيليّة الصادقة (تدقيق عميق — readiness مفصّل لا علم واحد).

الاتصال قد يكون أخضر بينما نشرُ القيود المحاسبيّة غير متاح (ربط الحسابات غير مُعدّ).
health() يفصل: erp_connection_ready / account_mapping_configured / field_cost_posting_ready
/ inventory_sync_ready — لا يخفي عجز النشر خلف «connected».

وحدة صرفة — ``pytest -m unit``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from erp_provider import ERPNextProvider  # noqa: E402

pytestmark = pytest.mark.unit


def _stub_auth(provider: ERPNextProvider, ok: bool) -> None:
    async def _auth() -> bool:
        return ok

    provider.authenticate = _auth  # type: ignore[method-assign]


async def test_posting_ready_needs_connection_and_account_mapping():
    p = ERPNextProvider(
        "https://erp.example.com",
        "k",
        "s",
        expense_account="Exp",
        credit_account="Cash",
        company="Co",
    )
    _stub_auth(p, True)
    h = await p.health()
    assert h["erp_connection_ready"] is True
    assert h["account_mapping_configured"] is True
    assert h["field_cost_posting_ready"] is True
    assert h["inventory_sync_ready"] is True


async def test_connected_but_no_account_mapping_cannot_post():
    p = ERPNextProvider("https://erp.example.com", "k", "s")  # لا ربط حسابات
    _stub_auth(p, True)
    h = await p.health()
    assert h["erp_connection_ready"] is True
    assert h["account_mapping_configured"] is False
    assert h["field_cost_posting_ready"] is False  # متّصل لكن لا يستطيع النشر
    assert h["inventory_sync_ready"] is True


async def test_disconnected_nothing_ready_but_mapping_reported():
    p = ERPNextProvider(
        "https://erp.example.com",
        "k",
        "s",
        expense_account="Exp",
        credit_account="Cash",
        company="Co",
    )
    _stub_auth(p, False)
    h = await p.health()
    assert h["erp_connection_ready"] is False
    assert h["field_cost_posting_ready"] is False
    assert h["inventory_sync_ready"] is False
    assert h["account_mapping_configured"] is True  # الإعداد موجود رغم انقطاع الاتصال
