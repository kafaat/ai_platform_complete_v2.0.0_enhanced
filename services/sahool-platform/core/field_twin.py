"""core/field_twin.py — التوأم الرقميّ للحقل: لقطة حالة موحّدة مُجمَّعة (نقيّ، الشريحة 6).

المرحلة B. حالة الحقل اليوم موزَّعة عبر جداول: المؤشّرات (indicators)، قرارات الموزِّع
المفتوحة (dispatch_decisions)، آخر تنفيذ (execution_ledger)، بيانات الحقل (fields). لا
**لقطة واحدة** تجيب «ما حال هذا الحقل الآن، وهل يحتاج انتباهاً، ولماذا؟». التوأم الرقميّ
يجمعها في `FieldTwin`: المؤشّرات الأحدث + القرارات المفتوحة + آخر نتيجة + **حالة مشتقّة**
(سليم / يحتاج انتباهاً / محجوب / بيانات قديمة) مع أسباب صريحة — يربط مخرجات حلقة المرحلة A
ببيانات الحقل في عرض واحد قابل للقياس.

نقيّ وحتميّ (لا I/O): يأخذ مدخلات مُجمَّعة مسبقاً (المُنادي يقرؤها من الجداول معزولةً
بـRLS)، يُرجِع لقطة. الحالة المشتقّة محافِظة وصريحة: أيّ قرار محجوب ⇒ blocked؛ غياب/قِدَم
البيانات ⇒ stale؛ غطاء ضعيف أو قرار مفتوح فاعل ⇒ needs_attention؛ وإلّا healthy. لا تلفيق.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

# عتبات مشتقّة (صريحة، قابلة للمراجعة) — تطابق منطق الواجهة (ndviStatus).
_NDVI_ATTENTION = 0.30  # غطاء أقلّ ⇒ يحتاج انتباهاً (poor)
_FRESHNESS_DAYS_DEFAULT = 7  # بيانات أقدم ⇒ stale (لا قرار على القديم)

# حالات القرار المفتوحة «الفاعلة» (قيد التنفيذ — تستدعي انتباهاً حتى تُغلَق).
_ACTIVE_DECISION_STATES = {"queued", "dispatched"}


@dataclass
class FieldTwin:  # DERIVED_VIEW: projection-only; CanonicalFieldState remains authoritative in production runtime
    """لقطة حالة الحقل الموحّدة + الحالة المشتقّة وأسبابها (شفّافة)."""

    field_id: str
    crop: str | None
    state: str  # healthy | needs_attention | blocked | stale
    ndvi: float | None = None
    indices: dict = field(default_factory=dict)
    growth_stage: str | None = None
    open_decisions: int = 0
    blocked_decisions: int = 0
    last_execution: dict | None = None
    data_age_days: int | None = None
    attention_reasons_ar: list[str] = field(default_factory=list)
    observed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_day(value: Any) -> date | None:
    """يحاول استخراج تاريخ من نصّ ISO/تاريخ — يُرجِع None إن تعذّر (لا يرفع)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        # Aware times are compared in UTC (as asyncpg returns timestamptz), so a +03:00 offset
        # cannot make an observation a day younger than it is.
        return (value.astimezone(UTC) if value.tzinfo is not None else value).date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def assemble_twin(
    field_id: str,
    *,
    crop: str | None = None,
    latest_indices: dict | None = None,
    observed_at: Any = None,
    index_observed_at: dict[str, Any] | None = None,
    now: Any = None,
    open_decisions: list[dict] | None = None,
    last_execution: dict | None = None,
    growth_stage: str | None = None,
    freshness_days: int = _FRESHNESS_DAYS_DEFAULT,
) -> FieldTwin:
    """يجمع حالة الحقل في توأم رقميّ بحالة مشتقّة صريحة (نقيّ) — انظر docstring الوحدة.

    `latest_indices`: {ndvi, evi, …}. `open_decisions`: صفوف dispatch_decisions المفتوحة
    (state/exec_status). `observed_at`/`now`: لحساب قِدَم البيانات. fail-safe: مدخلات
    ناقصة ⇒ حالة محافِظة (stale عند غياب البيانات) لا انهيار.
    """
    indices = dict(latest_indices or {})
    ndvi = indices.get("ndvi")
    if ndvi is not None:
        try:
            ndvi = float(ndvi) if math.isfinite(float(ndvi)) else None
        except (TypeError, ValueError, OverflowError):
            ndvi = None  # a non-numeric or non-finite NDVI is no evidence of cover
    decisions = list(open_decisions or [])
    blocked = [d for d in decisions if (d.get("state") or "").lower() == "blocked"]
    active = [
        d for d in decisions if (d.get("exec_status") or "").lower() in _ACTIVE_DECISION_STATES
    ]

    # The vegetation judgement is led by NDVI. A newer EVI/NDMI must not
    # disguise an old or undated NDVI measurement. Legacy callers without
    # per-indicator dates continue using observed_at, but absence is never fresh.
    observed = (
        index_observed_at.get("ndvi")
        if ndvi is not None and index_observed_at is not None
        else observed_at
    )
    obs_day = _parse_day(observed)
    now_day = _parse_day(now) or datetime.now(UTC).date()
    data_age_days = (now_day - obs_day).days if obs_day is not None else None

    reasons: list[str] = []
    # ترتيب الأسبقيّة: محجوب ← قديم ← يحتاج انتباهاً ← سليم (محافِظ وصريح).
    if blocked:
        state = "blocked"
        reasons.append(f"{len(blocked)} قرار محجوب (خطّ أحمر) ينتظر معالجة.")
    elif (
        not indices
        or ndvi is None
        or data_age_days is None
        or data_age_days < 0
        or data_age_days > freshness_days
    ):
        state = "stale"
        if not indices:
            reasons.append("لا مؤشّرات حديثة — لا يُتَّخذ قرار على بيانات غائبة.")
        elif ndvi is None:
            reasons.append("NDVI غير متوفّر — لا يمكن إثبات سلامة الغطاء النباتي.")
        elif data_age_days is None:
            reasons.append("تاريخ رصد NDVI غير متوفّر — لا يُعتبر القياس حديثاً.")
        elif data_age_days < 0:
            reasons.append("تاريخ رصد NDVI في المستقبل — لا يُقبل كدليل حاضر.")
        else:
            reasons.append(f"البيانات أقدم من {freshness_days} أيّام ({data_age_days} يوماً).")
    elif (ndvi is not None and float(ndvi) < _NDVI_ATTENTION) or active:
        state = "needs_attention"
        if ndvi is not None and float(ndvi) < _NDVI_ATTENTION:
            reasons.append(f"غطاء نباتيّ ضعيف (NDVI={float(ndvi):.2f}).")
        if active:
            reasons.append(f"{len(active)} قرار مفتوح قيد التنفيذ.")
    else:
        state = "healthy"

    return FieldTwin(  # DERIVED_VIEW
        field_id=field_id,
        crop=crop,
        state=state,
        ndvi=(float(ndvi) if ndvi is not None else None),
        indices=indices,
        growth_stage=growth_stage,
        open_decisions=len(decisions),
        blocked_decisions=len(blocked),
        last_execution=last_execution,
        data_age_days=data_age_days,
        attention_reasons_ar=reasons,
        observed_at=(obs_day.isoformat() if obs_day else None),
    )


