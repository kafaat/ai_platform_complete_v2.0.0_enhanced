"""api/learning_feedback.py — حلقة التغذية الراجعة للتعلّم (Learning Feedback Loop)

#385: تقرأ دليل المعايرة المتراكم (evidence_registry) لكلّ منطقة وتقترح **أين**
المعايرة ضعيفة و**أيّ** المعاملات تحتاج مراجعة بشريّة — **بلا أيّ تعديل آليّ**.
القرار يبقى للإنسان حتى Adaptive Calibration (#387).

لكلّ منطقة: إجراء مقترَح (جمع بيانات / مراجعة معايرة / تحقّق / مراقبة)، أولويّة،
وأهداف مراجعة (عائلات معاملات مُرشَّحة) مستنبَطة من **أضعف جوانب النجاح**.

نقيّ حتميّ (لا I/O). صدق: اقتراحات لا أوامر؛ `auto_adjust=False` صريح؛ العتبات
تقديريّة موسومة؛ ما يندر قياسه لا يُحاكَم (يُوجَّه لجمع البيانات لا للوم المعايرة).
"""

from __future__ import annotations

from api.event_bus import EventSource

# عتبة نسبة النجاح التي تحت‌ها تُقترَح مراجعة المعايرة. ⚠ تقديريّة.
_LOW_SUCCESS_THRESHOLD = 0.6

# أعلام النجاح ⇒ عائلات معاملات مُرشَّحة للمراجعة البشريّة (تلميح لا إصلاح).
_FLAG_REVIEW_TARGETS: dict[str, list[str]] = {
    "stress_avoided": ["raw_fraction", "root_depth_m"],
    "stress_better": ["raw_fraction", "root_depth_m"],
    "yield_met": ["kc_dyn_max", "uptake_fractions"],
    "water_within_budget": ["forecast_infiltration"],
    # irrigation_followed سلوك مزارع لا فيزياء ⇒ يراجَع واقعيّة السياسة لا المعايرة.
    "irrigation_followed": [],
}


def _review_targets(n: int, flag_counts: dict) -> list[str]:
    """أضعف جوانب النجاح ⇒ عائلات معاملات مُرشَّحة للمراجعة (الأندر تكراراً أوّلاً)."""
    weak = sorted(_FLAG_REVIEW_TARGETS, key=lambda f: flag_counts.get(f, 0))
    targets: list[str] = []
    for f in weak:
        if flag_counts.get(f, 0) <= n * _LOW_SUCCESS_THRESHOLD:
            targets.extend(_FLAG_REVIEW_TARGETS[f])
    return list(dict.fromkeys(targets))  # إزالة التكرار


def _region_feedback(ev: dict) -> dict:
    """تغذية راجعة لمنطقة واحدة من سجلّ دليلها — اقتراح لا أمر."""
    region = ev.get("region", "_generic")
    level = ev.get("evidence_level", "none")
    n = ev.get("sample_count", 0)
    rate = ev.get("success_rate")
    flag_counts = ev.get("success_flag_counts", {}) or {}

    low_rate = rate is not None and rate < _LOW_SUCCESS_THRESHOLD
    review_targets: list[str] = _review_targets(n, flag_counts) if low_rate else []
    if n == 0:
        action = "collect_data"
        priority = 3
        rec = f"لا دليل ميدانيّ لـ{region} — ابدأ جمع قياسات النتائج (ريّ/إجهاد/إنتاج)"
    elif level == "field_sample_complete":
        # U01: العيّنة اكتملت لكن لا اعتماد بعد — بوّابةُ المراجعة تسبق تصنيفَ النسبة
        # (Copilot على #1001: كانت النسبةُ المنخفضة تحجب هذا الفرع)؛ النسبةُ المنخفضة ترفع
        # الأولويّة وتحمل أهدافَ المعايرة معها، والإجراءُ يبقى مراجعةَ مختصّ.
        action = "expert_review"
        priority = 3 if low_rate else 2
        rec = f"عيّنة {region} بلغت العتبة ({n}) — تلزم مراجعة مختصّ قبل اعتماد الدليل"
        if low_rate:
            rec += f"؛ ونسبةُ النجاح منخفضة ({rate}) فراجِع المعاملات المُرشَّحة معها"
    elif low_rate:
        action = "review_calibration"
        priority = 3
        rec = f"نسبة نجاح القرار منخفضة في {region} ({rate}) — راجِع المعاملات يدويّاً"
    elif level == "field_preliminary":
        action = "verify"
        priority = 2
        need = ev.get("samples_to_verified", 0)
        rec = f"دليل أوّليّ لـ{region} — اجمع {need} عيّنة إضافيّة للتحقّق الميدانيّ"
    else:  # field_verified بنسبة نجاح جيّدة
        action = "monitor"
        priority = 1
        rec = f"معايرة {region} مدعومة ميدانيّاً وأداؤها جيّد — راقِب فقط"

    return {
        "region": region,
        "evidence_level": level,
        "sample_count": n,
        "success_rate": rate,
        "action": action,
        "priority": priority,
        "review_targets": review_targets,
        "recommendation_ar": rec,
    }


