"""tests/test_farm_ledger.py — تستثبت farm_ledger المنطق المحاسبي."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

from core.farm_ledger import (
    EXPENSE_KINDS,
    INCOME_KINDS,
    LedgerEntry,
    LedgerKind,
    break_even_yield,
    compare_seasons,
    cost_per_hectare,
    format_summary_ar,
    summarize_season,
    top_expense_categories,
)


class TestFarmLedger:
    def _sample_entries(self):
        """قيود نموذجيّة لموسم قمح في حقل واحد."""
        return [
            # مصروفات
            LedgerEntry(
                "e1",
                "T1",
                "F1",
                "FLD1",
                "2025-W",
                LedgerKind.SEED,
                50000,
                "YER",
                quantity=100,
                unit="kg",
                description_ar="بذور قمح Sids 14",
            ),
            LedgerEntry(
                "e2",
                "T1",
                "F1",
                "FLD1",
                "2025-W",
                LedgerKind.FERTILIZER,
                80000,
                "YER",
                description_ar="DAP + Urea",
            ),
            LedgerEntry(
                "e3",
                "T1",
                "F1",
                "FLD1",
                "2025-W",
                LedgerKind.LABOR,
                120000,
                "YER",
                description_ar="أجور موسم",
            ),
            LedgerEntry(
                "e4",
                "T1",
                "F1",
                "FLD1",
                "2025-W",
                LedgerKind.FUEL,
                40000,
                "YER",
                description_ar="ديزل مضخّة",
            ),
            LedgerEntry("e5", "T1", "F1", "FLD1", "2025-W", LedgerKind.WATER, 30000, "YER"),
            # إيراد
            LedgerEntry(
                "e6",
                "T1",
                "F1",
                "FLD1",
                "2025-W",
                LedgerKind.HARVEST_SALE,
                450000,
                "YER",
                quantity=2000,
                unit="kg",
                description_ar="بيع ٢ طن قمح",
            ),
        ]

    def test_summarize_basic(self):
        """يجمع المصروفات والإيرادات الصحيحة."""
        entries = self._sample_entries()
        summary = summarize_season(
            entries,
            "T1",
            "F1",
            "2025-W",
            field_id="FLD1",
        )
        assert summary.total_expenses == 50000 + 80000 + 120000 + 40000 + 30000
        assert summary.total_income == 450000
        assert summary.net_profit == 450000 - 320000  # = 130000
        assert summary.entry_count == 6

    def test_breakdown_by_kind(self):
        """التصنيف بـkind صحيح."""
        entries = self._sample_entries()
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        assert summary.expense_breakdown[LedgerKind.LABOR.value] == 120000
        assert summary.expense_breakdown[LedgerKind.FERTILIZER.value] == 80000
        assert LedgerKind.SEED.value in summary.expense_breakdown

    def test_top_categories(self):
        """top_expense_categories تُرجع الأعلى."""
        entries = self._sample_entries()
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        top3 = top_expense_categories(summary, top_n=3)
        assert len(top3) == 3
        # العمالة الأعلى (120000)
        assert top3[0][0] == "عمالة"
        assert top3[0][1] == 120000

    def test_cost_per_hectare(self):
        """التكلفة لكل هكتار."""
        entries = self._sample_entries()
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        # نفترض الحقل ٢ هكتار
        per_ha = cost_per_hectare(summary, area_ha=2.0)
        assert per_ha["expense_per_ha"] == 160000  # 320000 / 2
        assert per_ha["profit_per_ha"] == 65000  # 130000 / 2

    def test_break_even(self):
        """break-even yield calculation."""
        entries = self._sample_entries()
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        # سعر السوق 225 YER/kg
        be = break_even_yield(summary, area_ha=2.0, market_price_per_kg=225.0)
        # 320000 / (2 * 225) = ~711 kg/ha
        assert 700 < be < 720

    def test_multi_currency_error(self):
        """يرفض القيود بعملات مختلفة في موسم واحد."""
        entries = self._sample_entries()
        entries.append(
            LedgerEntry("e7", "T1", "F1", "FLD1", "2025-W", LedgerKind.OTHER_EXPENSE, 100, "USD")
        )
        try:
            summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
            raise AssertionError("يجب أن يفشل عند currencies مختلفة")
        except ValueError as e:
            assert "عملات متعدّدة" in str(e)

    def test_format_arabic(self):
        """النصّ العربي مفهوم وكامل."""
        entries = self._sample_entries()
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        text = format_summary_ar(summary)
        assert "ربح" in text
        assert "2025-W" in text
        assert "YER" in text

    def test_compare_seasons(self):
        """مقارنة مواسم متعدّدة."""
        e1 = self._sample_entries()
        # موسم سابق بـربح أقلّ
        e2 = [
            LedgerEntry("p1", "T1", "F1", "FLD1", "2024-W", LedgerKind.FERTILIZER, 60000, "YER"),
            LedgerEntry("p2", "T1", "F1", "FLD1", "2024-W", LedgerKind.HARVEST_SALE, 100000, "YER"),
        ]
        s1 = summarize_season(e1, "T1", "F1", "2025-W", "FLD1")
        s2 = summarize_season(e2, "T1", "F1", "2024-W", "FLD1")
        comparison = compare_seasons([s1, s2])
        assert "2025-W" in comparison
        assert "2024-W" in comparison
        assert comparison["2025-W"]["net_profit"] > comparison["2024-W"]["net_profit"]

    def test_field_id_filter(self):
        """field_id يفرز الصحيح."""
        entries = self._sample_entries()
        # إضافة قيد لـحقل آخر
        entries.append(
            LedgerEntry("other", "T1", "F1", "FLD2", "2025-W", LedgerKind.SEED, 999999, "YER")
        )
        # فلترة لـFLD1 فقط — يجب أن لا يحتسب القيد المُضاف
        summary = summarize_season(entries, "T1", "F1", "2025-W", "FLD1")
        assert summary.total_expenses == 320000  # نفس النتيجة السابقة
        # بدون فلترة — يحتسبه
        summary2 = summarize_season(entries, "T1", "F1", "2025-W", field_id=None)
        assert summary2.total_expenses == 320000 + 999999
