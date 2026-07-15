"""RS-5 temporal baseline engine over canonical observations.

The engine consumes canonical timeline entries only. It does not query raster
storage or recompute indicators. The first production-safe baselines are:
previous valid observation and a robust historical envelope. Optional stage
labels may be supplied by the existing field-season projection to restrict
comparisons to the same phenological stage.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


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
        }


def _value(entry: dict[str, Any]) -> Decimal | None:
    summary = entry.get("summary") or {}
    raw = summary.get("mean")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError, TypeError):
        return None


def _acquired(entry: dict[str, Any]) -> datetime:
    raw = str(entry.get("acquired_at") or "")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _run_ref(field_id: str, indicator: str, current_ref: str, baseline_type: str) -> str:
    digest = hashlib.sha256(
        f"{field_id}|{indicator}|{current_ref}|{baseline_type}".encode()
    ).hexdigest()[:24]
    return f"urn:sahool:processing-run:run_{digest}"


def _comparison(
    *,
    field_id: str,
    indicator: str,
    current: dict[str, Any],
    members: list[dict[str, Any]],
    baseline_type: str,
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
    confidence = min(Decimal("0.95"), Decimal("0.55") + Decimal(sample_size) * Decimal("0.08"))
    reasons = ["canonical_observations_only"]
    if baseline_type == "historical_robust_median":
        reasons.append("robust_median")
    if baseline_type == "same_phenological_stage":
        reasons.append("stage_matched")
    return BaselineComparison(
        baseline_run_ref=_run_ref(
            field_id, indicator, str(current["observation_ref"]), baseline_type
        ),
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
) -> list[BaselineComparison]:
    valid = [
        item
        for item in entries
        if (item.get("indicator") or {}).get("code") == indicator
        and (item.get("observation_quality") or {}).get("gate_status") == "passed"
        and _value(item) is not None
    ]
    valid.sort(key=_acquired)
    if len(valid) < 2:
        return []
    current = valid[-1]
    history = valid[max(0, len(valid) - 1 - max_history) : -1]
    output: list[BaselineComparison] = []

    previous = _comparison(
        field_id=field_id,
        indicator=indicator,
        current=current,
        members=[history[-1]],
        baseline_type="previous_valid",
    )
    if previous:
        output.append(previous)

    robust = _comparison(
        field_id=field_id,
        indicator=indicator,
        current=current,
        members=history,
        baseline_type="historical_robust_median",
    )
    if robust:
        output.append(robust)

    if current_stage and stage_by_observation:
        stage_members = [
            item
            for item in history
            if stage_by_observation.get(str(item.get("observation_ref"))) == current_stage
        ]
        stage = _comparison(
            field_id=field_id,
            indicator=indicator,
            current=current,
            members=stage_members,
            baseline_type="same_phenological_stage",
        )
        if stage:
            output.append(stage)
    return output
