#!/usr/bin/env python3
"""حارس CI: يمنع اشتقاق أيّ إيراد/هامش اقتصاديّ من معامل Ky قبل نموذج اقتصاديّ صريح.

نموذج Ky (FAO-33) تقديريّ لاستجابة الغلّة للماء — **ليس** نموذج إنتاج/تسعير. حتى وصول
نموذج اقتصاديّ صريح (إيراد × سعر × جودة)، يجب أن يبقى J3 (الغلّة) معزولاً عن J4 (الهامش):
- سجلّ Ky لا يذكر إيراداً/هامشاً/سعراً.
- المتحكّم يُبقي `economic_margin_delta = None`، وJ4 يُحسَب من الماء فقط (m³×سعر ماء).
- لا سطر يضرب/يجمع مخرَج الغلّة (relative_yield/yield_loss) في سعر/إيراد.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KY = ROOT / "services/sahool-platform/core/engines/ky_registry.py"
MPC = ROOT / "services/sahool-platform/api/lexicographic_irrigation_mpc.py"

# مصطلحات اقتصاديّة ممنوعة في سجلّ Ky (مصدر معاملات فيزيائيّة بحتة).
_ECON_TERMS = ("revenue", "margin", "profit", "price_per", "usd", "yield_value", "income")

_FAILURES: list[str] = []


def _fail(msg: str) -> None:
    _FAILURES.append(msg)


def check_ky_registry() -> None:
    assert KY.is_file(), f"missing: {KY}"
    text = KY.read_text(encoding="utf-8").lower()
    for term in _ECON_TERMS:
        if term in text:
            _fail(f"ky_registry.py must not reference economics: found '{term}'")


def check_mpc_isolation() -> None:
    assert MPC.is_file(), f"missing: {MPC}"
    text = MPC.read_text(encoding="utf-8")
    # economic_margin_delta يجب أن يبقى None في كلّ إسناد (لا اشتقاق).
    for m in re.finditer(r"economic_margin_delta\s*=\s*([^,\n]+)", text):
        val = m.group(1).strip()
        if val != "None":
            _fail(f"economic_margin_delta must stay None (no Ky-derived margin); found '{val}'")
    # لا سطر يضرب مخرَج الغلّة في سعر/إيراد.
    for i, line in enumerate(text.splitlines(), 1):
        low = line.strip().lower()
        if low.startswith("#"):
            continue
        couples_yield = ("relative_yield" in low) or ("yield_loss" in low) or ("j3" in low)
        couples_money = ("price" in low) or ("revenue" in low) or ("margin" in low)
        if couples_yield and couples_money and "*" in low:
            _fail(f"{MPC.name}:{i} couples yield (Ky) with price/margin: {line.strip()}")
    # J4 (تكلفة الماء) يجب أن يُشتَقّ من الماء لا من الغلّة.
    if "j4 = plan.total_irrigation_m3_ha * price" not in text.replace("  ", " "):
        # مرن على المسافات
        if not re.search(r"j4\s*=\s*plan\.total_irrigation_m3_ha\s*\*\s*price", text):
            _fail("J4 water-cost must be derived from water volume × water price, not yield")


def main() -> int:
    check_ky_registry()
    check_mpc_isolation()
    if _FAILURES:
        print("ky_no_economic_coupling_guard FAILED:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("ky_no_economic_coupling_guard_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
