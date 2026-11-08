"""api/harvest_models.py — نماذج ومساعدات تتبّع سلسلة الإمداد (farm-to-market) — v65.

مُستخرَجة من main.py ضمن تفكيك الوحدة الضخمة (B1): نماذج Pydantic + مُطبِّعات الصفوف
(DB→نموذج) + أعمدة SELECT لدفعات الحصاد وسلسلة الحيازة. يستهلكها
routers/harvest_traceability مباشرةً (لا عبر main.py)، فيُقلّل اقتران الراوتر بالوحدة
المركزيّة. منطق نماذج صرف — لا I/O ولا تبعيّة على main.py.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator

# حدود event_details (JSONB حرّ): الحجم مُسلسَلاً (UTF-8) والعمق — يمنعان حمولةً بلا سقف
# تُخزَّن وتُبصَم وتُعاد في كلّ قراءة أثر.
EVENT_DETAILS_MAX_BYTES = 8 * 1024
EVENT_DETAILS_MAX_DEPTH = 4
# أقصى ما تحمله NUMERIC(12,2).
_MAX_KG = 9_999_999_999.99


def _json_depth(value, level: int = 1) -> int:
    """عمق التداخل: dict/list في القمّة = 1، وكلّ حاوية متداخلة +1."""
    if not isinstance(value, (dict, list)):
        return level - 1
    children = value.values() if isinstance(value, dict) else value
    return max([level, *(_json_depth(c, level + 1) for c in children)])


def validate_event_details(details: dict) -> dict:
    """يرفض event_details فوق 8 KB مُسلسَلةً أو أعمق من 4 أو بقيم NaN/Infinity (ليست JSON
    صالحاً لـJSONB)."""
    try:
        raw = json.dumps(details, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as e:
        raise ValueError("event_details: قيمة غير قابلة للتمثيل JSON") from e
    if len(raw.encode("utf-8")) > EVENT_DETAILS_MAX_BYTES:
        raise ValueError(f"event_details أكبر من {EVENT_DETAILS_MAX_BYTES} بايت مُسلسَلةً")
    if _json_depth(details) > EVENT_DETAILS_MAX_DEPTH:
        raise ValueError(f"event_details أعمق من {EVENT_DETAILS_MAX_DEPTH} مستويات")
    return details


class HarvestLotCreateRequest(BaseModel):
    """طلب إنشاء دفعة حصاد — تُربط بحقل (إلزاميّ) وموسم (اختياريّ)."""

    field_id: str = Field(max_length=50)
    season_id: str | None = Field(default=None, max_length=50)
    crop: str | None = Field(default=None, max_length=50)
    harvest_date: str  # ISO date (يُتحقَّق في المسار)
    quantity_kg: float = Field(ge=0)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    quality_grade: str | None = Field(default=None, pattern="^(A|B|C|reject)$")
    notes_ar: str | None = Field(default=None, max_length=2000)


class HarvestLotSummary(BaseModel):
    harvest_lot_id: str
    field_id: str
    season_id: str | None = None
    crop: str | None = None
    harvest_date: str | None = None
    quantity_kg: float | None = None
    moisture_pct: float | None = None
    quality_grade: str | None = None
    notes_ar: str | None = None
    status: str
    created_at: str | None = None


class CustodyEventCreateRequest(BaseModel):
    """طلب تسجيل حدث حيازة على دفعة (append-only) — يُحرّك حالة الدفعة تطبيقيّاً."""

    event_type: str = Field(pattern="^(harvest|storage|quality_check|transport|sales)$")
    handler: str | None = Field(default=None, max_length=120)
    handler_role: str | None = Field(
        default=None, pattern="^(farmer|storage|transporter|trader|buyer|inspector|system)$"
    )
    location_name: str | None = Field(default=None, max_length=120)
    quantity_kg: float | None = Field(default=None, ge=0, le=_MAX_KG, allow_inf_nan=False)
    event_details: dict = Field(default_factory=dict)
    occurred_at: str = Field(max_length=64)  # ISO datetime (يُتحقَّق في المسار)

    @field_validator("event_details")
    @classmethod
    def _bounded_details(cls, v: dict) -> dict:
        return validate_event_details(v)


class CustodyEventSummary(BaseModel):
    custody_event_id: int
    harvest_lot_id: str
    event_type: str
    handler: str | None = None
    handler_role: str | None = None
    location_name: str | None = None
    quantity_kg: float | None = None
    event_details: dict = Field(default_factory=dict)
    occurred_at: str | None = None
    recorded_at: str | None = None
    content_hash: str | None = None


def _row_to_harvest_lot(r) -> HarvestLotSummary:
    """صفّ DB → HarvestLotSummary. NUMERIC(Decimal)→float، DATE/TIMESTAMPTZ→ISO نصّ."""

    def _f(key):
        v = r[key]
        return float(v) if v is not None else None

    return HarvestLotSummary(
        harvest_lot_id=r["harvest_lot_id"],
        field_id=r["field_id"],
        season_id=r["season_id"],
        crop=r["crop"],
        harvest_date=r["harvest_date"].isoformat() if r["harvest_date"] else None,
        quantity_kg=_f("quantity_kg"),
        moisture_pct=_f("moisture_pct"),
        quality_grade=r["quality_grade"],
        notes_ar=r["notes_ar"],
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
    )


def _row_to_custody_event(r) -> CustodyEventSummary:
    """صفّ DB → CustodyEventSummary. event_details (JSONB) قد يأتي نصّاً من asyncpg."""
    import json as _json

    details = r["event_details"]
    if isinstance(details, str):
        try:
            details = _json.loads(details)
        except (ValueError, TypeError):
            details = {}
    qty = r["quantity_kg"]
    return CustodyEventSummary(
        custody_event_id=int(r["custody_event_id"]),
        harvest_lot_id=r["harvest_lot_id"],
        event_type=r["event_type"],
        handler=r["handler"],
        handler_role=r["handler_role"],
        location_name=r["location_name"],
        quantity_kg=float(qty) if qty is not None else None,
        event_details=details or {},
        occurred_at=r["occurred_at"].isoformat() if r["occurred_at"] else None,
        recorded_at=r["recorded_at"].isoformat() if r["recorded_at"] else None,
        content_hash=r["content_hash"],
    )


_HARVEST_LOT_SELECT = (
    "harvest_lot_id, field_id, season_id, crop, harvest_date, quantity_kg, "
    "moisture_pct, quality_grade, notes_ar, status, created_at"
)
_CUSTODY_EVENT_SELECT = (
    "custody_event_id, harvest_lot_id, event_type, handler, handler_role, "
    "location_name, quantity_kg, event_details, occurred_at, recorded_at, content_hash"
)
