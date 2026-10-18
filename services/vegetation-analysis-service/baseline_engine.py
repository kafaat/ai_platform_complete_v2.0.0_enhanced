"""RS-5 temporal baseline engine over canonical observations.

The engine consumes canonical timeline entries only. It does not query raster
storage or recompute indicators. The first production-safe baselines are:
previous valid observation and a robust historical envelope. Optional stage
labels may be supplied by the existing field-season projection to restrict
comparisons to the same phenological stage.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from shared.contracts.remote_sensing.admission import admissible, finite_decimal


@dataclass(frozen=True)
class BaselineComparison:
    baseline_run_ref: str
    baseline_type: str
    primary_observation_ref: str
    member_observation_refs: tuple[str, ...]
    observed_value: Decimal
    expected_value: Decimal
    deviation: Decimal
    deviation_percent: Decimal | None
    expected_confidence: Decimal
    sample_size: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_run_ref": self.baseline_run_ref,
            "baseline_type": self.baseline_type,
            "primary_observation_ref": self.primary_observation_ref,
            "member_observation_refs": list(self.member_observation_refs),
            "observed_value": str(self.observed_value),
            "expected_value": str(self.expected_value),
            "deviation": str(self.deviation),
            "deviation_percent": (
                str(self.deviation_percent) if self.deviation_percent is not None else None
            ),
            "expected_confidence": str(self.expected_confidence),
            "sample_size": self.sample_size,
            "reason_codes": list(self.reason_codes),
            "confidence_method": "minimum_measured_input_quality_v2",
            "confidence_is_probability": False,
        }


def _value(entry: dict[str, Any]) -> Decimal | None:
    return finite_decimal((entry.get("summary") or {}).get("mean"))


def _acquired(entry: dict[str, Any]) -> datetime:
    raw = str(entry.get("acquired_at") or "")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _run_ref(
    field_id: str,
    indicator: str,
    current: dict,
    members: list[dict],
    baseline_type: str,
    policy: dict,
) -> str:
    def snapshot(item):
        return {
            key: item.get(key)
            for key in (
                "observation_ref",
                "acquired_at",
                "indicator",
                "summary",
                "observation_quality",
                "lineage",
            )
        }

    payload = {
        "field_id": field_id,
        "indicator": indicator,
        "current": snapshot(current),
        "members": [snapshot(item) for item in members],
        "baseline_type": baseline_type,
        "policy": policy,
        "algorithm": "temporal-baseline-v2",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode()).hexdigest()[:24]
    return f"urn:sahool:processing-run:run_{digest}"


def _comparison(
    *,
    field_id: str,
    indicator: str,
    current: dict[str, Any],
    members: list[dict[str, Any]],
    baseline_type: str,
    policy: dict,
) -> BaselineComparison | None:
    current_value = _value(current)
    values = [v for item in members if (v := _value(item)) is not None]
    if current_value is None or not values:
        return None
    expected = (
        values[-1] if baseline_type == "previous_valid" else Decimal(str(statistics.median(values)))
    )
    deviation = current_value - expected
    deviation_percent = None if expected == 0 else (deviation / abs(expected)) * Decimal("100")
    sample_size = len(values)
    confidence = min(
        Decimal(str(item["observation_quality"][key]))
        for item in [current, *members]
        for key in ("valid_pixel_ratio", "field_coverage_ratio")
    )
    reasons = ["canonical_observations_only"]
    if baseline_type == "historical_robust_median":
        reasons.append("robust_median")
    if baseline_type == "same_phenological_stage":
        reasons.append("stage_matched")
    return BaselineComparison(
        baseline_run_ref=_run_ref(field_id, indicator, current, members, baseline_type, policy),
        baseline_type=baseline_type,
        primary_observation_ref=str(current["observation_ref"]),
        member_observation_refs=tuple(str(item["observation_ref"]) for item in members),
        observed_value=current_value,
        expected_value=expected,
        deviation=deviation,
        deviation_percent=deviation_percent,
        expected_confidence=confidence,
        sample_size=sample_size,
        reason_codes=tuple(reasons),
    )


def build_baselines(
    *,
    field_id: str,
    indicator: str,
    entries: list[dict[str, Any]],
    stage_by_observation: dict[str, str] | None = None,
    current_stage: str | None = None,
    max_history: int = 12,
    max_gap_days: int = 32,
    as_of: datetime | None = None,
) -> list[BaselineComparison]:
    candidates = []
    for item in entries:
        if (item.get("indicator") or {}).get("code") != indicator:
            continue
        try:
            acquired = _acquired(item)
            if acquired.tzinfo is None or not item.get("observation_ref"):
                continue
        except (ValueError, TypeError):
            continue
        candidates.append(item)
    candidates.sort(key=_acquired)
    if (
        not candidates
        or _value(candidates[-1]) is None
        or not admissible(candidates[-1].get("observation_quality") or {})
    ):
        return []
    current = candidates[-1]
    if as_of is not None and not timedelta(0) <= as_of - _acquired(current) <= timedelta(
        days=max_gap_days
    ):
        return []
    valid = [
        item
        for item in candidates
        if _value(item) is not None and admissible(item.get("observation_quality") or {})
    ]
    if len(valid) < 2:
        return []
    history = valid[max(0, len(valid) - 1 - max_history) : -1]
    # Use only the contiguous suffix ending at the current observation. An old
    # cloudy month cannot disable comparisons after adequate observations resume.
    contiguous = []
    next_date = _acquired(current)
    for item in reversed(history):
        acquired = _acquired(item)
        if next_date - acquired > timedelta(days=max_gap_days):
            break
        contiguous.append(item)
        next_date = acquired
    history = list(reversed(contiguous))
    if not history:
        return []
    policy = {
        "max_history": max_history,
        "max_gap_days": max_gap_days,
        "current_stage": current_stage,
        "stage_by_observation": stage_by_observation or {},
    }
    output: list[BaselineComparison] = []

    previous = _comparison(
        field_id=field_id,
        indicator=indicator,
        current=current,
        members=[history[-1]],
        baseline_type="previous_valid",
        policy=policy,
    )
    if previous:
        output.append(previous)

    robust = _comparison(
        field_id=field_id,
        indicator=indicator,
        current=current,
        members=history,
        baseline_type="historical_robust_median",
        policy=policy,
    )
    if robust:
        output.append(robust)

    if current_stage:
        stage_by_observation = stage_by_observation or {}
        stage_members = [
            item
            for item in history
            if stage_by_observation.get(str(item.get("observation_ref"))) == current_stage
        ]
        if not stage_members:
            return []
        stage = _comparison(
            field_id=field_id,
            indicator=indicator,
            current=current,
            members=stage_members,
            baseline_type="same_phenological_stage",
            policy=policy,
        )
        if stage:
            output.append(stage)
    return output