def learning_feedback(evidence_records: list[dict]) -> dict:
    """يحوّل دليل المناطق إلى أولويّات مراجعة بشريّة — نقيّ حتميّ، بلا تعديل آليّ.

    evidence_records: قائمة مخرجات aggregate_evidence لكلّ منطقة. يرتّب تنازليّاً
    بالأولويّة (الأعلى أوّلاً). صدق: اقتراحات فقط؛ auto_adjust=False صريح.
    """
    regions = [_region_feedback(ev) for ev in evidence_records]
    regions.sort(key=lambda r: (-r["priority"], r["region"]))

    rates = [r["success_rate"] for r in regions if r["success_rate"] is not None]
    summary = {
        "n_regions": len(regions),
        "n_none": sum(r["evidence_level"] == "none" for r in regions),
        "n_preliminary": sum(r["evidence_level"] == "field_preliminary" for r in regions),
        "n_sample_complete": sum(r["evidence_level"] == "field_sample_complete" for r in regions),
        "n_verified": sum(r["evidence_level"] == "field_verified" for r in regions),
        "mean_success_rate": round(sum(rates) / len(rates), 3) if rates else None,
        "regions_needing_data": [r["region"] for r in regions if r["action"] == "collect_data"],
        # U01: مراجعةُ المعايرة ومراجعةُ المختصّ كلتاهما «تحتاج مراجعة» (Copilot على #1001).
        "regions_needing_review": [
            r["region"] for r in regions if r["action"] in ("review_calibration", "expert_review")
        ],
    }

    return {
        "regions": regions,
        "summary": summary,
        "auto_adjust": False,  # صريح: لا تعديل آليّ — القرار للإنسان (#387 لاحقاً)
        "calibrated": False,
        "warnings_ar": [
            "عتبات الأولويّة/النجاح تقديريّة؛ هذه اقتراحات مراجعة بشريّة لا أوامر تعديل",
        ],
    }


def _stable_digest(payload: dict) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def independent_outcome_units(outcomes: list[dict], *, field_id: str, season_id: str) -> set:
    """وحداتُ التكرار المستقلّة: (المزرعة، الموسم) المتمايزة — لا الصفوف (F5).

    صفٌّ بلا ``farm_id`` يُنسَب إلى حقله (``field:<id>`` — حقلُ الصفّ نفسه إن حمله، وإلّا الحقلُ
    المُغلَق) فلا يُختلَق استقلالٌ من فراغ، ولا يُحتسَب كلُّ صفٍّ فارغٍ وحدةً منفصلة. صفوفُ وحدةٍ
    واحدة المكرَّرة تُعَدّ مرّةً واحدة (مجموعة).
    """
    return {_outcome_unit(o, field_id=field_id, season_id=season_id) for o in outcomes}


def _outcome_unit(o: dict, *, field_id: str, season_id: str) -> tuple[str, str]:
    return (
        str(o.get("farm_id") or f"field:{o.get('field_id') or field_id}"),
        str(o.get("season_id") or season_id),
    )