# ── row adapters (pure): the routers read rows under RLS and hand them here ──


def finite_indicator_readings(rows) -> tuple[dict[str, float], dict[str, Any]]:
    """Latest value and its own observation time per indicator; non-numeric/non-finite skipped.

    Each indicator keeps its own time, so a fresh EVI cannot lend its date to an old NDVI.
    """
    indices: dict[str, float] = {}
    observed: dict[str, Any] = {}
    for r in rows:
        try:
            value = float(r["value"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        indices[r["indicator_id"]] = value
        observed[r["indicator_id"]] = r["recorded_at"]
    return indices, observed


def season_crop_list(raw: Any) -> list[str]:
    """seasons.crops (JSONB: list, or its JSON text from asyncpg) → list of crop names."""
    import json

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw if str(c).strip()]


def active_season_context(season_row) -> dict[str, Any]:
    """The active season as the twin reports it; the season owns crop identity, not fields.crop."""
    if season_row is None:
        return {
            "source": "seasons",
            "status": "missing_active_season",
            "season_id": None,
            "crops": [],
            "cultivar": None,
            "sowing_date": None,
        }
    sowing = season_row["sowing_date"]
    return {
        "source": "seasons",
        "status": "active",
        "season_id": str(season_row["season_id"]),
        "crops": season_crop_list(season_row["crops"]),
        "cultivar": season_row["cultivar"],
        "sowing_date": sowing.isoformat() if sowing is not None else None,
    }


def water_twin_crop_context(active_season, field_row) -> dict[str, Any]:
    """Which crop and planting date interpret a water-twin scenario, and from where.

    An active season wins over legacy fields.crop. A mixed or empty crop list in the active
    season maps to no single root policy, so no crop is inferred (an explicit TAW still works);
    the legacy field crop is not used as a fallback in that case.
    """
    if active_season is not None:
        crops = season_crop_list(active_season["crops"])
        if len(crops) == 1:
            return {
                "crop": crops[0],
                "planting_date": active_season["sowing_date"],
                "season_id": str(active_season["season_id"]),
                "source": "seasons.active",
                "limitations": [],
            }
        return {
            "crop": None,
            "planting_date": None,
            "season_id": str(active_season["season_id"]),
            "source": "seasons.active",
            "limitations": ["active_season_crop_ambiguous"],
        }
    if field_row is not None:
        return {
            "crop": field_row["crop"],
            "planting_date": field_row["planting_date"],
            "season_id": None,
            "source": "fields_legacy_unverified",
            "limitations": ["no_active_season"],
        }
    return {
        "crop": None,
        "planting_date": None,
        "season_id": None,
        "source": "not_loaded",
        "limitations": [],
    }
