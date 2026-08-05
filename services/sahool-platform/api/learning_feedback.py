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


def _region_feedback(ev: dict) -> dict:
    """تغذية راجعة لمنطقة واحدة من سجلّ دليلها — اقتراح لا أمر."""
    region = ev.get("region", "_generic")
    level = ev.get("evidence_level", "none")
    n = ev.get("sample_count", 0)
    rate = ev.get("success_rate")
    flag_counts = ev.get("success_flag_counts", {}) or {}

    review_targets: list[str] = []
    if n == 0:
        action = "collect_data"
        priority = 3
        rec = f"لا دليل ميدانيّ لـ{region} — ابدأ جمع قياسات النتائج (ريّ/إجهاد/إنتاج)"
    elif rate is not None and rate < _LOW_SUCCESS_THRESHOLD:
        action = "review_calibration"
        priority = 3
        # أضعف جوانب النجاح ⇒ عائلات معاملات مُرشَّحة (الأندر تكراراً).
        weak = sorted(_FLAG_REVIEW_TARGETS, key=lambda f: flag_counts.get(f, 0))
        for f in weak:
            if flag_counts.get(f, 0) <= n * _LOW_SUCCESS_THRESHOLD:
                review_targets.extend(_FLAG_REVIEW_TARGETS[f])
        review_targets = list(dict.fromkeys(review_targets))  # إزالة التكرار
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
        "n_verified": sum(r["evidence_level"] == "field_verified" for r in regions),
        "mean_success_rate": round(sum(rates) / len(rates), 3) if rates else None,
        "regions_needing_data": [r["region"] for r in regions if r["action"] == "collect_data"],
        "regions_needing_review": [
            r["region"] for r in regions if r["action"] == "review_calibration"
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

    existing = await conn.fetchrow(
        "SELECT evaluation FROM decision_learning_runs WHERE event_id=$1", event_id
    )
    if existing is not None:
        return {
            "status": "replayed",
            "idempotent_replay": True,
            "evaluation": dict(existing["evaluation"] or {}),
        }

    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"season-learning:{event_id}")
    rows = await conn.fetch(
        """SELECT recommendation_id,predicted_yield_t_ha,actual_yield_t_ha,accepted,matured_within_lag
           FROM recommendation_outcomes
           WHERE field_id=$1 AND season_id=$2 AND actual_yield_t_ha IS NOT NULL
           ORDER BY created_at,id""",
        field_id,
        season_id,
    )
    outcomes = [dict(row) for row in rows]
    source_digests = sorted(_stable_digest(item) for item in outcomes)
    paired = [
        o
        for o in outcomes
        if o.get("predicted_yield_t_ha") is not None and o.get("actual_yield_t_ha") is not None
    ]
    errors = [float(o["actual_yield_t_ha"]) - float(o["predicted_yield_t_ha"]) for o in paired]
    mae = None if not errors else round(sum(abs(v) for v in errors) / len(errors), 6)
    bias = None if not errors else round(sum(errors) / len(errors), 6)
    enough = len(paired) >= minimum_outcomes
    evaluation = {
        "field_id": field_id,
        "season_id": season_id,
        "outcome_count": len(paired),
        "minimum_outcomes": minimum_outcomes,
        "mae_t_ha": mae,
        "bias_t_ha": bias,
        "status": "review_ready" if enough else "blocked",
        "limitations": [] if enough else ["MINIMUM_VERIFIED_OUTCOMES_NOT_MET"],
        "source_digests": source_digests,
    }
    learning_digest = _stable_digest(evaluation)
    await conn.execute(
        """INSERT INTO decision_learning_runs
        (tenant_id,season_id,field_id,event_id,status,outcome_count,source_digests,evaluation,learning_digest)
        VALUES (current_setting('app.current_tenant')::uuid,$1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
        ON CONFLICT (tenant_id,event_id) DO NOTHING""",
        season_id,
        field_id,
        event_id,
        evaluation["status"],
        len(paired),
        json.dumps(source_digests),
        json.dumps(evaluation),
        learning_digest,
    )
    candidate = {
        "candidate_id": f"gmp_{learning_digest[:20]}",
        "season_id": season_id,
        "task": "yield_forecast_calibration",
        "status": "review_ready" if enough else "blocked",
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