# ── تجميع الدليل عبر وحداتٍ مستقلّة متماثلة ──────────────────────────────────────────
# حقلٌ-موسمٌ واحد وحدةٌ واحدة، فالحدُّ الأدنى (٣ افتراضاً) لا يُبلَغ من إغلاقٍ واحد أبداً. يُجمَّع
# الدليلُ من مواسم المستأجِر **الأخرى المكتملة** المتماثلة مع المُغلَق. مفتاحُ التماثل أضيقُ ما تحمله
# صفوف ``recommendation_outcomes`` (v49) بصدق: المستأجِر (RLS + مُسنَدٌ صريح) × المحصول القانونيّ
# (``resolve_crop_id`` على عمود ``crop``؛ اسمٌ مجهول أو ملتبس ⇒ لا تجميع) × المهمّة
# ``yield_forecast_calibration`` (كلُّ صفوف الجدول أزواجُ غلّة، وسياسةُ الأهليّة تُسقِط ما لا زوجَ له).
# لا عمودَ لإصدار النموذج/السياسة ولا للإقليم على الصفّ، والإقليمُ (``fields.zone_key``) جدولٌ لا يقرؤه
# هذا المسار — فلا يُدَّعى تماثلٌ أضيق ممّا يُقاس. «مكتمل» = صفٌّ اجتاز سياسة الأهليّة نفسها
# (ناضج + قيمة فعليّة منتهية).
LEARNING_POOL_TASK = "yield_forecast_calibration"


def _normalized_tenant(value) -> str:
    from uuid import UUID

    text = str(value or "").strip()
    try:
        return str(UUID(text))
    except (TypeError, ValueError):
        return text.lower()


def resolve_pooling_crop(outcomes: list[dict]) -> tuple[str | None, str | None]:
    """المحصولُ القانونيّ للوحدة المُغلَقة من صفوفها: ``(crop_id, None)`` أو ``(None, السبب)``.

    بلا محصول ⇒ ``POOLING_CROP_MISSING``؛ اسمٌ لا تحلّه البطاقات ⇒ ``POOLING_CROP_UNRESOLVED``؛
    أكثر من محصولٍ قانونيّ في الحقل-الموسم ⇒ ``POOLING_CROP_AMBIGUOUS``. لا تخمين.
    """
    from core.season_phenology import resolve_crop_id

    raws = {str(o.get("crop")).strip() for o in outcomes if str(o.get("crop") or "").strip()}
    if not raws:
        return None, "POOLING_CROP_MISSING"
    ids = {resolve_crop_id(raw) for raw in raws}
    if None in ids:
        return None, "POOLING_CROP_UNRESOLVED"
    if len(ids) != 1:
        return None, "POOLING_CROP_AMBIGUOUS"
    return ids.pop(), None


def comparable_pool_rows(
    candidates: list[dict],
    *,
    tenant_id: str,
    crop_id: str,
    field_id: str,
    season_id: str,
) -> tuple[list[dict], dict[str, int]]:
    """صفوفُ الحقول-المواسم الأخرى المتماثلة ``(rows, rejected_reasons)`` — دفاعٌ ثانٍ فوق SQL.

    يُرفَض: مستأجِرٌ آخر أو غائب (``tenant_mismatch``)، محصولٌ قانونيّ آخر (``crop_mismatch``)،
    صفوفُ الحقل-الموسم المُغلَق نفسه (تُقرأ في استعلامها فلا تُعَدّ مرّتين: ``closing_unit_row``)،
    صفٌّ بلا موسم (``missing_season`` — لا يُنسَب إلى الموسم المُغلَق) أو بلا مزرعة ولا حقل
    (``missing_unit_identity``).
    """
    from core.season_phenology import resolve_crop_id

    tenant = _normalized_tenant(tenant_id)
    kept: list[dict] = []
    rejected: dict[str, int] = {}

    def _reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for row in candidates:
        if not row.get("tenant_id") or _normalized_tenant(row.get("tenant_id")) != tenant:
            _reject("tenant_mismatch")
        elif resolve_crop_id(str(row.get("crop") or "")) != crop_id:
            _reject("crop_mismatch")
        elif not row.get("season_id"):
            _reject("missing_season")
        elif not (row.get("farm_id") or row.get("field_id")):
            _reject("missing_unit_identity")
        elif str(row.get("field_id") or "") == str(field_id) and str(row["season_id"]) == str(
            season_id
        ):
            _reject("closing_unit_row")
        else:
            kept.append(row)
    return kept, rejected


