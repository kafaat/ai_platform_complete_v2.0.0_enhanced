"""
services/sahool-platform/api/trueup.py — Yield Calibration Engine

المرجع: المستند ٩ (Prompt Comprehensive) — ميزة TrueUp

المشكلة الزراعيّة:
   حصّاد combine معايرته متطلّقة بعض الشيء. مزارع يقول:
     "النظام قاس إنتاج ٢٠٠٠ كغ، لكنّي وزنتُ المحصول حقيقةً = ٢١٥٠ كغ".
   نحن نحتاج لإعادة معايرة الـyield map كاملة بناءً على هذا الفرق.

الرياضيّات (من المستند ٩):
   k_new = true_up_weight / measured_weight
   Y_adjusted = Y_raw * k_new

ميزات إضافيّة لا توجد في المستند:
   - tracking history للـcalibration (audit)
   - moisture correction (الإنتاج عند ١٤٪ رطوبة معيار للقمح)
   - per-zone calibration (لو الـyield map له zones)
   - emit event "trueup.applied" → reports يُعاد توليدها

محدوديّة v1:
   - لا variable k per zone (نطبّق نفس الـk على كل الـmap)
   - تأتي لاحقاً مع spatial regression
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg


# ─── Crop-specific moisture standards ───────────────────────────
# مرجع: USDA + FAO grain trading standards
# الإنتاج يُنقَل دائماً إلى نسبة الرطوبة المعياريّة قبل التسعير
STANDARD_MOISTURE_PCT = {
    "wheat":   13.5,
    "barley":  13.5,
    "corn":    15.5,
    "sorghum": 14.0,
    "rice":    14.0,
    # الخضراوات تُسعَّر طازجة، لا تطبيق
    "tomato":  None,
    "potato":  None,
    "onion":   None,
}


# ─── Types ──────────────────────────────────────────────────────

class TrueUpStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"   # لو الـk_new خارج النطاق المعقول


@dataclass
class TrueUpInput:
    field_id: str
    operation_id: str           # harvest operation
    actual_weight_kg: float     # الوزن الحقيقي بعد التوزين (للحقل كاملاً أو لعيّنة)
    actual_moisture_pct: float  # رطوبة العيّنة عند التوزين
    measured_weight_kg: float   # ما قاسه الـcombine
    sample_area_ha: Optional[float] = None  # لو القياس لجزء فقط من الحقل
    notes_ar: Optional[str] = None


@dataclass
class TrueUpResult:
    field_id: str
    operation_id: str
    status: TrueUpStatus

    # The k correction factor
    k_old: float                # كان 1.0 لو أوّل معايرة
    k_new: float
    k_change_pct: float

    # Moisture-corrected yields (kg/ha at standard moisture)
    measured_yield_kg_ha: float
    adjusted_yield_kg_ha: float

    # Adjustment metadata
    moisture_correction_applied: bool
    standard_moisture_pct: Optional[float]

    error_pct: float            # |k_new - 1| × 100 — كم كان الـcombine off
    warnings: List[str] = field(default_factory=list)
    rationale_ar: str = ""
    applied_at: str = ""


# ─── Math (pure functions — testable without DB) ────────────────

def moisture_correct(
    weight_kg: float,
    actual_moisture_pct: float,
    standard_moisture_pct: float,
) -> float:
    """
    Adjust grain weight to standard moisture content.

    Formula: W_std = W_actual × (100 − M_actual) / (100 − M_std)

    مثال: ١٠٠٠ كغ قمح برطوبة ١٦٪، المعيار ١٣.٥٪
          W_std = 1000 × (100-16) / (100-13.5) = 1000 × 84/86.5 = 971 كغ
    """
    if actual_moisture_pct >= 100 or standard_moisture_pct >= 100:
        raise ValueError("moisture must be < 100%")
    if actual_moisture_pct < 0 or standard_moisture_pct < 0:
        raise ValueError("moisture must be >= 0%")
    return weight_kg * (100 - actual_moisture_pct) / (100 - standard_moisture_pct)


def calculate_k_new(
    actual_weight_kg: float,
    measured_weight_kg: float,
) -> float:
    """k_new = actual / measured (مع validation)."""
    if measured_weight_kg <= 0:
        raise ValueError("measured_weight_kg must be > 0")
    if actual_weight_kg < 0:
        raise ValueError("actual_weight_kg must be >= 0")
    return actual_weight_kg / measured_weight_kg


def is_k_acceptable(k_new: float) -> bool:
    """
    قواعد القبول:
      - k بين 0.7 و 1.3 (±30% خطأ معقول للـcombine)
      - خارج هذا = خطأ في القياس، نرفض

    لو combine قاس ١٠٠٠ كغ والوزن الحقيقي ٢٠٠٠ كغ، شيء خطأ بالعمليّة
    (ربّما العيّنة من حقل آخر، أو وزن خاطئ).
    """
    return 0.7 <= k_new <= 1.3


# ─── TrueUp engine ──────────────────────────────────────────────

class TrueUpEngine:
    """
    Server-side engine لتطبيق TrueUp.

    Workflow:
       1. validate input
       2. compute k_new + moisture correction
       3. check acceptance bounds
       4. persist (DB writes)
       5. emit event 'trueup.applied' → reports تُعاد توليدها
    """

    def __init__(self, pool: "asyncpg.Pool" = None, event_bus=None):
        """pool + event_bus اختياريّان — التعديل الرياضي يعمل بدونهما."""
        self.pool = pool
        self.event_bus = event_bus

    def compute(
        self,
        input_data: TrueUpInput,
        crop: str,
        measured_yield_kg_ha: float,
        k_old: float = 1.0,
    ) -> TrueUpResult:
        """
        Pure function — يحسب الـTrueUp بدون أيّ DB access.
        قابل للاختبار مستقلّاً.
        """
        warnings: List[str] = []

        # ١. Moisture correction (إن كان المحصول حبوب)
        std_moisture = STANDARD_MOISTURE_PCT.get(crop.lower())
        moisture_applied = False

        if std_moisture is not None:
            try:
                actual_corrected = moisture_correct(
                    input_data.actual_weight_kg,
                    input_data.actual_moisture_pct,
                    std_moisture,
                )
                measured_corrected = moisture_correct(
                    input_data.measured_weight_kg,
                    input_data.actual_moisture_pct,  # نفس الرطوبة لكليهما (لحظة القياس)
                    std_moisture,
                )
                moisture_applied = True
            except ValueError as e:
                warnings.append(f"تعذّر تطبيق تصحيح الرطوبة: {e}")
                actual_corrected = input_data.actual_weight_kg
                measured_corrected = input_data.measured_weight_kg
        else:
            # خضراوات/فاكهة — نستخدم الوزن الطازج مباشرةً
            actual_corrected = input_data.actual_weight_kg
            measured_corrected = input_data.measured_weight_kg

        # ٢. k_new calculation
        try:
            k_new = calculate_k_new(actual_corrected, measured_corrected)
        except ValueError as e:
            return TrueUpResult(
                field_id=input_data.field_id,
                operation_id=input_data.operation_id,
                status=TrueUpStatus.REJECTED,
                k_old=k_old, k_new=0, k_change_pct=0,
                measured_yield_kg_ha=measured_yield_kg_ha,
                adjusted_yield_kg_ha=measured_yield_kg_ha,
                moisture_correction_applied=moisture_applied,
                standard_moisture_pct=std_moisture,
                error_pct=0,
                warnings=[f"قيمة غير صالحة: {e}"],
                rationale_ar="رُفض الـTrueUp بسبب قيم غير صالحة",
                applied_at=_now_iso(),
            )

        # ٣. Acceptance check
        if not is_k_acceptable(k_new):
            return TrueUpResult(
                field_id=input_data.field_id,
                operation_id=input_data.operation_id,
                status=TrueUpStatus.REJECTED,
                k_old=k_old, k_new=k_new,
                k_change_pct=(k_new - 1.0) * 100,
                measured_yield_kg_ha=measured_yield_kg_ha,
                adjusted_yield_kg_ha=measured_yield_kg_ha,
                moisture_correction_applied=moisture_applied,
                standard_moisture_pct=std_moisture,
                error_pct=abs(k_new - 1.0) * 100,
                warnings=[
                    f"k_new={k_new:.3f} خارج النطاق المعقول (0.7-1.3).",
                    "تحقّق من قياس الوزن — قد يكون من حقل آخر أو ميزان خاطئ.",
                ],
                rationale_ar=(
                    f"الفرق بين القياس ({input_data.measured_weight_kg} كغ) "
                    f"والوزن الفعلي ({input_data.actual_weight_kg} كغ) كبير جدّاً. "
                    "رُفض الـTrueUp."
                ),
                applied_at=_now_iso(),
            )

        # ٤. Apply correction
        adjusted_yield = measured_yield_kg_ha * k_new
        error_pct = abs(k_new - 1.0) * 100

        # Build rationale
        rationale_parts = []
        if moisture_applied:
            rationale_parts.append(
                f"تصحيح الرطوبة: من {input_data.actual_moisture_pct}% "
                f"إلى المعيار {std_moisture}%"
            )
        rationale_parts.append(
            f"معامل التصحيح k={k_new:.3f} (الفرق {error_pct:.1f}%)"
        )
        rationale_parts.append(
            f"الإنتاج المُعدَّل: {adjusted_yield:.0f} كغ/هـ "
            f"(كان {measured_yield_kg_ha:.0f})"
        )

        if error_pct > 10:
            warnings.append(
                f"الـcombine كان off بـ{error_pct:.1f}% — يُنصح بمعايرة الجهاز قبل الموسم القادم"
            )

        return TrueUpResult(
            field_id=input_data.field_id,
            operation_id=input_data.operation_id,
            status=TrueUpStatus.APPLIED,
            k_old=k_old,
            k_new=round(k_new, 4),
            k_change_pct=round((k_new - k_old) / k_old * 100, 2) if k_old > 0 else 0,
            measured_yield_kg_ha=round(measured_yield_kg_ha, 1),
            adjusted_yield_kg_ha=round(adjusted_yield, 1),
            moisture_correction_applied=moisture_applied,
            standard_moisture_pct=std_moisture,
            error_pct=round(error_pct, 2),
            warnings=warnings,
            rationale_ar=" · ".join(rationale_parts),
            applied_at=_now_iso(),
        )

    async def apply(
        self,
        input_data: TrueUpInput,
        crop: str,
        measured_yield_kg_ha: float,
        actor_id: str,
        tenant_id: str,
        command_id: Optional[str] = None,
    ) -> TrueUpResult:
        """
        النسخة الكاملة: compute + persist + emit event.
        تحتاج pool + event_bus configured.
        """
        if self.pool is None:
            raise RuntimeError("TrueUpEngine: pool not configured for async apply()")

        # ١. Look up current k (default 1.0)
        import uuid as _uuid
        async with self.pool.acquire() as conn:
            k_old_row = await conn.fetchval(
                """
                SELECT k_factor FROM trueup_calibrations
                WHERE operation_id = $1
                ORDER BY applied_at DESC LIMIT 1
                """,
                _uuid.UUID(input_data.operation_id),
            )
        k_old = float(k_old_row) if k_old_row is not None else 1.0

        # ٢. Compute
        result = self.compute(input_data, crop, measured_yield_kg_ha, k_old)

        if result.status == TrueUpStatus.REJECTED:
            return result

        # ٣. Persist
        async with self.pool.acquire() as conn:
            calib_id = _uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO trueup_calibrations
                    (calibration_id, operation_id, field_id, tenant_id,
                     k_factor, actual_weight_kg, actual_moisture_pct,
                     measured_weight_kg, measured_yield_kg_ha,
                     adjusted_yield_kg_ha, error_pct, applied_by,
                     command_id, notes_ar)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                calib_id,
                _uuid.UUID(input_data.operation_id),
                _uuid.UUID(input_data.field_id),
                _uuid.UUID(tenant_id),
                result.k_new,
                input_data.actual_weight_kg,
                input_data.actual_moisture_pct,
                input_data.measured_weight_kg,
                result.measured_yield_kg_ha,
                result.adjusted_yield_kg_ha,
                result.error_pct,
                actor_id,
                _uuid.UUID(command_id) if command_id else None,
                input_data.notes_ar,
            )

        # ٤. Emit event (لـreports تُعاد توليدها)
        if self.event_bus:
            from .event_bus import EventType, EventSource
            await self.event_bus.emit(
                event_type=EventType.TRUEUP_APPLIED,
                entity_type="field",
                entity_id=input_data.field_id,
                tenant_id=tenant_id,
                payload={
                    "operation_id": input_data.operation_id,
                    "k_old": result.k_old,
                    "k_new": result.k_new,
                    "measured_yield_kg_ha": result.measured_yield_kg_ha,
                    "adjusted_yield_kg_ha": result.adjusted_yield_kg_ha,
                    "error_pct": result.error_pct,
                    "moisture_corrected": result.moisture_correction_applied,
                },
                source=EventSource.SYSTEM,
                actor_id=actor_id,
                command_id=command_id,
            )

        return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
