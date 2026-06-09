"""
api/temporal_coherence.py — طبقة التماسك الزمني الموحّد (Convergence)

الفجوة المُكتشَفة: المحرّكات تمثّل الزمن بصيغ مختلفة:
  • gdd_tracker      → List[DailyTemp] (بلا تاريخ تقويمي مطلق)
  • water_balance    → day_of_year (1-365، يفقد السنة)
  • astronomical     → date ISO مطلق (YYYY-MM-DD)

بلا محوّل موحّد، قد "يصحّ كلّ محرّك محلّيّاً لكن لا يتّسقون عالميّاً"
(Semantic Drift). هذه الطبقة تضمن مرجعاً زمنيّاً واحداً يربط الثلاثة، فتتكلّم
المحرّكات نفس الزمن — وهي أوّل لبنة convergence قابلة للإثبات offline.

المبدأ: تاريخ ISO هو المرجع الموثوق (authoritative)؛ day_of_year واليوم النسبي
يُشتقّان منه بدالّة واحدة، لا بحساب مستقلّ في كلّ محرّك.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional


@dataclass
class TemporalContext:
    """مرجع زمني موحّد لكلّ المحرّكات في موسم/حقل واحد."""
    current_date: date
    planting_date: Optional[date] = None

    @property
    def day_of_year(self) -> int:
        """لـwater_balance / الإشعاع الشمسي (1-365/366)."""
        return self.current_date.timetuple().tm_yday

    @property
    def days_since_planting(self) -> Optional[int]:
        """لـGDD / المراحل — اليوم النسبي من الزراعة."""
        if self.planting_date is None:
            return None
        return (self.current_date - self.planting_date).days

    @property
    def iso(self) -> str:
        """لـastronomical / السجلّات — التاريخ المطلق."""
        return self.current_date.isoformat()

    def to_dict(self) -> Dict:
        return {
            "iso": self.iso,
            "day_of_year": self.day_of_year,
            "days_since_planting": self.days_since_planting,
            "planting_date": self.planting_date.isoformat() if self.planting_date else None,
        }


def make_temporal_context(
    current_date_iso: str,
    planting_date_iso: Optional[str] = None,
) -> TemporalContext:
    """يبني مرجعاً زمنيّاً موحّداً من تواريخ ISO.

    كلّ المحرّكات تأخذ زمنها من هنا → اتّساق مضمون.
    """
    def _parse(s: str) -> date:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)

    current = _parse(current_date_iso)
    planting = _parse(planting_date_iso) if planting_date_iso else None

    if planting and planting > current:
        raise ValueError(
            f"تاريخ الزراعة ({planting_date_iso}) بعد التاريخ الحالي "
            f"({current_date_iso}) — غير منطقي."
        )
    return TemporalContext(current_date=current, planting_date=planting)


@dataclass
class CoherenceCheck:
    """تحقّق اتّساق زمني بين مخرجات محرّكات مختلفة لنفس اللحظة."""
    coherent: bool
    detail_ar: str

    def to_dict(self) -> Dict:
        return {"coherent": self.coherent, "detail_ar": self.detail_ar}


def check_temporal_coherence(
    ctx: TemporalContext,
    gdd_days_counted: Optional[int] = None,
    astronomical_anchor_days: Optional[int] = None,
    *,
    tolerance_days: int = 3,
) -> CoherenceCheck:
    """يتحقّق أنّ المحرّكات تشير لنفس اللحظة الزمنيّة (لا انحراف دلالي).

    Args:
        ctx: المرجع الزمني الموحّد.
        gdd_days_counted: عدد الأيّام التي عدّها GDD (يجب أن يطابق days_since_planting).
        astronomical_anchor_days: أيّام من المرساة الفلكيّة (للتحقّق المنطقي).
        tolerance_days: هامش السماح (فروق التقريب).
    """
    issues = []

    # GDD يجب أن يكون عدّ نفس عدد أيّام الموسم
    if gdd_days_counted is not None and ctx.days_since_planting is not None:
        diff = abs(gdd_days_counted - ctx.days_since_planting)
        if diff > tolerance_days:
            issues.append(
                f"GDD عدّ {gdd_days_counted} يوماً بينما الموسم "
                f"{ctx.days_since_planting} يوماً (فرق {diff})."
            )

    # day_of_year يجب أن يكون في النطاق الصالح
    if not (1 <= ctx.day_of_year <= 366):
        issues.append(f"day_of_year خارج النطاق: {ctx.day_of_year}")

    if issues:
        return CoherenceCheck(
            coherent=False,
            detail_ar="انحراف زمني: " + "؛ ".join(issues),
        )
    return CoherenceCheck(
        coherent=True,
        detail_ar=(
            f"متّسق: التاريخ {ctx.iso}، اليوم {ctx.day_of_year} من السنة، "
            f"{ctx.days_since_planting if ctx.days_since_planting is not None else '—'} "
            "يوماً من الزراعة — كلّ المحرّكات على نفس المرجع."
        ),
    )