def contributing_units(
    paired: list[dict], *, closing_units: set, field_id: str, season_id: str
) -> list[dict]:
    """قائمةُ الوحدات المساهِمة القابلة للتدقيق: الوحدة + عدد نتائجها المؤهّلة + هل هي المُغلَقة."""
    counts: dict[tuple[str, str], int] = {}
    for o in paired:
        unit = _outcome_unit(o, field_id=field_id, season_id=season_id)
        counts[unit] = counts.get(unit, 0) + 1
    return [
        {
            "farm_id": farm,
            "season_id": season,
            "outcome_count": n,
            "closing": (farm, season) in closing_units,
        }
        for (farm, season), n in sorted(counts.items())
    ]


def outcome_source_digests(rows: list[dict]) -> list[str]:
    """بصمةُ كلّ صفٍّ مساهِم على أعمدة الدليل **وهويّة وحدته** (مزرعة/موسم/حقل/محصول).

    هويّةُ الوحدة داخل البصمة: مجمّعٌ مختلف (وحدةٌ أُضيفت/أُسقِطت/استُبدِلت) يُنتج بصماتٍ مختلفة فلا
    يرث مراجعةَ غيره. المستأجِر يُستبعَد (ثابتٌ تحت RLS).
    """
    return sorted(
        _stable_digest({k: v for k, v in row.items() if k != "tenant_id"}) for row in rows
    )


def learning_pool_digest(*, pooling_key: dict, units: list[dict], source_digests: list[str]) -> str:
    """بصمةُ المجمّع كاملاً (المفتاح + الوحدات + بصمات الصفوف) — تربط المراجعةَ بمجمّعٍ بعينه."""
    return _stable_digest(
        {"pooling_key": pooling_key, "units": units, "source_digests": source_digests}
    )


# ── مراجعة المرشَّحات (F7) ─────────────────────────────────────────────────────────
# جدولا المرشَّحات (governed_model_promotion_candidates · irrigation_learning_proposals) يقبلان
# approved/rejected مع reviewed_by فارغ على مستوى المخطّط. لا مسارَ يكتب الحالتين اليوم؛ أيُّ
# كاتبٍ لاحق يمرّ بهذه البوّابة النقيّة فلا تُعتمَد مرشَّحةٌ بلا مراجِع وزمن.
CANDIDATE_REVIEW_TERMINAL = frozenset({"approved", "rejected"})
_CANDIDATE_REVIEW_FROM = {
    "approved": frozenset({"review_ready"}),
    "rejected": frozenset({"review_ready", "monitor", "blocked"}),
}


def learning_candidate_review_transition(
    current_status: str,
    new_status: str,
    *,
    reviewed_by: str | None,
    reviewed_at=None,
    evidence_pool_digest: str | None = None,
    reviewed_pool_digest: str | None = None,
) -> dict:
    """يتحقّق من انتقال مراجعة مرشَّح تعلّم ويُعيد الأعمدة الواجب كتابتها معاً.

    approved/rejected ⇒ ``reviewed_by`` غير فارغ إلزاميّاً و``reviewed_at`` (الآن إن غاب)؛
    الاعتمادُ من ``review_ready`` فقط؛ الحالةُ النهائيّة لا تُراجَع ثانيةً. يرفع ``ValueError``.

    مرشَّحٌ مجمَّع يحمل ``pool_digest`` في دليله: حين يُمرَّر (``evidence_pool_digest``) لا يُعتمَد إلّا
    بمراجعةٍ تُسمّي البصمةَ نفسها (``reviewed_pool_digest``) — مراجعةُ مجمّعٍ لا تُنقَل إلى مجمّعٍ آخر.
    """
    from datetime import UTC, datetime

    if new_status not in CANDIDATE_REVIEW_TERMINAL:
        raise ValueError(f"UNSUPPORTED_REVIEW_STATUS:{new_status}")
    if current_status in CANDIDATE_REVIEW_TERMINAL:
        raise ValueError(f"CANDIDATE_ALREADY_REVIEWED:{current_status}")
    if current_status not in _CANDIDATE_REVIEW_FROM[new_status]:
        raise ValueError(f"INVALID_REVIEW_TRANSITION:{current_status}->{new_status}")
    reviewer = (reviewed_by or "").strip() if isinstance(reviewed_by, str) else ""
    if not reviewer:
        raise ValueError("REVIEWER_REQUIRED")
    if (
        new_status == "approved"
        and evidence_pool_digest is not None
        and reviewed_pool_digest != evidence_pool_digest
    ):
        raise ValueError("REVIEWED_POOL_DIGEST_MISMATCH")
    return {
        "status": new_status,
        "reviewed_by": reviewer,
        "reviewed_at": reviewed_at or datetime.now(UTC),
    }


