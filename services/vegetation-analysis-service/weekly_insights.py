"""Versioned bilingual field-insight snapshots; no generated claims or delivery."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from anomaly_engine import detect_signals
from baseline_engine import build_baselines


def build_weekly_insights(*, tenant_id: str, week_end: datetime, fields: list[dict]) -> dict:
    if week_end.tzinfo is None:
        raise ValueError("week_end_requires_timezone")
    week_end = week_end.astimezone(UTC)
    period_start = week_end - timedelta(days=7)
    history_start = week_end - timedelta(days=14)
    rows = []
    for field in sorted(fields, key=lambda x: (x["field_id"], x["season_id"])):
        entries = []
        for entry in field.get("entries", []):
            acquired = datetime.fromisoformat(str(entry["acquired_at"]).replace("Z", "+00:00"))
            if history_start <= acquired <= week_end:
                entries.append(entry)
        comparisons = build_baselines(
            field_id=field["field_id"],
            indicator="ndvi",
            entries=entries,
            current_stage=field.get("current_stage"),
            stage_by_observation=field.get("stage_by_observation"),
            as_of=week_end,
            max_gap_days=7,
        )
        signals = detect_signals(
            field_id=field["field_id"],
            indicator="ndvi",
            comparisons=[item.to_dict() for item in comparisons],
            now=week_end,
        )
        status = (
            "review_requested"
            if signals
            else "no_material_change"
            if comparisons
            else "not_assessable"
        )
        summaries = {
            "review_requested": {
                "ar": "تغير في المؤشر يستحق الكشف الميداني؛ السبب الزراعي غير مثبت.",
                "en": "An indicator change merits scouting; its agronomic cause is unverified.",
            },
            "no_material_change": {
                "ar": "لم يتجاوز التغير عتبة السياسة ضمن الرصد المتاح؛ لا يعني خلو الحقل من المشكلات.",
                "en": "No change exceeds the policy threshold in available observations; this does not establish field health.",
            },
            "not_assessable": {
                "ar": "لا توجد مقارنة مؤهلة كافية؛ راجع جودة الصور وتواريخها وسياق الموسم.",
                "en": "Insufficient qualified comparison; review image quality, dates and season context.",
            },
        }
        rows.append(
            {
                "field_id": field["field_id"],
                "season_id": field["season_id"],
                "status": status,
                "summary": summaries[status],
                "reason_codes": field.get("reason_codes", [])
                or ([] if comparisons else ["insufficient_qualified_history"]),
                "comparisons": [c.to_dict() for c in comparisons],
                "signals": [signal.to_dict() for signal in signals],
            }
        )
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    rows.sort(
        key=lambda row: (
            rank.get(row["signals"][0]["severity"], 5) if row["signals"] else 5,
            row["field_id"],
            row["season_id"],
        )
    )
    snapshot = {
        "schema": "sahool.weekly-field-insights.v1",
        "tenant_id": tenant_id,
        "policy": "qualified-previous-or-stage-v2",
        "window_start": period_start.isoformat(),
        "window_end": week_end.isoformat(),
        "history_start": history_start.isoformat(),
        "fields": rows,
        "confidence_is_probability": False,
        "delivery_status": "not_requested",
        "persistence": "response_snapshot_only",
    }
    content = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**snapshot, "snapshot_sha256": hashlib.sha256(content.encode()).hexdigest()}
