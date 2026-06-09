"""
core/farm_ledger.py — دفتر حسابات بسيط للمزرعة
================================================

السياق المُحقَّق من البحث:
  • World Bank: smallholders بدون records → لا يحصلون على تمويل
  • Frontiers Sustainable Food Systems (2026): record-keeping يزيد
    productivity, resilience, sustainability — لكنّ مهمَل في الـMENA
  • Economy of Yemen: GDP per capita = $401، 48.6% poverty line
    → كل قرار اقتصادي حاسم للمزارع اليمني

الميزة المعماريّة:
  • لا يستهدف accountants — يستهدف المزارع الأمّي
  • مدخلات بسيطة: نوع + قيمة + تاريخ
  • مخرجات قابلة للفهم: "خسرت X في الموسم"، "ربحك ٢٠٪ من العام الماضي"
  • integrate مع farm_memory: يربط الحسابات بالأنشطة

المبادئ المُراعاة:
  ✓ offline-first (يخزّن محلّياً، يُزامن لاحقاً)
  ✓ لا simulation، لا prediction — مجرّد دفتر شفّاف
  ✓ نواة محايدة جغرافيّاً (currency محدّد كـparameter)
  ✓ يتكامل مع farm_memory الموجودة (لا duplication)

ما ليس هنا:
  ✗ market price forecasting (يحتاج بيانات أسواق فعليّة)
  ✗ loan/credit scoring (خارج النطاق — bank's job)
  ✗ tax calculation (yemen-specific tax code خارج عن سهول)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from enum import Enum


class LedgerKind(str, Enum):
    """نوع القيد المحاسبي."""

    # مصروفات (expenses)
    SEED = "seed"  # بذور
    FERTILIZER = "fertilizer"  # أسمدة
    PESTICIDE = "pesticide"  # مبيدات
    LABOR = "labor"  # عمالة
    FUEL = "fuel"  # وقود (مضخّات/جرارات)
    WATER = "water"  # ريّ
    EQUIPMENT = "equipment"  # معدّات
    TRANSPORT = "transport"  # نقل للسوق
    OTHER_EXPENSE = "other_expense"
    # إيرادات (income)
    HARVEST_SALE = "harvest_sale"  # بيع المحصول
    SUBSIDY = "subsidy"  # دعم حكومي/منظّمات
    OTHER_INCOME = "other_income"


EXPENSE_KINDS = {
    LedgerKind.SEED,
    LedgerKind.FERTILIZER,
    LedgerKind.PESTICIDE,
    LedgerKind.LABOR,
    LedgerKind.FUEL,
    LedgerKind.WATER,
    LedgerKind.EQUIPMENT,
    LedgerKind.TRANSPORT,
    LedgerKind.OTHER_EXPENSE,
}

INCOME_KINDS = {
    LedgerKind.HARVEST_SALE,
    LedgerKind.SUBSIDY,
    LedgerKind.OTHER_INCOME,
}

KIND_NAMES_AR = {
    LedgerKind.SEED: "بذور",
    LedgerKind.FERTILIZER: "أسمدة",
    LedgerKind.PESTICIDE: "مبيدات",
    LedgerKind.LABOR: "عمالة",
    LedgerKind.FUEL: "وقود",
    LedgerKind.WATER: "ري",
    LedgerKind.EQUIPMENT: "معدّات",
    LedgerKind.TRANSPORT: "نقل",
    LedgerKind.OTHER_EXPENSE: "مصروف آخر",
    LedgerKind.HARVEST_SALE: "بيع المحصول",
    LedgerKind.SUBSIDY: "دعم/منحة",
    LedgerKind.OTHER_INCOME: "دخل آخر",
}


@dataclass(frozen=True)
class LedgerEntry:
    """قيد محاسبي واحد. immutable لـauditability."""

    entry_id: str
    tenant_id: str
    farm_id: str
    field_id: str | None  # قد يكون farm-level (وقود مشترك)
    season_id: str | None  # ٢٠٢٥-قمح-صعدة
    kind: LedgerKind
    amount: float  # موجب دائماً، الـsign من kind
    currency: str = "YER"  # Yemeni Rial default
    quantity: float | None = None  # اختياري (مثلاً 50 كغ بذور)
    unit: str | None = None
    description_ar: str = ""
    entry_date: date_type = field(default_factory=date_type.today)
    invoice_ref: str | None = None  # رقم فاتورة لو موجود


@dataclass(frozen=True)
class SeasonSummary:
    """ملخّص موسم لـحقل/مزرعة."""

    tenant_id: str
    farm_id: str
    field_id: str | None
    season_id: str
    currency: str

    total_expenses: float
    total_income: float
    net_profit: float  # موجب = ربح، سالب = خسارة
    expense_breakdown: dict[str, float]  # kind → sum
    income_breakdown: dict[str, float]
    entry_count: int


# ─── منطق ─────────────────────────────────────────────────────────


def summarize_season(
    entries: list[LedgerEntry],
    tenant_id: str,
    farm_id: str,
    season_id: str,
    field_id: str | None = None,
) -> SeasonSummary:
    """يحسب ملخّص اقتصادي للموسم.

    Args:
        entries: قائمة القيود المسجَّلة
        field_id: إن أردنا حقل واحد فقط (None = كل الحقول)
    """
    filtered = [
        e
        for e in entries
        if e.tenant_id == tenant_id
        and e.farm_id == farm_id
        and e.season_id == season_id
        and (field_id is None or e.field_id == field_id)
    ]

    # تحقّق من تطابق العملة
    currencies = {e.currency for e in filtered}
    if len(currencies) > 1:
        raise ValueError(
            f"عملات متعدّدة في نفس الموسم {season_id}: {currencies}. "
            f"يجب توحيد العملة أو تحويل القيود يدوياً."
        )
    currency = currencies.pop() if currencies else "YER"

    expense_breakdown: dict[str, float] = {}
    income_breakdown: dict[str, float] = {}
    total_expenses = 0.0
    total_income = 0.0

    for e in filtered:
        if e.kind in EXPENSE_KINDS:
            expense_breakdown[e.kind.value] = expense_breakdown.get(e.kind.value, 0.0) + e.amount
            total_expenses += e.amount
        elif e.kind in INCOME_KINDS:
            income_breakdown[e.kind.value] = income_breakdown.get(e.kind.value, 0.0) + e.amount
            total_income += e.amount

    net_profit = total_income - total_expenses

    return SeasonSummary(
        tenant_id=tenant_id,
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        currency=currency,
        total_expenses=total_expenses,
        total_income=total_income,
        net_profit=net_profit,
        expense_breakdown=expense_breakdown,
        income_breakdown=income_breakdown,
        entry_count=len(filtered),
    )


def cost_per_hectare(
    summary: SeasonSummary,
    area_ha: float,
) -> dict[str, float]:
    """يحسب التكلفة/الإيراد لكل هكتار.

    Args:
        area_ha: مساحة الحقل/المزرعة بالهكتار
    """
    if area_ha <= 0:
        raise ValueError(f"area_ha يجب > 0، وُجِد {area_ha}")
    return {
        "expense_per_ha": summary.total_expenses / area_ha,
        "income_per_ha": summary.total_income / area_ha,
        "profit_per_ha": summary.net_profit / area_ha,
    }


def break_even_yield(
    summary: SeasonSummary,
    area_ha: float,
    market_price_per_kg: float,
) -> float:
    """يحسب أدنى إنتاج لتغطية التكاليف (break-even yield بـكغ/هكتار).

    مفيد لمعرفة: "كم يجب أن أحصد لأغطّي ما صرفته؟"

    Args:
        market_price_per_kg: السعر المتوقّع للمحصول

    Returns:
        kg/ha — break-even yield
    """
    if area_ha <= 0 or market_price_per_kg <= 0:
        raise ValueError("area_ha و market_price_per_kg يجب > 0")
    return summary.total_expenses / (area_ha * market_price_per_kg)


def compare_seasons(
    summaries: list[SeasonSummary],
) -> dict[str, dict[str, float]]:
    """يقارن ٢+ مواسم — تحليل تطوّر المزرعة عبر السنوات.

    Returns:
        dict {season_id: metrics}
    """
    out: dict[str, dict[str, float]] = {}
    for s in summaries:
        out[s.season_id] = {
            "total_expenses": s.total_expenses,
            "total_income": s.total_income,
            "net_profit": s.net_profit,
            "profit_margin_pct": (
                (s.net_profit / s.total_income * 100) if s.total_income > 0 else 0.0
            ),
        }
    return out


# ─── Helpers لتقديم النتائج للمزارع ─────────────────────────────────


def format_summary_ar(summary: SeasonSummary) -> str:
    """يولّد نصّ عربي مفهوم للمزارع."""
    status = "ربح" if summary.net_profit > 0 else "خسارة"
    sign = "+" if summary.net_profit > 0 else ""
    return (
        f"موسم {summary.season_id}:\n"
        f"  المصروفات: {summary.total_expenses:,.0f} {summary.currency}\n"
        f"  الإيرادات: {summary.total_income:,.0f} {summary.currency}\n"
        f"  الصافي:   {sign}{summary.net_profit:,.0f} {summary.currency} ({status})\n"
        f"  عدد القيود: {summary.entry_count}"
    )


def top_expense_categories(
    summary: SeasonSummary,
    top_n: int = 3,
) -> list[tuple[str, float, float]]:
    """يُرجع أعلى ٣ فئات مصروفات.

    Returns:
        list of (category_ar, amount, pct_of_total)
    """
    if summary.total_expenses == 0:
        return []
    sorted_items = sorted(
        summary.expense_breakdown.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:top_n]
    return [
        (
            KIND_NAMES_AR.get(LedgerKind(k), k),
            v,
            (v / summary.total_expenses) * 100,
        )
        for k, v in sorted_items
    ]