# الحدُّ المطلوب كما طُبِّق — مُميِّزٌ لا ``None`` لأنّ ``None`` نفسه حمولةٌ سيّئة تُعلَن.
_REQUESTED_AS_APPLIED = object()


def _has_eligible_outcome(outcomes: list[dict]) -> bool:
    from core.outcome_reconciler import recommendation_outcome_eligibility

    return any(
        recommendation_outcome_eligibility(o, require_acceptance=False)["eligible"]
        for o in outcomes
    )


def evaluate_season_learning(
    outcomes: list[dict],
    pool_rows: list[dict],
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    minimum_outcomes: int,
    requested_minimum=_REQUESTED_AS_APPLIED,
) -> dict:
    """تقييمُ مرشَّح التعلّم من صفوف الوحدة المُغلَقة وصفوف المجمّع المقروءة — نقيّ حتميّ.

    ``outcomes``: صفوف الحقل-الموسم المُغلَق. ``pool_rows``: صفوف الحقول-المواسم الأخرى المرشَّحة
    (تُفرَز هنا بالمستأجِر والمحصول القانونيّ والهويّة؛ لا يُوثَق بالاستعلام وحده). أقلّ من الحدّ الأدنى
    من الوحدات المستقلّة ⇒ ``blocked`` + ``MINIMUM_INDEPENDENT_UNITS_NOT_MET`` والعددُ الفعليّ.
    """
    if requested_minimum is _REQUESTED_AS_APPLIED:
        requested_minimum = minimum_outcomes
    # U02 (التدقيق الموحَّد 2026-09-13): سياسةُ الأهليّة نفسها التي يستعملها الموحِّد —
    # قيمةٌ فعليّة مبكّرة قبل النضج أو غير منتهية لا تدخل حساب MAE ولا تعدّ نحو الحدّ
    # الأدنى. دراسةُ دقّة التوقّع لا تشترط قبولَ التوصية (رفضُ المزارع لا يمحو حصاده).
    from core.outcome_reconciler import recommendation_outcome_eligibility

    excluded_reasons: dict[str, int] = {}

    def _eligible(items: list[dict]) -> list[dict]:
        kept: list[dict] = []
        for o in items:
            verdict = recommendation_outcome_eligibility(o, require_acceptance=False)
            if verdict["eligible"]:
                kept.append(o)
            else:
                reason = str(verdict["reason"])
                excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
        return kept

    closing_paired = _eligible(outcomes)
    closing_units = independent_outcome_units(
        closing_paired, field_id=field_id, season_id=season_id
    )

    # التجميع عبر الوحدات المتماثلة (انظر LEARNING_POOL_TASK): لا يُفعَّل إلّا إذا ساهمت الوحدةُ
    # المُغلَقة نفسها بنتيجةٍ مؤهّلة وحُلَّ محصولُها قانونيّاً — وإلّا يبقى العدُّ على وحدتها وحدها.
    crop_id, pooling_limitation = resolve_pooling_crop(outcomes)
    if crop_id is not None and not closing_paired:
        pooling_limitation = "POOLING_REQUIRES_ELIGIBLE_CLOSING_OUTCOME"
    pool_candidates: list[dict] = []
    pool_rejected: dict[str, int] = {}
    if pooling_limitation is None and crop_id is not None:
        pool_candidates, pool_rejected = comparable_pool_rows(
            pool_rows,
            tenant_id=tenant_id,
            crop_id=crop_id,
            field_id=field_id,
            season_id=season_id,
        )
    pooled_paired = _eligible(pool_candidates)
    paired = closing_paired + pooled_paired
    considered = len(outcomes) + len(pool_candidates)
    errors = [float(o["actual_yield_t_ha"]) - float(o["predicted_yield_t_ha"]) for o in paired]
    mae = None if not errors else round(sum(abs(v) for v in errors) / len(errors), 6)
    bias = None if not errors else round(sum(errors) / len(errors), 6)
    # F5 (pseudo-replication): صفوفُ حقلٍ-موسمٍ واحد ليست عيّناتٍ مستقلّة. الحدُّ الأدنى يُقاس
    # بوحدات (المزرعة، الموسم) المتمايزة لا بعدد الصفوف — ثلاثُ نتائج لموسمٍ واحد وحدةٌ واحدة،
    # ووحدةٌ تظهر في الإغلاق وفي المجمّع معاً تُعَدّ مرّةً واحدة.
    units = independent_outcome_units(paired, field_id=field_id, season_id=season_id)
    unit_list = contributing_units(
        paired, closing_units=closing_units, field_id=field_id, season_id=season_id
    )
    enough = len(units) >= minimum_outcomes
    limitations = []
    if len(paired) < minimum_outcomes:
        limitations.append("MINIMUM_VERIFIED_OUTCOMES_NOT_MET")
    if not enough:
        limitations.append("MINIMUM_INDEPENDENT_UNITS_NOT_MET")
    if pooling_limitation is not None:
        limitations.append(pooling_limitation)
    pooling_key = {
        "tenant_scope": "app.current_tenant",
        "crop_id": crop_id,
        "task": LEARNING_POOL_TASK,
        "source_table": "recommendation_outcomes",
    }
    # البصمةُ على كلّ صفٍّ مساهِم بهويّة وحدته — مجمّعٌ مختلف ⇒ بصماتٌ مختلفة ⇒ مرشَّحٌ مختلف.
    source_digests = outcome_source_digests(paired)
    evaluation = {
        "field_id": field_id,
        "season_id": season_id,
        "outcome_count": len(paired),
        "closing_unit_outcome_count": len(closing_paired),
        "excluded_count": considered - len(paired),
        "excluded_reasons": excluded_reasons,
        "independent_units": len(units),
        "unit_basis": "distinct (farm_id, season_id)",
        "pooling_key": pooling_key,
        "pooling_applied": pooling_limitation is None and crop_id is not None,
        "pool_rejected": pool_rejected,
        "contributing_units": unit_list,
        "contributing_unit_count": len(unit_list),
        "minimum_outcomes": minimum_outcomes,
        **(
            {"minimum_outcomes_requested": requested_minimum}
            if requested_minimum != minimum_outcomes
            else {}
        ),
        "mae_t_ha": mae,
        "bias_t_ha": bias,
        "status": "review_ready" if enough else "blocked",
        "limitations": limitations,
        "source_digests": source_digests,
        "pool_digest": learning_pool_digest(
            pooling_key=pooling_key, units=unit_list, source_digests=source_digests
        ),
    }
    return evaluation


