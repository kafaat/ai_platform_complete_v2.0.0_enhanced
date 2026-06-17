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

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

# عتبات مشتقّة (صريحة، قابلة للمراجعة) — تطابق منطق الواجهة (ndviStatus).
_NDVI_ATTENTION = 0.30  # غطاء أقلّ ⇒ يحتاج انتباهاً (poor)
_FRESHNESS_DAYS_DEFAULT = 7  # بيانات أقدم ⇒ stale (لا قرار على القديم)

# حالات القرار المفتوحة «الفاعلة» (قيد التنفيذ — تستدعي انتباهاً حتى تُغلَق).
_ACTIVE_DECISION_STATES = {"queued", "dispatched"}


@dataclass
class FieldTwin:
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
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
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
    decisions = list(open_decisions or [])
    blocked = [d for d in decisions if (d.get("state") or "").lower() == "blocked"]
    active = [
        d for d in decisions if (d.get("exec_status") or "").lower() in _ACTIVE_DECISION_STATES
    ]

    # قِدَم البيانات (أيّام) — None إن تعذّر الحساب.
    obs_day = _parse_day(observed_at)
    now_day = _parse_day(now) or date.today()
    data_age_days = (now_day - obs_day).days if obs_day is not None else None

    reasons: list[str] = []
    # ترتيب الأسبقيّة: محجوب ← قديم ← يحتاج انتباهاً ← سليم (محافِظ وصريح).
    if blocked:
        state = "blocked"
        reasons.append(f"{len(blocked)} قرار محجوب (خطّ أحمر) ينتظر معالجة.")
    elif not indices or (data_age_days is not None and data_age_days > freshness_days):
        state = "stale"
        if not indices:
            reasons.append("لا مؤشّرات حديثة — لا يُتَّخذ قرار على بيانات غائبة.")
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

    return FieldTwin(
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