async def process_season_closed_event(
    conn,
    *,
    event_id: str,
    tenant_id: str,
    field_id: str,
    season_id: str,
    minimum_outcomes: int = 3,
) -> dict:
    """Build one governed learning candidate from persisted outcomes.

    The event provides identifiers only. Outcomes are loaded under tenant RLS;
    model promotion is never automatic and replay is idempotent by event_id.
    """
    import json
    from uuid import UUID

    # الحدُّ الأدنى يأتي من حمولة الحدث بلا تحقّق — صفرٌ أو سالب كان يُمرّر `enough` على عيّنة
    # فارغة فيُنشئ مرشَّحاً `review_ready` بلا نتيجة (Copilot على #1001). يُطبَّع إلى ≥ 1 ويُعلَن
    # المطلوبُ الأصليّ حين يختلف.
    requested_minimum = minimum_outcomes
    try:
        minimum_outcomes = max(1, int(minimum_outcomes))
    except (TypeError, ValueError):
        minimum_outcomes = 3

    # القفلُ **قبل** فحص الإعادة (Copilot على #1001): تسليمان متزامنان كانا يريان «لا صفّ»
    # معاً ثمّ يُصدِران الحدثَ مرّتين رغم ON CONFLICT DO NOTHING — الثاني ينتظر القفل ثمّ يرى
    # صفَّ الأوّل ويعود بالتقييم المخزَّن.
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"season-learning:{event_id}")
    existing = await conn.fetchrow(
        "SELECT evaluation FROM decision_learning_runs WHERE event_id=$1", event_id
    )
    if existing is not None:
        stored = existing["evaluation"]
        # JSONB عبر اتّصال asyncpg خام (العامل بلا codec) يصل نصّاً — يُفكّ قبل التحويل
        # (Copilot على #1001: كان `dict(str)` يرفع فينكسر مسارُ الإعادة بعد أوّل إغلاق ناجح).
        if isinstance(stored, (str, bytes, bytearray)):
            stored = json.loads(stored)
        return {
            "status": "replayed",
            "idempotent_replay": True,
            "evaluation": dict(stored or {}),
        }

    # الترتيبُ بأعمدة الجدول الفعليّة (v49: outcome_id/issued_at/outcome_recorded_at) — كان
    # `created_at,id` فيفشل كلُّ إغلاق موسم بعمود غير معرَّف قبل أيّ إدامة (Copilot على #1001).
    rows = await conn.fetch(
        """SELECT recommendation_id,predicted_yield_t_ha,actual_yield_t_ha,accepted,matured_within_lag,
                  farm_id,season_id,field_id,crop
           FROM recommendation_outcomes
           WHERE field_id=$1 AND season_id=$2
           ORDER BY COALESCE(outcome_recorded_at, issued_at),outcome_id""",
        field_id,
        season_id,
    )
    outcomes = [dict(row) for row in rows]
    crop_id, pooling_limitation = resolve_pooling_crop(outcomes)
    pool_rows: list[dict] = []
    if pooling_limitation is None and _has_eligible_outcome(outcomes):
        # أسماءُ المحصول الخام لدى المستأجِر التي تحلّها البطاقات إلى المحصول نفسه — ثمّ مطابقةٌ تامّة
        # في SQL. المستأجِر مُسنَدٌ صريح فوق RLS (لا اعتمادَ على السياسة وحدها، ولا عبورَ مستأجِر)،
        # ثمّ يُعاد فرزُ كلّ صفٍّ في ``comparable_pool_rows`` (دفاعٌ ثانٍ).
        from core.season_phenology import resolve_crop_id

        crop_rows = await conn.fetch(
            """SELECT DISTINCT crop FROM recommendation_outcomes
               WHERE crop IS NOT NULL
                 AND tenant_id::text = NULLIF(current_setting('app.current_tenant', TRUE), '')"""
        )
        raw_crops = sorted(
            {
                str(r["crop"])
                for r in (dict(x) for x in crop_rows)
                if r.get("crop") and resolve_crop_id(str(r["crop"])) == crop_id
            }
        )
        if raw_crops:
            fetched = await conn.fetch(
                """SELECT tenant_id::text AS tenant_id,recommendation_id,predicted_yield_t_ha,
                          actual_yield_t_ha,accepted,matured_within_lag,farm_id,season_id,field_id,crop
                   FROM recommendation_outcomes
                   WHERE crop = ANY($1::text[])
                     AND season_id IS NOT NULL
                     AND NOT (field_id IS NOT DISTINCT FROM $2 AND season_id = $3)
                     AND tenant_id::text = NULLIF(current_setting('app.current_tenant', TRUE), '')
                   ORDER BY COALESCE(outcome_recorded_at, issued_at),outcome_id""",
                raw_crops,
                field_id,
                season_id,
            )
            pool_rows = [dict(r) for r in fetched]
    evaluation = evaluate_season_learning(
        outcomes,
        pool_rows,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        minimum_outcomes=minimum_outcomes,
        requested_minimum=requested_minimum,
    )
    paired_count = evaluation["outcome_count"]
    learning_digest = _stable_digest(evaluation)
    # الجدول يحمل قيدَين فريدَين: (tenant_id,event_id) و(tenant_id,learning_digest). كان
    # الهدفُ الأوّل وحده ⇒ إغلاقٌ ثانٍ للموسم نفسه (event_id جديد، تقييمٌ مطابق) يرفع
    # UniqueViolation على البصمة فيُعاد تسليمه إلى الأبد (رسالة سامّة). بلا هدف ⇒ أيّ
    # تعارضٍ فريد إعادةٌ صامتة، ولا يُصدَر حدثٌ ثانٍ لتقييمٍ سبق تسجيلُه.
    inserted_run = await conn.fetchval(
        """INSERT INTO decision_learning_runs
        (tenant_id,season_id,field_id,event_id,status,outcome_count,source_digests,evaluation,learning_digest)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
        ON CONFLICT DO NOTHING
        RETURNING id""",
        season_id,
        field_id,
        event_id,
        evaluation["status"],
        paired_count,
        json.dumps(evaluation["source_digests"]),
        json.dumps(evaluation),
        learning_digest,
    )
    if inserted_run is None:
        return {
            "status": "replayed",
            "idempotent_replay": True,
            "replay_reason": "LEARNING_DIGEST_ALREADY_RECORDED",
            "evaluation": evaluation,
        }
    candidate = {
        "candidate_id": f"gmp_{learning_digest[:20]}",
        "season_id": season_id,
        "task": LEARNING_POOL_TASK,
        "status": evaluation["status"],
        "review_required": True,
        "auto_promote": False,
        "evidence": evaluation,
    }
    candidate_digest = _stable_digest(candidate)
    await conn.execute(
        """INSERT INTO governed_model_promotion_candidates
        (tenant_id,candidate_id,season_id,task,status,review_required,auto_promote,evidence,candidate_digest)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,TRUE,FALSE,$5::jsonb,$6)
        ON CONFLICT (tenant_id,candidate_id) DO NOTHING""",
        candidate["candidate_id"],
        season_id,
        candidate["task"],
        candidate["status"],
        json.dumps(evaluation),
        candidate_digest,
    )
    outbox_event_id = await conn.fetchval(
        """SELECT emit_event($1::text,'season'::text,$2::text,$3::uuid,$4::jsonb,$5::text,NULL::text,$6::uuid,now())""",
        "decision.learning.review_requested",
        season_id,
        UUID(tenant_id),
        json.dumps({"learning_digest": learning_digest, "candidate": candidate}),
        # ``source`` is the constrained enum, not a module name — see EventSource.
        EventSource.SYSTEM.value,
        None,
    )
    return {
        "status": evaluation["status"],
        "evaluation": evaluation,
        "promotion_candidate": {**candidate, "candidate_digest": candidate_digest},
        "event_id": str(outbox_event_id) if outbox_event_id else None,
    }


async def existing_recommendation_outcome(conn, tenant_id: str, recommendation_id: str):
    """The stored outcome row for (tenant, recommendation_id), or None.

    Read by the pre-cutover outcome writer after it takes the advisory lock, so a repeat is
    replayed or completed instead of adding a second sample (F4). Kept in this module, which
    already reads ``recommendation_outcomes``, so the S5-EXEC-01 frozen runtime read surface
    does not gain a new file.
    """
    return await conn.fetchrow(
        "SELECT outcome_id, actual_yield_t_ha FROM recommendation_outcomes "
        "WHERE tenant_id = $1::uuid AND recommendation_id = $2 "
        "ORDER BY outcome_id LIMIT 1",
        tenant_id,
        recommendation_id,
    )
